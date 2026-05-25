"""שולח התראות מיידיות (Spec §8.1). תזמון: שעתי.

לוגיקה:
1. שלוף updates עם is_urgent=True, status=processed, processed_at ב-24h.
2. עבור כל update — שלוף משתמשים מנויים שלא מושהים שמסכימים לדחוף.
3. claim אטומי דרך delivery + send. במקרה כשל send — log + continue.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.dispatcher.delivery_repository import DeliveryRepository
from app.dispatcher.formatter import build_urgent_message
from app.dispatcher.sender import TelegramSender
from app.logging_config import get_logger

logger = get_logger(__name__)

# חלון הזמן ל-updates דחופים (Spec §8.1).
_LOOKBACK_HOURS = 24


@dataclass
class UrgentRunSummary:
    started_at: datetime
    finished_at: datetime
    updates_checked: int = 0
    messages_sent: int = 0
    already_delivered: int = 0
    send_failures: int = 0


class UrgentDispatcher:
    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        sender: TelegramSender,
        *,
        lookback_hours: int = _LOOKBACK_HOURS,
    ) -> None:
        self._db = db
        self._sender = sender
        self._delivery_repo = DeliveryRepository(db)
        self._lookback = timedelta(hours=lookback_hours)

    async def run(self) -> UrgentRunSummary:
        """תמיד מחזיר summary — לא זורק. APScheduler לא יפיל את ה-job."""
        started = datetime.now(timezone.utc)
        summary = UrgentRunSummary(started_at=started, finished_at=started)

        try:
            updates = await self._fetch_urgent_updates(started)
        except Exception:
            logger.exception("urgent.fetch_failed")
            summary.finished_at = datetime.now(timezone.utc)
            return summary

        summary.updates_checked = len(updates)
        logger.info("urgent.run.start", count=len(updates))

        for update in updates:
            await self._dispatch_one_update(update, summary)

        summary.finished_at = datetime.now(timezone.utc)
        logger.info(
            "urgent.run.done",
            updates_checked=summary.updates_checked,
            messages_sent=summary.messages_sent,
            already_delivered=summary.already_delivered,
            send_failures=summary.send_failures,
        )
        await self._write_state(summary)
        return summary

    async def _fetch_urgent_updates(self, now: datetime) -> list[dict[str, Any]]:
        cutoff = now - self._lookback
        cursor = self._db.updates.find(
            {
                "is_urgent": True,
                "status": "processed",
                "processed_at": {"$gte": cutoff},
            }
        )
        return await cursor.to_list(length=None)

    async def _dispatch_one_update(
        self,
        update: dict[str, Any],
        summary: UrgentRunSummary,
    ) -> None:
        try:
            users = await self._fetch_eligible_users(update["api_id"])
        except Exception:
            logger.exception(
                "urgent.users_fetch_failed", update_id=str(update.get("_id"))
            )
            return

        message = build_urgent_message(update)

        for user in users:
            try:
                await self._send_to_user(user, update, message, summary)
            except Exception:
                # הגנה אחרונה — לעולם לא להפיל את שאר ה-batch
                logger.exception(
                    "urgent.send_unexpected",
                    user_hash=str(user.get("telegram_id"))[:6],
                )
                summary.send_failures += 1

    async def _fetch_eligible_users(self, api_id: str) -> list[dict[str, Any]]:
        cursor = self._db.users.find(
            {
                "subscribed_apis": api_id,
                "paused": False,
                "receive_urgent_alerts": True,
            }
        )
        return await cursor.to_list(length=None)

    async def _send_to_user(
        self,
        user: dict[str, Any],
        update: dict[str, Any],
        message: str,
        summary: UrgentRunSummary,
    ) -> None:
        user_id = user["_id"]
        update_id = update["_id"]
        telegram_id = user["telegram_id"]

        # claim לפני send — מבטיח שאם שני workers ירוצו במקביל, רק אחד שולח.
        claimed = await self._delivery_repo.try_claim(
            user_id, update_id, "urgent"
        )
        if not claimed:
            summary.already_delivered += 1
            return

        result = await self._sender.send(telegram_id, message)
        if result.success:
            summary.messages_sent += 1
        else:
            summary.send_failures += 1
            # ה-delivery row נשארת — לא ננסה שוב בריצה הבאה (Spec: pas
            # de duplicate sends). אם משתמש חסם, זה ה-end state שלו.

    async def _write_state(self, summary: UrgentRunSummary) -> None:
        try:
            await self._db.system_state.update_one(
                {"key": "last_urgent_run"},
                {
                    "$set": {
                        "value": {
                            "started_at": summary.started_at,
                            "finished_at": summary.finished_at,
                            "updates_checked": summary.updates_checked,
                            "messages_sent": summary.messages_sent,
                            "already_delivered": summary.already_delivered,
                            "send_failures": summary.send_failures,
                        },
                        "updated_at": summary.finished_at,
                    }
                },
                upsert=True,
            )
        except Exception:
            logger.exception("urgent.state_write_failed")
