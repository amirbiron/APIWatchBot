"""כלי עזר משותפים לכל מקורות ה-HTML scraping (selectolax).

הדפוס מקביל ל-`_feed_utils.py`: fetch → parse → extract.
selectolax (lexbor backend) מהיר מאוד ולא חוסם, אבל ה-wrappers
האסינכרוניים שומרים על אחידות API עם feed sources.
"""

from __future__ import annotations

import asyncio
import re

import httpx
from selectolax.parser import HTMLParser, Node

from app.logging_config import get_logger

logger = get_logger(__name__)

# רצף תווי whitespace (כולל nbsp, tabs, ירידות שורה) לקיפול לרווח יחיד.
_WHITESPACE_RE = re.compile(r"[\s ]+")


# UA של Chrome אמיתי — לאתרי Meta (Spec §5.2 "User-Agent מסווה").
# לא משקרים שהבוט הוא משתמש, אבל כן עוקפים סינון פשטני של "lib/" agents.
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


async def fetch_html(http: httpx.AsyncClient, url: str, timeout: float) -> bytes:
    """משיכת HTML גולמי. raise_for_status כדי שכשלים יעלו ל-Runner שיטפל בלוג."""
    response = await http.get(url, timeout=timeout)
    response.raise_for_status()
    return response.content


async def fetch_html_with_retries(
    http: httpx.AsyncClient,
    url: str,
    timeout: float,
    *,
    max_attempts: int = 3,
    use_browser_ua: bool = True,
    backoff_base: float = 2.0,
) -> bytes:
    """גרסה עם exponential backoff למקורות שביריים (Meta, WhatsApp).

    Spec §5.2: "retries + User-Agent מסווה" עבור Meta וWhatsApp.
    backoff פנימי של 2 ו-4 שניות בין נסיונות; בכשל סופי מעלה את
    החריגה המקורית כך ש-CollectorRunner._run_one יטפל בה כרגיל.

    `backoff_base` בעיקר לבדיקות — אפשר להעביר 0 כדי להמנע מהמתנה.
    """
    headers = {"User-Agent": _BROWSER_UA} if use_browser_ua else None
    last_exc: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            response = await http.get(url, timeout=timeout, headers=headers)
            response.raise_for_status()
            return response.content
        except (httpx.HTTPError, httpx.TimeoutException) as e:
            last_exc = e
            if attempt < max_attempts:
                wait_s = backoff_base**attempt
                logger.warning(
                    "fetch.retry",
                    url=url,
                    attempt=attempt,
                    wait_s=wait_s,
                    error=type(e).__name__,
                )
                if wait_s > 0:
                    await asyncio.sleep(wait_s)

    assert last_exc is not None
    raise last_exc


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


# זיהוי גס של "האם המחרוזת מכילה תאריך" — לא פרסור! משמש רק להחלטת
# dedup (custom_hash) ב-google_gemini: כותרת שמכילה תאריך היא מפתח יציב
# לפריט. שם חודש באנגלית או שנה בת 4 ספרות מספיקים. חילוץ התאריך עצמו
# עבר לאחריות Gemini בשלב העיבוד (כלל קדימות ב-AIProcessor).
_MONTH_NAME_RE = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b",
    re.IGNORECASE,
)
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def looks_like_date(value: str | None) -> bool:
    """True אם המחרוזת נראית כמו תאריך (שם חודש או שנה). לא מפרסר."""
    if not value:
        return False
    return bool(_YEAR_RE.search(value) or _MONTH_NAME_RE.search(value))


def extract_header_sections(
    parser: HTMLParser,
    header_tags: set[str],
) -> list[tuple[str, str]]:
    """מחלץ סקציות "header + תוכן עד ה-header הבא" מ-DOM.

    דפוס חוזר באתרי changelog: כותרת (h2/h3/h4) מסמנת תחילת פריט,
    והתוכן הוא כל ה-siblings עד הכותרת הבאה (באותה רמה / קבוצת tags).

    מחזיר רשימה של (title, content), מסונן מ-headers ריקות וסקציות
    ללא תוכן. הסדר נשמר לפי סדר ה-DOM.
    """
    if not header_tags:
        return []
    selector = ", ".join(sorted(header_tags))
    headers = [n for n in parser.css(selector) if n.tag in header_tags]

    sections: list[tuple[str, str]] = []
    for header in headers:
        title = clean_text(header)
        if not title:
            continue

        content_parts: list[str] = []
        sibling = header.next
        while sibling is not None and sibling.tag not in header_tags:
            text = clean_text(sibling)
            if text:
                content_parts.append(text)
            sibling = sibling.next

        content = " ".join(content_parts).strip()
        if not content:
            continue

        sections.append((title, content))

    return sections
