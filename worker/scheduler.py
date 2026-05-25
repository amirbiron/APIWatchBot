"""הגדרת ה-scheduler של ה-worker. מבודד מ-__main__.py כדי שיהיה ניתן לבדיקה."""

from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.ai.processor import AIProcessor
from app.collectors.runner import CollectorRunner
from app.dispatcher.urgent import UrgentDispatcher
from app.dispatcher.weekly import WeeklyDispatcher
from app.logging_config import get_logger

logger = get_logger(__name__)


def build_scheduler(
    runner: CollectorRunner,
    *,
    timezone: str = "Asia/Jerusalem",
    run_at_startup: bool = True,
    ai_processor: AIProcessor | None = None,
    urgent_dispatcher: UrgentDispatcher | None = None,
    weekly_dispatcher: WeeklyDispatcher | None = None,
) -> AsyncIOScheduler:
    """בונה scheduler עם cron triggers לפי סעיף 5.4 ב-Spec.

    אם `run_at_startup=True` — מוסיף job שירוץ מיד (next_run_time=datetime.now()).
    אם `ai_processor` מועבר — מוסיף job AI כל 5 דקות.
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

    # AI processor — job אופציונלי שרץ אם יש GEMINI_API_KEY.
    if ai_processor is not None:
        scheduler.add_job(
            ai_processor.run_batch,
            trigger=IntervalTrigger(minutes=5, timezone=timezone),
            id="process_ai_batch",
            name="process_ai_batch",
            coalesce=True,
            max_instances=1,
            misfire_grace_time=120,
        )

    # Urgent dispatcher — job אופציונלי. Spec §8.1: שעתי.
    if urgent_dispatcher is not None:
        scheduler.add_job(
            urgent_dispatcher.run,
            trigger=CronTrigger(minute=0, timezone=timezone),
            id="dispatch_urgent",
            name="dispatch_urgent",
            coalesce=True,
            max_instances=1,
            misfire_grace_time=300,
        )

    # Weekly dispatcher — Spec §8.2: ראשון 08:00 שעון ישראל.
    # APScheduler day_of_week: 0=Mon ... 6=Sun (תואם cron-style).
    if weekly_dispatcher is not None:
        scheduler.add_job(
            weekly_dispatcher.run,
            trigger=CronTrigger(
                day_of_week="sun", hour=8, minute=0, timezone=timezone
            ),
            id="dispatch_weekly",
            name="dispatch_weekly",
            coalesce=True,
            max_instances=1,
            misfire_grace_time=3600,  # שעה — שווה לנסות גם אם איחרנו
        )

    if run_at_startup:
        # job חד-פעמי שירוץ מיד אחרי scheduler.start().
        # חשוב: APScheduler מפרש datetime *naive* בטיימזון של ה-scheduler
        # (Asia/Jerusalem), כך שעל שרת UTC זה היה הופך לזמן בעבר ונדחה
        # ע"י misfire_grace_time הדיפולטיבי. לכן יוצרים datetime tz-aware.
        from datetime import datetime, timedelta

        import pytz

        tz = pytz.timezone(timezone)
        run_date = datetime.now(tz) + timedelta(seconds=5)

        scheduler.add_job(
            runner.run_all,
            trigger="date",
            run_date=run_date,
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
