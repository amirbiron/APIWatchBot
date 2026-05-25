"""יצירת כל האינדקסים הנדרשים לפי סעיף 4 של docs/Spec.md.

הפונקציה idempotent — Mongo יזהה אינדקסים קיימים ולא יצור שוב.
"""

from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING, IndexModel

from app.logging_config import get_logger

logger = get_logger(__name__)


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    """יוצר/מוודא את כל האינדקסים. בטוח להריץ בכל startup."""

    # users
    await db.users.create_indexes(
        [
            IndexModel([("telegram_id", ASCENDING)], unique=True, name="uniq_telegram_id"),
            IndexModel([("subscribed_apis", ASCENDING)], name="multikey_subscribed_apis"),
            IndexModel([("paused", ASCENDING)], name="paused"),
        ]
    )

    # updates
    await db.updates.create_indexes(
        [
            IndexModel([("content_hash", ASCENDING)], unique=True, name="uniq_content_hash"),
            IndexModel(
                [("api_id", ASCENDING), ("collected_at", DESCENDING)],
                name="api_id_collected_at",
            ),
            IndexModel(
                [("is_urgent", ASCENDING), ("processed_at", DESCENDING)],
                name="urgent_processed_at",
            ),
            IndexModel([("status", ASCENDING)], name="status"),
        ]
    )

    # deliveries — מונע שליחה כפולה של אותו update לאותו user
    await db.deliveries.create_indexes(
        [
            IndexModel(
                [("user_id", ASCENDING), ("update_id", ASCENDING)],
                unique=True,
                name="uniq_user_update",
            ),
            IndexModel([("sent_at", DESCENDING)], name="sent_at"),
        ]
    )

    # system_state — key/value פנימי
    await db.system_state.create_indexes(
        [
            IndexModel([("key", ASCENDING)], unique=True, name="uniq_key"),
        ]
    )

    logger.info("mongo.indexes.ensured")
