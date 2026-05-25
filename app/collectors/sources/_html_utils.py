"""כלי עזר משותפים לכל מקורות ה-HTML scraping (selectolax).

הדפוס מקביל ל-`_feed_utils.py`: fetch → parse → extract.
selectolax (lexbor backend) מהיר מאוד ולא חוסם, אבל ה-wrappers
האסינכרוניים שומרים על אחידות API עם feed sources.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import httpx
from selectolax.parser import HTMLParser, Node

from app.logging_config import get_logger

logger = get_logger(__name__)

# רצף תווי whitespace (כולל nbsp, tabs, ירידות שורה) לקיפול לרווח יחיד.
_WHITESPACE_RE = re.compile(r"[\s ]+")


async def fetch_html(http: httpx.AsyncClient, url: str, timeout: float) -> bytes:
    """משיכת HTML גולמי. raise_for_status כדי שכשלים יעלו ל-Runner שיטפל בלוג."""
    response = await http.get(url, timeout=timeout)
    response.raise_for_status()
    return response.content


async def parse_html(data: bytes) -> HTMLParser:
    """wrapper סינכרוני (selectolax מהיר מספיק שלא נחסום event loop)."""
    return HTMLParser(data)


def clean_text(value: Node | str | None) -> str:
    """מקבל Node של selectolax או מחרוזת, מחזיר טקסט מנורמל.

    - אם None: מחזיר "".
    - מקפל רצפי whitespace לרווח יחיד (כולל nbsp, שמופיע הרבה ב-MkDocs/Stripe).
    - חותך רווחים בקצוות.
    """
    if value is None:
        return ""
    text = value.text(separator=" ") if isinstance(value, Node) else str(value)
    return _WHITESPACE_RE.sub(" ", text).strip()


# פורמטים נפוצים שמופיעים באתרי changelog של Telegram/Stripe/Google.
# סדר חשוב — מנסים מהמדויק לפחות-מדויק.
_DATE_FORMATS = (
    "%Y-%m-%d",
    "%B %d, %Y",   # "May 20, 2026"
    "%b %d, %Y",   # "May 20, 2026" (Stripe לפעמים מקצר)
    "%d %B %Y",    # "20 May 2026"
    "%d %b %Y",
    "%Y/%m/%d",
)


def parse_iso_date(value: str | None) -> datetime | None:
    """מנסה לפרסר תאריך לפי פורמטים נפוצים. מחזיר tz-aware UTC או None.

    מועדף לא לזרוק כשהפורמט לא מזוהה — פריט בלי source_published_at
    עדיין שמיש (לא חוסם dedup ולא חוסם AI).
    """
    if not value:
        return None
    s = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    logger.debug("html_utils.date_parse_failed", value=s)
    return None
