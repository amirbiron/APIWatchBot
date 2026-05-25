"""ניהול חיבור אסינכרוני יחיד ל-MongoDB (Motor)."""

from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import get_settings
from app.logging_config import get_logger

logger = get_logger(__name__)

# מצב מודולרי — נוצר פעם אחת ב-startup וסגור ב-shutdown.
_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


async def connect_to_mongo() -> AsyncIOMotorDatabase:
    """לקרוא ב-startup של FastAPI / worker."""
    global _client, _db

    if _db is not None:
        return _db

    settings = get_settings()
    if not settings.mongodb_configured:
        raise RuntimeError("MONGODB_URI לא מוגדר — לא ניתן להתחבר למסד הנתונים.")

    logger.info("mongo.connect.start", db_name=settings.mongodb_db_name)
    _client = AsyncIOMotorClient(
        settings.mongodb_uri,
        # timeout קצר יחסית כדי שלא נתקע ב-startup אם MongoDB לא זמין
        serverSelectionTimeoutMS=10_000,
        tz_aware=True,
    )

    # אימות חיבור ע"י ping — נכשל מהר אם ה-URI שגוי
    await _client.admin.command("ping")
    _db = _client[settings.mongodb_db_name]
    logger.info("mongo.connect.ok", db_name=settings.mongodb_db_name)

    return _db


async def close_mongo_connection() -> None:
    """לקרוא ב-shutdown."""
    global _client, _db
    if _client is not None:
        logger.info("mongo.close")
        _client.close()
        _client = None
        _db = None


def get_db() -> AsyncIOMotorDatabase:
    """לשימוש בקוד שכבר יודע שיש חיבור פעיל."""
    if _db is None:
        raise RuntimeError("MongoDB לא מחובר — יש לקרוא ל-connect_to_mongo() קודם.")
    return _db
