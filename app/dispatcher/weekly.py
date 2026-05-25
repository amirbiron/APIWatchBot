"""שולח סיכום שבועי (Spec §8.2). תזמון: ראשון 08:00 שעון ישראל.

לוגיקה לכל משתמש פעיל (לא paused, frequency=weekly):
1. שלוף updates ב-7 ימים אחרונים, processed, מסונן ל-subscribed_apis ו-min_severity.
2. סנן פריטים שכבר נשלחו (urgent ב-24 השעות האחרונות).
3. אם 0 → דלג (לא שולחים digest ריק — Spec §8.2).
4. claim פר update_id, build digest, split if long, send.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.dispatcher.delivery_repository import DeliveryRepository
from app.dispatcher.formatter import (
    build_weekly_digest,
    format_date_range,
    split_long_message,
)
from app.dispatcher.sender import TelegramSender
from app.logging_config import get_logger

logger = get_logger(__name__)

# חלון הזמן ל-updates בסיכום השבועי (Spec §8.2).
_LOOKBACK_DAYS = 7

# מיפוי min_severity של משתמש → קבוצת severities שיכללו בסיכום שלו.
# Spec §4.1: "critical" | "important" | "all".
SEVERITY_SETS: dict[str, set[str]] = {
    "critical": {"critical"},
    "important": {"critical", "important"},
    "all": {"critical", "important", "info"},
}


@dataclass
class WeeklyRunSummary:
    started_at: datetime
    finished_at: datetime
    users_checked: int = 0
    users_with_content: int = 0
    digests_sent: int = 0
    send_failures: int = 0


class WeeklyDispatcher:
    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        sender: TelegramSender,
        *,
        lookback_days: int = _LOOKBACK_DAYS,
    ) -> None:
        self._db = db
        self._sender = sender
        self._delivery_repo = DeliveryRepository(db)
        self._lookback = timedelta(days=lookback_days)

    async def run(self) -> WeeklyRunSummary:
        """תמיד מחזיר summary — לא זורק."""
        started = datetime.now(timezone.utc)
        summary = WeeklyRunSummary(started_at=started, finished_at=started)

        try:
            users = await self._fetch_eligible_users()
        except Exception:
            logger.exception("weekly.fetch_users_failed")
            summary.finished_at = datetime.now(timezone.utc)
            return summary

        summary.users_checked = len(users)
        cutoff = started - self._lookback
        date_range = format_date_range(cutoff, started)
        logger.info("weekly.run.start", users=len(users))

        for user in users:
            try:
                await self._dispatch_for_user(user, cutoff, date_range, summary)
            except Exception:
                logger.exception(
                    "weekly.user_unexpected",
                    user_hash=str(user.get("telegram_id"))[:6],
                )
                summary.send_failures += 1

        summary.finished_at = datetime.now(timezone.utc)
        logger.info(
            "weekly.run.done",
            users_checked=summary.users_checked,
            users_with_content=summary.users_with_content,
            digests_sent=summary.digests_sent,
            send_failures=summary.send_failures,
        )
        await self._write_state(summary)
        return summary

    async def _fetch_eligible_users(self) -> list[dict[str, Any]]:
        cursor = self._db.users.find(
            {"paused": False, "frequency": "weekly"}
        )
        return await cursor.to_list(length=None)

    async def _dispatch_for_user(
        self,
        user: dict[str, Any],
        cutoff: datetime,
        date_range: str,
        summary: WeeklyRunSummary,
    ) -> None:
        subscribed = user.get("subscribed_apis") or []
        if not subscribed:
            return  # משתמש בלי מנויים — אין מה לשלוח

        allowed_severities = SEVERITY_SETS.get(
            user.get("min_severity", "important"),
            SEVERITY_SETS["important"],
        )

        # שלוף את כל ה-candidates
        cursor = self._db.updates.find(
            {
                "api_id": {"$in": subscribed},
                "status": "processed",
                "severity": {"$in": list(allowed_severities)},
                "processed_at": {"$gte": cutoff},
            }
        ).sort("processed_at", -1)
        candidates = await cursor.to_list(length=None)
        if not candidates:
            return

        # סנן פריטים שכבר נשלחו (urgent מוקדם יותר השבוע, או digest ישן)
        candidate_ids = [c["_id"] for c in candidates]
        already_delivered = await self._delivery_repo.get_delivered_update_ids(
            user["_id"], candidate_ids
        )
        new_items = [c for c in candidates if c["_id"] not in already_delivered]
        if not new_items:
            return

        summary.users_with_content += 1

        message = build_weekly_digest(new_items, date_range=date_range)
        if message is None:
            return

        # claim פר update לפני send — אחרי הclaim, ה-items "שלנו" לסיכום הזה
        claimed_ids: list[Any] = []
        for item in new_items:
            if await self._delivery_repo.try_claim(
                user["_id"], item["_id"], "weekly_digest"
            ):
                claimed_ids.append(item["_id"])

        if not claimed_ids:
            # race נדיר — בין fetch ל-claim מישהו הספיק לשלוח. דלג.
            return

        # שלח (ייתכן בכמה חלקים אם ארוך)
        chunks = split_long_message(message)
        send_failed = False
        for chunk in chunks:
            result = await self._sender.send(user["telegram_id"], chunk)
            if not result.success:
                send_failed = True
                # אם נכשל בחלק הראשון — אין טעם להמשיך לשאר.
                break

        if send_failed:
            summary.send_failures += 1
        else:
            summary.digests_sent += 1

    async def _write_state(self, summary: WeeklyRunSummary) -> None:
        try:
            await self._db.system_state.update_one(
                {"key": "last_weekly_run"},
                {
                    "$set": {
                        "value": {
                            "started_at": summary.started_at,
                            "finished_at": summary.finished_at,
                            "users_checked": summary.users_checked,
                            "users_with_content": summary.users_with_content,
                            "digests_sent": summary.digests_sent,
                            "send_failures": summary.send_failures,
                        },
                        "updated_at": summary.finished_at,
                    }
                },
                upsert=True,
            )
        except Exception:
            logger.exception("weekly.state_write_failed")
