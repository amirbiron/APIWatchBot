"""שכבת CRUD על קולקציית `users`.

מבדיל את ההנדלרים מ-MongoDB ישירות. כל הפעולות אסינכרוניות ומחזירות
dict (לא Pydantic model) כי MongoDB מחזיר dict ואין סיבה לעטוף.

עיקרון מ-CLAUDE.md כלל 2: state transitions עם תנאי (state חזוי) חייבים
להיות אטומיים. משתמשים ב-`find_one_and_update` במקום SELECT+UPDATE.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.logging_config import get_logger

logger = get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserRepository:
    """כל הפעולות על users עוברות פה."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._db = db

    async def get(self, telegram_id: int) -> dict[str, Any] | None:
        return await self._db.users.find_one({"telegram_id": telegram_id})

    async def get_or_create(
        self,
        telegram_id: int,
        *,
        username: str | None = None,
        first_name: str | None = None,
        language_code: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        """מחזיר (user_doc, created). אטומי דרך insert + catch DuplicateKey.

        ל-2 webhooks מקבילים: הראשון insert מצליח (created=True), השני
        תופס DuplicateKey ועושה update של last_active_at (created=False).
        זה אטומי לחלוטין — מסתמך על unique index של telegram_id.
        """
        now = _utcnow()
        new_doc = {
            "telegram_id": telegram_id,
            "username": username,
            "first_name": first_name,
            "language_code": language_code,
            "subscribed_apis": [],
            "min_severity": "important",
            "frequency": "weekly",
            "receive_urgent_alerts": True,
            "registered_at": now,
            "last_active_at": now,
            "paused": False,
            "conversation_state": "idle",
        }

        try:
            await self._db.users.insert_one(new_doc)
            return new_doc, True
        except DuplicateKeyError:
            existing = await self._db.users.find_one_and_update(
                {"telegram_id": telegram_id},
                {"$set": {"last_active_at": now}},
                return_document=ReturnDocument.AFTER,
            )
            # אם הgvideo המקורי נמחק בין ה-insert ל-find — נחזור לעצמנו
            if existing is None:
                # tiny race window — נסה insert שוב
                try:
                    await self._db.users.insert_one(new_doc)
                    return new_doc, True
                except DuplicateKeyError:
                    existing = await self._db.users.find_one(
                        {"telegram_id": telegram_id}
                    )
            return existing or new_doc, False

    async def set_conversation_state(
        self,
        telegram_id: int,
        new_state: str,
        *,
        expected_state: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """מעבר state אטומי. אם `expected_state` סופק — מתבצע רק אם המצב
        הנוכחי תואם (מונע race בין callbacks מהירים רצופים).

        `extra` — שדות נוספים לעדכון באותה פעולה (לדוגמה min_severity).
        """
        query: dict[str, Any] = {"telegram_id": telegram_id}
        if expected_state is not None:
            query["conversation_state"] = expected_state

        update_set: dict[str, Any] = {
            "conversation_state": new_state,
            "last_active_at": _utcnow(),
        }
        if extra:
            update_set.update(extra)

        return await self._db.users.find_one_and_update(
            query,
            {"$set": update_set},
            return_document=ReturnDocument.AFTER,
        )

    async def toggle_subscription(
        self, telegram_id: int, api_id: str
    ) -> dict[str, Any] | None:
        """מוסיף/מסיר api_id מ-subscribed_apis — אטומי לחלוטין.

        כלל 2 ב-CLAUDE.md אוסר על check-then-act. הדפוס הזה משתמש
        בשתי קריאות `find_one_and_update` עם predicate על מצב הרשימה,
        כך שכל פעולה היא atomic compare-and-swap:

        1. נסה add עם תנאי "api_id לא ברשימה". אם נמצא — הוסף.
        2. אחרת נסה remove עם תנאי "api_id כן ברשימה". אם נמצא — הסר.
        3. אם שניהם לא נמצאו — המשתמש לא קיים.

        תרחיש 2 קליקים מהירים מאותו משתמש:
        - T1: add (succeeds, רשימה עכשיו מכילה).
        - T2: add נכשל (predicate "not in" לא תואם), עובר ל-pull
              והוא מצליח (predicate "in" תואם). רשימה עכשיו ריקה.
        כלומר 2 קליקים = 2 הפיכות, כצפוי.
        """
        now = _utcnow()

        # נסה ADD — predicate "api_id לא ברשימה כרגע"
        added = await self._db.users.find_one_and_update(
            {"telegram_id": telegram_id, "subscribed_apis": {"$ne": api_id}},
            {
                "$addToSet": {"subscribed_apis": api_id},
                "$set": {"last_active_at": now},
            },
            return_document=ReturnDocument.AFTER,
        )
        if added is not None:
            return added

        # ADD לא קרה כי api_id כבר ברשימה (או המשתמש לא קיים). נסה REMOVE.
        removed = await self._db.users.find_one_and_update(
            {"telegram_id": telegram_id, "subscribed_apis": api_id},
            {
                "$pull": {"subscribed_apis": api_id},
                "$set": {"last_active_at": now},
            },
            return_document=ReturnDocument.AFTER,
        )
        return removed  # None אם המשתמש לא קיים בכלל

    async def set_paused(self, telegram_id: int, paused: bool) -> bool:
        """מחזיר True אם השינוי בוצע (משתמש קיים)."""
        result = await self._db.users.update_one(
            {"telegram_id": telegram_id},
            {"$set": {"paused": paused, "last_active_at": _utcnow()}},
        )
        return result.matched_count > 0

    async def update_settings(
        self,
        telegram_id: int,
        *,
        min_severity: str | None = None,
        frequency: str | None = None,
        receive_urgent_alerts: bool | None = None,
    ) -> dict[str, Any] | None:
        """עדכון מספר שדות העדפה בקריאה אחת. None = לא משנים."""
        updates: dict[str, Any] = {"last_active_at": _utcnow()}
        if min_severity is not None:
            updates["min_severity"] = min_severity
        if frequency is not None:
            updates["frequency"] = frequency
        if receive_urgent_alerts is not None:
            updates["receive_urgent_alerts"] = receive_urgent_alerts

        return await self._db.users.find_one_and_update(
            {"telegram_id": telegram_id},
            {"$set": updates},
            return_document=ReturnDocument.AFTER,
        )

    async def delete(self, telegram_id: int) -> bool:
        """מחיקה מלאה של המשתמש. Spec §7.1: /stop = מחיקה מהמערכת."""
        result = await self._db.users.delete_one({"telegram_id": telegram_id})
        return result.deleted_count > 0
