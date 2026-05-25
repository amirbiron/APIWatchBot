"""שכבת CRUD על קולקציית `deliveries` עם claim אטומי.

כלל 2 ב-CLAUDE.md: claim הוא check-then-act קלאסי שחייב להיות אטומי.
משתמשים ב-insert_one + DuplicateKeyError על ה-unique index של
(user_id, update_id). זה מבטיח שגם אם 2 הרצות חופפות (urgent ו-weekly
על אותו פריט באותו זמן), רק אחת תצליח לתפוס.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from app.logging_config import get_logger

logger = get_logger(__name__)

DeliveryType = Literal["urgent", "weekly_digest"]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DeliveryRepository:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._db = db

    async def try_claim(
        self,
        user_id: Any,
        update_id: Any,
        delivery_type: DeliveryType,
    ) -> bool:
        """מנסה לתפוס delivery slot עבור (user, update). אטומי.

        מחזיר True אם תפסנו (גם אם שליחה תיכשל בהמשך, ה-slot שלנו).
        מחזיר False אם כבר תפוס (משתמש קיבל את הפריט הזה בעבר).

        ה-unique index מבטיח שגם בריצות מקבילות רק אחת תצליח.
        """
        doc = {
            "user_id": user_id,
            "update_id": update_id,
            "delivery_type": delivery_type,
            "sent_at": _utcnow(),
        }
        try:
            await self._db.deliveries.insert_one(doc)
            return True
        except DuplicateKeyError:
            return False

    async def get_delivered_update_ids(
        self,
        user_id: Any,
        candidate_update_ids: list[Any],
    ) -> set[Any]:
        """מחזיר את ה-update_id-ים מהרשימה שכבר נשלחו ל-user.

        שימוש: weekly digest שולף קודם מועמדים, אז מסיר את אלה שכבר
        נשלחו (כ-urgent ב-24 השעות האחרונות, לדוגמה).
        """
        if not candidate_update_ids:
            return set()

        cursor = self._db.deliveries.find(
            {"user_id": user_id, "update_id": {"$in": candidate_update_ids}},
            projection={"update_id": 1, "_id": 0},
        )
        delivered = await cursor.to_list(length=None)
        return {d["update_id"] for d in delivered}

    async def release(
        self,
        user_id: Any,
        update_ids: list[Any],
        delivery_type: DeliveryType,
    ) -> int:
        """מבטל claims שלא הצלחנו לעמוד בהם (לדוגמה: weekly digest
        שהשליחה שלו נכשלה). מחזיר מספר הרשומות שנמחקו.

        הגבלה לפי delivery_type חשובה — אם פריט נשלח קודם כ-urgent
        ועכשיו ניסיון weekly נכשל, אסור למחוק את ה-urgent delivery.
        """
        if not update_ids:
            return 0
        result = await self._db.deliveries.delete_many(
            {
                "user_id": user_id,
                "update_id": {"$in": update_ids},
                "delivery_type": delivery_type,
            }
        )
        return result.deleted_count
