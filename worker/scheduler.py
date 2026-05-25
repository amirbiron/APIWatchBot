"""הגדרת ה-scheduler של ה-worker. מבודד מ-__main__.py כדי שיהיה ניתן לבדיקה."""

from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.collectors.runner import CollectorRunner
from app.logging_config import get_logger

logger = get_logger(__name__)


def build_scheduler(
    runner: CollectorRunner,
    *,
    timezone: str = "Asia/Jerusalem",
    run_at_startup: bool = True,
) -> AsyncIOScheduler:
    """בונה scheduler עם cron triggers לפי סעיף 5.4 ב-Spec.

    אם `run_at_startup=True` — מוסיף job שירוץ מיד (next_run_time=datetime.now()).
    """
    scheduler = AsyncIOScheduler(timezone=timezone)

    # cron עיקרי — כל 6 שעות (00:00, 06:00, 12:00, 18:00 שעון ישראל)
    scheduler.add_job(
        runner.run_all,
        trigger=CronTrigger(hour="0,6,12,18", minute=0, timezone=timezone),
        id="collect_all_every_6h",
        name="collect_all_every_6h",
        # coalesce=True: אם החמצנו הרצה (worker היה down), נריץ פעם אחת ולא נדחוס
        coalesce=True,
        # max_instances=1: אסור שני runs במקביל — נחסום אם הקודם עוד לא הסתיים
        max_instances=1,
        misfire_grace_time=600,
    )

    if run_at_startup:
        # job חד-פעמי שירוץ מיד אחרי scheduler.start()
        from datetime import datetime, timedelta

        scheduler.add_job(
            runner.run_all,
            trigger="date",
            run_date=datetime.now() + timedelta(seconds=5),
            id="collect_all_startup",
            name="collect_all_startup",
            max_instances=1,
        )

    logger.info(
        "scheduler.built",
        timezone=timezone,
        jobs=[j.id for j in scheduler.get_jobs()],
    )
    return scheduler
