"""Worker entrypoint — מריץ Collector (ובעתיד גם Dispatcher).

בשלב 2a: APScheduler עם 3 מקורות RSS + הרצה ראשונה ב-startup.
"""

from __future__ import annotations

import asyncio
import signal

import httpx

from app.ai.client import GeminiClient
from app.ai.processor import AIProcessor
from app.collectors.registry import build_sources
from app.collectors.runner import CollectorRunner
from app.config import get_settings
from app.db.client import close_mongo_connection, connect_to_mongo
from app.db.indexes import ensure_indexes
from app.logging_config import configure_logging, get_logger
from worker.scheduler import build_scheduler

logger = get_logger(__name__)


async def main() -> None:
    """startup → loop → shutdown עם cleanup מובטח.

    דפוס זהה ל-app/main.py:lifespan — כל רכישת משאב מסומנת ב-flag,
    וה-finally מנקה רק את מה שבאמת נרכש. אם ensure_indexes או
    scheduler.start נכשלים אחרי שmongo כבר התחבר, החיבור נסגר בכל זאת.
    """
    settings = get_settings()
    configure_logging(
        level=settings.log_level,
        json_output=settings.environment != "development",
    )
    logger.info("worker.startup", environment=settings.environment)

    if not settings.mongodb_configured:
        raise RuntimeError("MONGODB_URI חסר — ה-worker לא יכול לרוץ בלי DB.")

    mongo_connected = False
    try:
        db = await connect_to_mongo()
        mongo_connected = True
        await ensure_indexes(db)

        # http client אחד משותף בין כל המקורות — חוסך פתיחת connections.
        # ה-async with מבטיח סגירה בכל מקרה, גם בכשל פנימי.
        async with httpx.AsyncClient(
            headers={"User-Agent": "APIWatchBot/0.1 (+https://github.com/amirbiron/APIWatchBot)"},
            follow_redirects=True,
            timeout=30.0,
        ) as http_client:
            scheduler = None
            scheduler_started = False
            try:
                sources = build_sources(http_client)
                runner = CollectorRunner(sources=sources, db=db)

                # AI processor — אופציונלי. בלי GEMINI_API_KEY הworker
                # עדיין רץ ואוסף raw items; הם פשוט יישארו ב-status="raw"
                # עד שה-key יוגדר.
                ai_processor: AIProcessor | None = None
                if settings.ai_configured:
                    ai_client = GeminiClient(
                        api_key=settings.gemini_api_key.get_secret_value()
                    )
                    ai_processor = AIProcessor(db=db, ai_client=ai_client)
                    logger.info("worker.ai.enabled")
                else:
                    logger.warning(
                        "worker.ai.skipped",
                        reason="GEMINI_API_KEY חסר",
                    )

                scheduler = build_scheduler(
                    runner,
                    timezone=settings.timezone,
                    run_at_startup=True,
                    ai_processor=ai_processor,
                )

                scheduler.start()
                scheduler_started = True
                logger.info(
                    "worker.ready",
                    source_count=len(sources),
                    ai_enabled=ai_processor is not None,
                )

                # המתנה ל-SIGTERM/SIGINT
                stop_event = asyncio.Event()
                loop = asyncio.get_running_loop()
                for sig in (signal.SIGTERM, signal.SIGINT):
                    loop.add_signal_handler(sig, stop_event.set)

                await stop_event.wait()
                logger.info("worker.shutdown.start")
            finally:
                # scheduler נסגר *לפני* יציאה מ-async with httpx, כדי שjobs
                # שעוד רצים לא ייפלו על http_client סגור.
                if scheduler_started and scheduler is not None:
                    try:
                        scheduler.shutdown(wait=False)
                    except Exception:
                        logger.exception("worker.scheduler_shutdown_failed")
    finally:
        if mongo_connected:
            try:
                await close_mongo_connection()
            except Exception:
                logger.exception("worker.mongo_close_failed")
    logger.info("worker.shutdown.done")


if __name__ == "__main__":
    asyncio.run(main())
