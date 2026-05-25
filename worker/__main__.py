"""שלד worker — בשלב 1 רק מוכיח חיים.

בשלבים הבאים ייתווסף כאן APScheduler עם:
  - Collector (כל 6 שעות)
  - AI processor (כל 5 דקות לפריטים חדשים)
  - Dispatcher (כל שעה לדחופים, ראשון 08:00 לשבועי)
"""

from __future__ import annotations

import asyncio
import signal

from app.config import get_settings
from app.db.client import close_mongo_connection, connect_to_mongo
from app.db.indexes import ensure_indexes
from app.logging_config import configure_logging, get_logger

logger = get_logger(__name__)


async def main() -> None:
    settings = get_settings()
    configure_logging(
        level=settings.log_level,
        json_output=settings.environment != "development",
    )
    logger.info("worker.startup", environment=settings.environment)

    if settings.mongodb_configured:
        db = await connect_to_mongo()
        await ensure_indexes(db)

    # המתנה ל-SIGTERM/SIGINT — בעתיד כאן יהיה scheduler.start() במקום event
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop_event.set)

    logger.info("worker.ready", note="שלד בלבד — collectors יתווספו בשלב 2")
    await stop_event.wait()

    logger.info("worker.shutdown")
    if settings.mongodb_configured:
        await close_mongo_connection()


if __name__ == "__main__":
    asyncio.run(main())
