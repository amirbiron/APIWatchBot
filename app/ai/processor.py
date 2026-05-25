"""שולף raw items מ-DB, שולח ל-Gemini, ושומר את התוצאות.

מקבילי במבנה ל-CollectorRunner: run_batch מחזיר summary, לא זורק,
ורושם state ב-`system_state` (`last_ai_run`).
"""

from __future__ import annotations

import asyncio
import html
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.ai.client import GeminiAPIError, GeminiClient
from app.ai.prompt import build_prompt
from app.logging_config import get_logger
from app.utils.notify import notify_admin

logger = get_logger(__name__)

# מקסימום פריטים פר ריצה. שומרים שה-job לא יחסום את ה-scheduler.
DEFAULT_BATCH_SIZE = 50
# קונקרנציה כלפי Gemini Flash. מספיק נמוך כדי לא להתנגש ב-rate limits.
DEFAULT_CONCURRENCY = 5


@dataclass
class ItemResult:
    update_id: Any
    status: str  # "processed" | "skipped_noise" | "failed"
    error: str | None = None


@dataclass
class BatchSummary:
    started_at: datetime
    finished_at: datetime
    fetched: int = 0
    processed: int = 0
    skipped_noise: int = 0
    failed: int = 0
    results: list[ItemResult] = field(default_factory=list)


