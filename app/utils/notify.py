"""שליחת התראות אדמין דרך Bot API ישירות.

הסיבה להימנע מ-PTB Application: ה-worker רץ כprocess נפרד מ-FastAPI,
ויצירת Application שני באותו bot תתנגש עם ה-webhook (כפילות).
שימוש ישיר ב-Bot API נקי, חסר state, ו-fire-and-forget.

כלל 6 ב-CLAUDE.md (escape): אחריות ה-caller להעביר message שהוא
HTML-safe. אם הקורא מטמיע ערך משתמש או DB, עליו לקרוא ל-html.escape
על *הערך המוטמע*, לא על המחרוזת השלמה — אחרת tags כמו <b> שכוונו
לעיצוב יומרו ל-&lt;b&gt; ויוצגו כטקסט.
"""

from __future__ import annotations

import httpx

from app.config import get_settings
from app.logging_config import get_logger

logger = get_logger(__name__)

_TELEGRAM_API_BASE = "https://api.telegram.org"
_NOTIFY_TIMEOUT = 10.0


async def notify_admin(message: str) -> None:
    """שולח הודעת HTML ל-ADMIN_TELEGRAM_ID. fire-and-forget.

    אם הקונפיג חסר (admin_id או token) — לוג בלבד, לא שגיאה.
    אם ה-API נכשל — לוג בלבד; אסור שכשל בהתראה יפיל את הקורא
    (collector שאחראי על מילוי מאגר הנתונים).

    `message` חייב להיות HTML תקין מבחינת Telegram. ערכים מוטמעים
    (שמות מקורות, הודעות שגיאה) חייבים להיות מוגנים ע"י html.escape
    *לפני* ההטמעה.
    """
    settings = get_settings()
    if not settings.admin_notify_configured:
        logger.warning(
            "notify_admin.skipped",
            reason="admin_telegram_id או TELEGRAM_BOT_TOKEN חסרים",
        )
        return

    token = settings.telegram_bot_token.get_secret_value()
    url = f"{_TELEGRAM_API_BASE}/bot{token}/sendMessage"

    payload = {
        "chat_id": settings.admin_telegram_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        async with httpx.AsyncClient(timeout=_NOTIFY_TIMEOUT) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
        logger.info("notify_admin.sent", message_len=len(message))
    except Exception:
        # אסור לזרוק — ה-collector תלוי באמינות שלנו
        logger.exception("notify_admin.failed")
