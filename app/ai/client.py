"""wrapper דק סביב google-genai עם retry יחיד.

מבודד את ה-SDK מהשאר; processor.py מתעסק רק עם dict-ים, לא עם types
של Gemini. גם מאפשר mocking נוח בבדיקות.
"""

from __future__ import annotations

import json
from typing import Any

from google import genai
from google.genai import types

from app.ai.prompt import RESPONSE_SCHEMA
from app.logging_config import get_logger

logger = get_logger(__name__)

# מודל ברירת מחדל (Spec §1.4). חשיפת ה-class var כדי שטסטים יוכלו לדרוס.
DEFAULT_MODEL = "gemini-2.5-flash"


class GeminiAPIError(Exception):
    """כשל בקריאה ל-Gemini אחרי כל הnsנסיונות. ה-processor יסמן status='failed'."""


class GeminiClient:
    """מבצע generate_content עם structured output ו-retry יחיד.

    Spec §6.3: "אם ה-AI מחזיר JSON לא תקין: ניסיון חוזר אחד, ואז status: failed."
    structured output (response_schema) כמעט מבטל את הסיכוי ל-JSON לא תקין;
    ה-retry כאן בעיקר נגד API errors זמניים (rate limit, timeout, 5xx).
    """

    def __init__(
        self,
        api_key: str,
        *,
        model: str = DEFAULT_MODEL,
        max_attempts: int = 2,
    ) -> None:
        # נשמרים על client יחיד למשך חיי ה-processor — חוסך connection setup.
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._max_attempts = max_attempts

    async def generate(self, prompt: str) -> dict[str, Any]:
        """מחזיר dict לפי RESPONSE_SCHEMA. זורק GeminiAPIError אחרי retry."""
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=RESPONSE_SCHEMA,
            # ערכי ברירת מחדל סבירים — אפשר לכוון אם נראה איכות ירודה.
            temperature=0.3,
        )

        last_exc: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                response = await self._client.aio.models.generate_content(
                    model=self._model,
                    contents=prompt,
                    config=config,
                )
                return self._parse_response(response)
            except Exception as e:  # noqa: BLE001 — SDK עלול לזרוק טיפוסים שונים
                last_exc = e
                logger.warning(
                    "ai.client.attempt_failed",
                    attempt=attempt,
                    error=type(e).__name__,
                    message=str(e)[:200],
                )

        raise GeminiAPIError(
            f"Gemini failed after {self._max_attempts} attempts: {last_exc}"
        ) from last_exc

    def _parse_response(self, response: Any) -> dict[str, Any]:
        """מוציא את ה-dict מתוך ה-response של ה-SDK.

        עם structured output, response.text הוא JSON תקין. מנתחים ידנית
        ולא מסתמכים על response.parsed כי הוא לא תמיד מאוכלס בגרסאות
        מסוימות של ה-SDK.
        """
        text = (response.text or "").strip()
        if not text:
            raise GeminiAPIError("empty response from Gemini")

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            # במציאות עם response_schema זה לא צריך לקרות, אבל מגנים.
            raise GeminiAPIError(f"invalid JSON: {e}") from e

        if not isinstance(data, dict):
            raise GeminiAPIError(f"expected dict, got {type(data).__name__}")

        return data
