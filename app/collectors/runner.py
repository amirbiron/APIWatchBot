"""מריץ את כל המקורות במקביל ושומר את הפריטים.

עיקרון: כשל במקור אחד אסור שיפיל את האחרים. כל מקור עטוף ב-try/except
ומחזיר תוצאה מובנית. גם עידכון `system_state` עם זמן הרצה אחרון.
"""

from __future__ import annotations

import asyncio
import html
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from app.collectors.base import BaseSource
from app.collectors.storage import save_raw_items
from app.logging_config import get_logger
from app.utils.notify import notify_admin

logger = get_logger(__name__)

# סף שליחת התראה לאדמין על כשלים רצופים (Spec §5.2 ל-Meta).
# מתפעל בדיוק על הערך הזה — לא ב-> כדי להמנע מספאם בכשלים 4+.
_ALERT_AT_CONSECUTIVE_FAILURES = 3


@dataclass
class SourceResult:
    api_id: str
    fetched: int = 0
    inserted: int = 0
    duplicates: int = 0
    error: str | None = None
    duration_ms: int = 0


@dataclass
class RunSummary:
    started_at: datetime
    finished_at: datetime
    results: list[SourceResult] = field(default_factory=list)

    @property
    def total_inserted(self) -> int:
        return sum(r.inserted for r in self.results)

    @property
    def failed_sources(self) -> list[str]:
        return [r.api_id for r in self.results if r.error is not None]


class CollectorRunner:
    """מתאם הרצה של כל המקורות."""

    def __init__(
        self,
        sources: list[BaseSource],
        db: AsyncIOMotorDatabase,
    ) -> None:
        self._sources = sources
        self._db = db

    async def run_all(self) -> RunSummary:
        """מריץ את כל המקורות במקביל. תמיד מחזיר RunSummary — לא זורק."""
        started_at = datetime.now(timezone.utc)
        logger.info("collector.run.start", source_count=len(self._sources))

        results = await asyncio.gather(
            *(self._run_one(source) for source in self._sources),
            return_exceptions=False,  # _run_one כבר תופס הכל
        )

        finished_at = datetime.now(timezone.utc)
        summary = RunSummary(
            started_at=started_at,
            finished_at=finished_at,
            results=list(results),
        )

        # שמירת מטא ב-system_state — שימושי לאדמין ולבדיקה ידנית.
        # עטוף ב-try/except כדי לקיים את החוזה "לא זורק" — כשל ב-DB
        # write הזה לא צריך לבטל את ה-summary שבו ה-collection כבר הצליח.
        try:
            await self._db.system_state.update_one(
                {"key": "last_collect_run"},
                {
                    "$set": {
                        "value": {
                            "started_at": started_at,
                            "finished_at": finished_at,
                            "total_inserted": summary.total_inserted,
                            "failed_sources": summary.failed_sources,
                        },
                        "updated_at": finished_at,
                    }
                },
                upsert=True,
            )
        except Exception:
            logger.exception("collector.run.state_write_failed")

        logger.info(
            "collector.run.done",
            duration_ms=int((finished_at - started_at).total_seconds() * 1000),
            total_inserted=summary.total_inserted,
            failed=summary.failed_sources,
        )
        return summary

    async def _run_one(self, source: BaseSource) -> SourceResult:
        """הרצת מקור בודד — תמיד מחזיר תוצאה, אף פעם לא זורק."""
        start = datetime.now(timezone.utc)
        result = SourceResult(api_id=source.api_id)

        fetch_succeeded = False
        try:
            items = await source.fetch()
            result.fetched = len(items)
            inserted, duplicates = await save_raw_items(self._db, items)
            result.inserted = inserted
            result.duplicates = duplicates
            fetch_succeeded = True

            logger.info(
                "collector.source.success",
                api_id=source.api_id,
                fetched=result.fetched,
                inserted=result.inserted,
                duplicates=result.duplicates,
            )
        except httpx.HTTPError as e:
            result.error = f"http_error: {e}"
            logger.warning("collector.source.http_error", api_id=source.api_id, error=str(e))
        except Exception as e:  # noqa: BLE001 — בכוונה רחב, אסור שמקור יפיל אחרים
            result.error = f"unexpected: {type(e).__name__}: {e}"
            logger.exception("collector.source.unexpected", api_id=source.api_id)

        # רישום מצב פר מקור — last_collect (בהצלחה) + failure counter (בשני המקרים).
        # ב-try נפרד כי כשל ב-state write לא צריך לסמן את המקור ככשל
        # (ה-data כבר נשמר ב-updates).
        try:
            await self._update_source_state(source, fetch_succeeded, start)
        except Exception:
            logger.exception(
                "collector.source.state_write_failed", api_id=source.api_id
            )

        finished = datetime.now(timezone.utc)
        result.duration_ms = int((finished - start).total_seconds() * 1000)
        return result

    async def _update_source_state(
        self,
        source: BaseSource,
        success: bool,
        run_started_at: datetime,
    ) -> None:
        """מעדכן state פר מקור: timestamp אחרון של הצלחה + counter כשלים רצופים.

        ה-counter מתועד אטומית עם $inc / $set (כלל 2 ב-CLAUDE.md — אין
        check-then-act). בכשל ה-3 ברצף שולחים התראה לאדמין; בכשלים
        4-9 אין רעש; הצלחה מאפסת.
        """
        failures_key = f"failures:{source.source_key}"

        if success:
            # רישום הצלחה אחרונה
            await self._db.system_state.update_one(
                {"key": f"last_collect:{source.source_key}"},
                {"$set": {"value": run_started_at, "updated_at": run_started_at}},
                upsert=True,
            )
            # איפוס counter
            await self._db.system_state.update_one(
                {"key": failures_key},
                {"$set": {"value": 0, "updated_at": run_started_at}},
                upsert=True,
            )
            return

        # כשל — מגדילים atomically ומחזירים את הערך החדש
        updated = await self._db.system_state.find_one_and_update(
            {"key": failures_key},
            {"$inc": {"value": 1}, "$set": {"updated_at": run_started_at}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        consecutive = int(updated["value"]) if updated else 1
        logger.warning(
            "collector.source.failure_count",
            api_id=source.api_id,
            source_key=source.source_key,
            consecutive=consecutive,
        )

        # התראה רק על הכשל ה-3 בדיוק — אחר כך שקט עד שמתאפס וחוזר ל-3.
        if consecutive == _ALERT_AT_CONSECUTIVE_FAILURES:
            # escape פר-ערך (כלל 6 ב-CLAUDE.md). ה-<b>...</b> סביב escape
            # נשאר כ-tag פעיל; ערך פנימי עם < או & יישלח כטקסט בטוח.
            safe_name = html.escape(source.name_he)
            safe_key = html.escape(source.source_key)
            await notify_admin(
                f"⚠️ ה-collector של <b>{safe_name}</b> "
                f"({safe_key}) נכשל {consecutive} פעמים ברצף."
            )