class AIProcessor:
    """עיבוד אצווה של raw items עם Gemini."""

    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        ai_client: GeminiClient,
        *,
        batch_size: int = DEFAULT_BATCH_SIZE,
        concurrency: int = DEFAULT_CONCURRENCY,
    ) -> None:
        self._db = db
        self._client = ai_client
        self._batch_size = batch_size
        self._semaphore = asyncio.Semaphore(concurrency)

    async def run_batch(self) -> BatchSummary:
        """מעבד עד `batch_size` items. **תמיד מחזיר summary — לא זורק**.

        כל מקור פוטנציאלי לחריגה (Mongo query ראשוני, gather של coroutines,
        write_state, send_alert) עטוף בנפרד. החוזה הזה קריטי כי
        APScheduler מסמן את ה-job ככשל אם המתודה זורקת, וזה עלול לעצור
        ריצות עתידיות בתלות בתצורת ה-job.
        """
        started_at = datetime.now(timezone.utc)

        # ה-query הראשוני יכול להיכשל אם Mongo זמני לא זמין. מחזירים
        # summary ריק במקום לזרוק.
        try:
            cursor = (
                self._db.updates.find({"status": "raw"})
                .sort("collected_at", 1)
                .limit(self._batch_size)
            )
            docs = await cursor.to_list(length=self._batch_size)
        except Exception:
            logger.exception("ai.run.fetch_failed")
            finished_at = datetime.now(timezone.utc)
            return BatchSummary(
                started_at=started_at, finished_at=finished_at, fetched=0
            )

        logger.info("ai.run.start", fetched=len(docs))

        if not docs:
            finished_at = datetime.now(timezone.utc)
            return BatchSummary(
                started_at=started_at, finished_at=finished_at, fetched=0
            )

        # עיבוד מקבילי. return_exceptions=True מבטיח שגם אם _process_one
        # יזרוק (באג עתידי / בעיה לא צפויה), gather לא מפיץ — מקבלים
        # exception object ברשימה ויכולים לטפל בנפרד.
        raw_results = await asyncio.gather(
            *(self._process_with_limit(doc) for doc in docs),
            return_exceptions=True,
        )

        results: list[ItemResult] = []
        for doc, raw in zip(docs, raw_results):
            if isinstance(raw, BaseException):
                # _process_one לא אמור לזרוק (יש בו try/except), אבל
                # אם בכל זאת זרק — מסמנים failed בלי להפיל את ה-batch.
                logger.exception(
                    "ai.run.process_one_raised",
                    update_id=str(doc.get("_id")),
                    error_type=type(raw).__name__,
                )
                results.append(
                    ItemResult(
                        update_id=doc.get("_id"),
                        status="failed",
                        error=f"{type(raw).__name__}: {raw}",
                    )
                )
            else:
                results.append(raw)

        finished_at = datetime.now(timezone.utc)
        summary = BatchSummary(
            started_at=started_at,
            finished_at=finished_at,
            fetched=len(docs),
            processed=sum(1 for r in results if r.status == "processed"),
            skipped_noise=sum(1 for r in results if r.status == "skipped_noise"),
            failed=sum(1 for r in results if r.status == "failed"),
            results=results,
        )

        logger.info(
            "ai.run.done",
            duration_ms=int((finished_at - started_at).total_seconds() * 1000),
            processed=summary.processed,
            skipped_noise=summary.skipped_noise,
            failed=summary.failed,
        )

        # סיכום state — _write_state כבר עטוף ב-try/except פנימי
        await self._write_state(summary)

        # התראה אחת מקובצת אם היו כשלים — notify_admin עצמה swallow-er של חריגות
        if summary.failed > 0:
            try:
                await self._send_failure_alert(summary)
            except Exception:
                logger.exception("ai.run.alert_failed")

        return summary

    async def _process_with_limit(self, doc: dict[str, Any]) -> ItemResult:
        async with self._semaphore:
            return await self._process_one(doc)

    async def _process_one(self, doc: dict[str, Any]) -> ItemResult:
        """מטפל ב-doc אחד מקצה לקצה. **אסור לזרוק** — תמיד מחזיר ItemResult.

        כל קריאת DB עטופה ב-try/except: כשל ב-mongo לא יפיל את כל ה-batch
        (asyncio.gather עם return_exceptions=False יפיץ את החריגה החוצה).
        """
        update_id = doc["_id"]
        api_id = doc.get("api_id", "")
        prompt = build_prompt(
            api_name=api_id,
            raw_title=doc.get("raw_title", ""),
            raw_content=doc.get("raw_content", ""),
            source_url=doc.get("source_url", ""),
        )

        try:
            response = await self._client.generate(prompt)
        except GeminiAPIError as e:
            await self._safe_mark_failed(update_id, str(e))
            return ItemResult(update_id=update_id, status="failed", error=str(e))
        except Exception as e:  # noqa: BLE001 — שמירה על no-throw
            logger.exception("ai.process.unexpected", update_id=str(update_id))
            error_msg = f"unexpected: {type(e).__name__}: {e}"
            await self._safe_mark_failed(update_id, error_msg)
            return ItemResult(update_id=update_id, status="failed", error=error_msg)

        # is_noise=true → skipped_noise
        if response.get("is_noise"):
            await self._safe_mark_skipped_noise(update_id)
            return ItemResult(update_id=update_id, status="skipped_noise")

        # תוצאה תקינה
        ok = await self._safe_mark_processed(update_id, response)
        if not ok:
            # DB write נכשל אבל ה-AI הצליח. מסמנים את התוצאה כ-failed כדי שיתעבד שוב
            # בריצה הבאה (status נשאר "raw" כי ה-update_one נכשל).
            return ItemResult(
                update_id=update_id,
                status="failed",
                error="db_write_failed_after_ai_success",
            )
        return ItemResult(update_id=update_id, status="processed")

    async def _safe_mark_processed(
        self, update_id: Any, response: dict[str, Any]
    ) -> bool:
        try:
            await self._db.updates.update_one(
                {"_id": update_id},
                {
                    "$set": {
                        "summary_he": response.get("summary_he", ""),
                        "severity": response.get("severity"),
                        "is_urgent": bool(response.get("is_urgent", False)),
                        "categories": list(response.get("categories", [])),
                        "status": "processed",
                        "processed_at": datetime.now(timezone.utc),
                    }
                },
            )
            return True
        except Exception:
            logger.exception(
                "ai.mark_processed.db_failed", update_id=str(update_id)
            )
            return False

    async def _safe_mark_skipped_noise(self, update_id: Any) -> None:
        try:
            await self._db.updates.update_one(
                {"_id": update_id},
                {
                    "$set": {
                        "status": "skipped_noise",
                        "processed_at": datetime.now(timezone.utc),
                    }
                },
            )
        except Exception:
            logger.exception(
                "ai.mark_skipped.db_failed", update_id=str(update_id)
            )

    async def _safe_mark_failed(self, update_id: Any, error: str) -> None:
        """שומר את הודעת השגיאה ב-`last_error` כדי שאפשר יהיה לאבחן
        כשל מ-DB בלי לחצב לוגים. ה-string מקוצר ל-500 תווים — מספיק
        לסיווג, מונע נפיחות בdocs בקצה."""
        try:
            await self._db.updates.update_one(
                {"_id": update_id},
                {
                    "$set": {
                        "status": "failed",
                        "processed_at": datetime.now(timezone.utc),
                        "last_error": error[:500],
                    }
                },
            )
        except Exception:
            logger.exception(
                "ai.mark_failed.db_failed",
                update_id=str(update_id),
                original_error=error[:200],
            )

    async def _write_state(self, summary: BatchSummary) -> None:
        try:
            await self._db.system_state.update_one(
                {"key": "last_ai_run"},
                {
                    "$set": {
                        "value": {
                            "started_at": summary.started_at,
                            "finished_at": summary.finished_at,
                            "fetched": summary.fetched,
                            "processed": summary.processed,
                            "skipped_noise": summary.skipped_noise,
                            "failed": summary.failed,
                        },
                        "updated_at": summary.finished_at,
                    }
                },
                upsert=True,
            )
        except Exception:
            logger.exception("ai.run.state_write_failed")

    async def _send_failure_alert(self, summary: BatchSummary) -> None:
        """התראה אחת מקובצת. הקורא ב-runner.py כבר עשה escape פר-ערך
        (כלל 6 ב-CLAUDE.md); כאן הטקסט הוא קבוע + מספרים בלבד, אז
        ה-escape טריוויאלי."""
        safe_failed = html.escape(str(summary.failed))
        safe_total = html.escape(str(summary.fetched))
        await notify_admin(
            f"⚠️ <b>AI Layer</b>: {safe_failed} מתוך {safe_total} פריטים "
            f"נכשלו בעיבוד ב-Gemini בריצה האחרונה."
        )
