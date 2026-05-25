"""שולח הודעות למשתמשים דרך Bot API + rate limiting + error handling.

מבדיל מ-notify_admin בכך ש:
- שומר httpx.AsyncClient משותף (חוסך connection setup פר הודעה).
- אוכף rate limit גלובלי (Telegram: max 30 msgs/sec; אנחנו מתחת ל-25).
- מטפל בשגיאות פר-משתמש: 403 (חסם), 400 (chat לא קיים), 429 (RetryAfter).
- מחזיר תוצאה מובנית — הקורא יודע אם השליחה הצליחה.

ה-rate limit הוא ברמת ה-instance — TelegramSender יחיד לכל ה-worker.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.logging_config import get_logger

logger = get_logger(__name__)

_TELEGRAM_API_BASE = "https://api.telegram.org"
_SEND_TIMEOUT = 15.0
# מתחת ל-30/sec של Telegram כדי לשמור על הפרש בטיחות.
_MAX_MSGS_PER_SECOND = 25
_MIN_INTERVAL_SECONDS = 1.0 / _MAX_MSGS_PER_SECOND


@dataclass
class SendResult:
    success: bool
    # סטטוס מובן ל-caller: "sent" / "blocked" / "chat_not_found" / "rate_limited" / "error"
    status: str
    retry_after_seconds: float | None = None


class TelegramSender:
    """שולח הודעות לפי rate limit.

    Lifecycle: יצירה ב-worker startup, סגירה ב-shutdown (`async close()`).
    """

    def __init__(self, bot_token: str) -> None:
        self._token = bot_token
        # client אחד לכל ה-Sender — חוסך connection setup פר הודעה.
        self._client = httpx.AsyncClient(timeout=_SEND_TIMEOUT)
        # asyncio.Lock + timestamp אחרון לתיאום ה-rate limit הגלובלי.
        self._lock = asyncio.Lock()
        self._last_send_at: float = 0.0

    async def close(self) -> None:
        await self._client.aclose()

    async def send(self, chat_id: int, text: str) -> SendResult:
        """שולח HTML text ל-chat. עם rate limit + retry יחיד על 429.

        ה-text חייב להיות HTML מוכן (caller עשה escape פר-ערך).
        """
        await self._rate_limit_wait()

        result = await self._send_once(chat_id, text)
        if result.status == "rate_limited" and result.retry_after_seconds is not None:
            # 429 Too Many Requests — Telegram אומר לנו לחכות N שניות
            logger.warning(
                "sender.rate_limited",
                chat_id=chat_id,
                retry_after_s=result.retry_after_seconds,
            )
            await asyncio.sleep(result.retry_after_seconds)
            result = await self._send_once(chat_id, text)

        return result

    async def _rate_limit_wait(self) -> None:
        """לפני כל send — מוודאים שלא חורגים מקצב גלובלי של 25/sec."""
        async with self._lock:
            now = time.monotonic()
            delta = now - self._last_send_at
            if delta < _MIN_INTERVAL_SECONDS:
                wait = _MIN_INTERVAL_SECONDS - delta
                await asyncio.sleep(wait)
            self._last_send_at = time.monotonic()

    async def _send_once(self, chat_id: int, text: str) -> SendResult:
        """ניסיון יחיד. ממפה שגיאות ידועות ל-SendResult.status."""
        url = f"{_TELEGRAM_API_BASE}/bot{self._token}/sendMessage"
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        try:
            response = await self._client.post(url, json=payload)
        except httpx.HTTPError as e:
            logger.warning("sender.network_error", chat_id=chat_id, error=str(e))
            return SendResult(success=False, status="error")

        if response.status_code == 200:
            return SendResult(success=True, status="sent")

        # ניתוח שגיאות
        body = self._parse_error_body(response)
        if response.status_code == 429:
            retry_after = self._extract_retry_after(response, body)
            return SendResult(
                success=False, status="rate_limited", retry_after_seconds=retry_after
            )
        if response.status_code == 403:
            # bot blocked by user
            logger.info("sender.blocked", chat_id=chat_id, description=body.get("description"))
            return SendResult(success=False, status="blocked")
        if response.status_code == 400:
            # chat_not_found / user_deactivated וכו'
            logger.warning(
                "sender.bad_request",
                chat_id=chat_id,
                description=body.get("description"),
            )
            return SendResult(success=False, status="chat_not_found")

        # שאר ה-5xx — נחשבים שגיאה זמנית
        logger.warning(
            "sender.http_error",
            chat_id=chat_id,
            status_code=response.status_code,
            description=body.get("description"),
        )
        return SendResult(success=False, status="error")

    @staticmethod
    def _parse_error_body(response: httpx.Response) -> dict[str, Any]:
        try:
            return response.json()
        except ValueError:
            return {}

    @staticmethod
    def _extract_retry_after(response: httpx.Response, body: dict[str, Any]) -> float:
        """מנסה לחלץ retry_after משני המקומות שבהם Telegram מחזיר אותו.
        ברירת מחדל סבירה: 1 שניה."""
        # מועדף: parameters.retry_after מ-body
        params = body.get("parameters") or {}
        if "retry_after" in params:
            try:
                return float(params["retry_after"])
            except (TypeError, ValueError):
                pass
        # fallback: header
        ra = response.headers.get("Retry-After")
        if ra:
            try:
                return float(ra)
            except ValueError:
                pass
        return 1.0
