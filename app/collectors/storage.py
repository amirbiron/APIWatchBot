"""שמירת פריטים גולמיים ל-DB עם dedup אטומי.

לפי כלל 2 ב-CLAUDE.md: אסור להפריד check-then-act. במקום SELECT+INSERT,
נסתמך על unique index של `content_hash` ונתפוס DuplicateKeyError.
זה אטומי לחלוטין — לא יכול לקרות race condition בין שני workers/jobs.
"""

from __future__ import annotations

from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from app.collectors.base import RawItem
from app.logging_config import get_logger

logger = get_logger(__name__)


async def save_raw_items(
    db: AsyncIOMotorDatabase,
    items: list[RawItem],
) -> tuple[int, int]:
    """שומר את הפריטים. מחזיר (inserted, duplicates).

    כל פריט נשמר ב-insert_one נפרד כדי שכפילות של אחד לא תפיל את כל ה-batch
    (insert_many עם ordered=False זורק BulkWriteError ולא תמיד נוח לעבד).
    """
    inserted = 0
    duplicates = 0
    now = datetime.now(timezone.utc)

    for item in items:
        doc = {
            "api_id": item.api_id,
            "raw_title": item.raw_title,
            "raw_content": item.raw_content,
            "source_url": item.source_url,
            "source_published_at": item.source_published_at,
            "content_hash": item.content_hash,
            # תוצרי AI — יתמלאו בשלב 3
            "summary_he": None,
            "severity": None,
            "is_urgent": False,
            "categories": [],
            # מטא
            "collected_at": now,
            "processed_at": None,
            "status": "raw",
        }
        try:
            await db.updates.insert_one(doc)
            inserted += 1
        except DuplicateKeyError:
            # כבר קיים — זה התרחיש הצפוי לרוב הפריטים
            duplicates += 1

    return inserted, duplicates
