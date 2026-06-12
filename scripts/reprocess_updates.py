"""תיקון חד-פעמי: איפוס פריטים קיימים לעיבוד מחדש עם חילוץ תאריך.

רקע: עד עכשיו ה-dispatchers סיננו לפי processed_at (זמן העיבוד) ולא לפי
source_published_at (תאריך הפרסום האמיתי). הפריטים שכבר עובדו לא קיבלו
תאריך פרסום מ-Gemini. הסקריפט הזה מאפס אותם ל-status="raw" כדי שה-AI
processor יעבד אותם מחדש עם הפרומפט החדש שמחלץ תאריך.

עקרונות:
- reset ולא delete — שומר את ה-_id-ים, כך שרשומות deliveries קיימות
  (פריטים שכבר נשלחו) נשארות תקפות ולא יישלחו שוב.
- מנקה source_published_at רק למקורות HTML (התאריך יחולץ מחדש ע"י Gemini).
  למקורות RSS משאיר את התאריך האמין של feedparser.

הרצה (פעם אחת, מול ה-DB של הפרודקשן):
    python -m scripts.reprocess_updates
"""

from __future__ import annotations

import asyncio

from app.collectors.registry import ALL_SOURCES
from app.collectors.sources._feed_utils import BaseFeedSource
from app.db.client import close_mongo_connection, connect_to_mongo
from app.logging_config import configure_logging, get_logger

logger = get_logger(__name__)

# api_ids של מקורות RSS — שם feedparser נותן תאריך אמין שאין סיבה למחוק.
_RSS_API_IDS = sorted(
    {cls.api_id for cls in ALL_SOURCES if issubclass(cls, BaseFeedSource)}
)

# סטטוסים שכבר "נגעו" בהם — נחזיר ל-raw לעיבוד מחדש.
_PROCESSED_STATUSES = ["processed", "skipped_noise", "failed"]


async def main() -> None:
    configure_logging(level="INFO", json_output=False)
    db = await connect_to_mongo()
    try:
        logger.info("reprocess.start", rss_api_ids=_RSS_API_IDS)

        # ניקוי שדות ה-AI + החזרה ל-raw, בשתי קבוצות *זרות* (לפי api_id).
        # קריטי שכל מסמך ייגע בו פעם אחת בלבד ובפעולה אטומית אחת: אחרת,
        # אם ה-worker מעבד פריט בין שתי קריאות, פעולה שנייה הייתה דורסת
        # את התאריך שזה עתה חולץ. כאן non-RSS ו-RSS אינם חופפים, וכל
        # קבוצה מקבלת את כל ה-$set בבת אחת.
        _reset_fields = {
            "status": "raw",
            "summary_he": None,
            "severity": None,
            "is_urgent": False,
            "categories": [],
            "processed_at": None,
        }

        # מקורות HTML — מנקים גם source_published_at כדי ש-Gemini יחלץ מחדש.
        reset_html = await db.updates.update_many(
            {
                "status": {"$in": _PROCESSED_STATUSES},
                "api_id": {"$nin": _RSS_API_IDS},
            },
            {"$set": {**_reset_fields, "source_published_at": None}},
        )

        # מקורות RSS — משאירים את source_published_at (feedparser אמין).
        reset_rss = await db.updates.update_many(
            {
                "status": {"$in": _PROCESSED_STATUSES},
                "api_id": {"$in": _RSS_API_IDS},
            },
            {"$set": _reset_fields},
        )

        logger.info(
            "reprocess.done",
            html_reset=reset_html.modified_count,
            rss_reset=reset_rss.modified_count,
        )
    finally:
        await close_mongo_connection()


if __name__ == "__main__":
    asyncio.run(main())
