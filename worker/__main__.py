"""Worker entrypoint — מריץ Collector (ובעתיד גם Dispatcher).

בשלב 2a: APScheduler עם 3 מקורות RSS + הרצה ראשונה ב-startup.
"""

from __future__ import annotations

import asyncio
import signal

import httpx

from app.collectors.registry import build_sources
from app.collectors.runner import CollectorRunner
from app.config import get_settings
from app.db.client import close_mongo_connection, connect_to_mongo
from app.db.indexes import ensure_indexes
from app.logging_config import configure_logging, get_logger
from worker.scheduler import build_scheduler

logger = get_logger(__name__)


async def main() -> None:
    settings = get_settings()
    configure_logging(
        level=settings.log_level,
        json_output=settings.environment != "development",
    )
    logger.info("worker.startup", environment=settings.environment)

    if not settings.mongodb_configured:
        raise RuntimeError("MONGODB_URI חסר — ה-worker לא יכול לרוץ בלי DB.")

    db = await connect_to_mongo()
    await ensure_indexes(db)

    # http client אחד משותף בין כל המקורות — חוסך פתיחת connections.
    async with httpx.AsyncClient(
        headers={"User-Agent": "APIWatchBot/0.1 (+https://github.com/amirbiron/APIWatchBot)"},
        follow_redirects=True,
        timeout=30.0,
    ) as http_client:
        sources = build_sources(http_client)
        runner = CollectorRunner(sources=sources, db=db)
        scheduler = build_scheduler(runner, timezone=settings.timezone, run_at_startup=True)

        scheduler.start()
        logger.info("worker.ready", source_count=len(sources))

        # המתנה ל-SIGTERM/SIGINT
        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop_event.set)

        await stop_event.wait()

        logger.info("worker.shutdown.start")
        # wait=False כי אם יש job רץ נחכה לו מעט אבל לא לנצח
        scheduler.shutdown(wait=False)

    await close_mongo_connection()
    logger.info("worker.shutdown.done")


if __name__ == "__main__":
    asyncio.run(main())
