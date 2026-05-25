"""מקור Google Gemini — HTML scraping.

מבנה דומה ל-GBP (header + פסקאות), אבל סעיף 5.2 ב-Spec מדגיש:
"hash על רמת פריט בודד (לפי תאריך) ולא על הדף כולו, כי יש עדכונים
תוך-יומיים." לכן אנחנו מעבירים `custom_hash_input` ל-RawItem עם
ערך מבוסס תאריך הפריט — כך שהוספת שורה בתוך פריט קיים לא תייצר
פריט חדש, אבל פריט חדש (תאריך חדש) כן יזוהה.

אם תאריך לא נמצא בכותרת — נופלים ל-hash הדיפולטיבי (title+content),
שעדיין נכון אבל יוצר רעש כשהתוכן משתנה בלי שינוי משמעותי.
"""

from __future__ import annotations

from app.collectors.base import BaseSource, RawItem
from app.collectors.sources._html_utils import (
    clean_text,
    fetch_html,
    parse_html,
    parse_iso_date,
)
from app.logging_config import get_logger

logger = get_logger(__name__)

_HEADER_TAGS = {"h2", "h3"}


class GoogleGeminiSource(BaseSource):
    api_id = "google_gemini"
    name_he = "Google Gemini API"
    source_url = "https://ai.google.dev/gemini-api/docs/changelog"

    async def fetch(self) -> list[RawItem]:
        data = await fetch_html(self._http, self.source_url, self.timeout_seconds)
        parser = await parse_html(data)

        items: list[RawItem] = []
        headers = [n for n in parser.css("h2, h3") if n.tag in _HEADER_TAGS]

        for header in headers:
            title = clean_text(header)
            if not title:
                continue

            content_parts: list[str] = []
            sibling = header.next
            while sibling is not None and sibling.tag not in _HEADER_TAGS:
                text = clean_text(sibling)
                if text:
                    content_parts.append(text)
                sibling = sibling.next

            content = " ".join(content_parts).strip()
            if not content:
                continue

            # ה-trick של Gemini: hash דטרמיניסטי לפי הכותרת (שמכילה תאריך).
            # מעדכן תוך-יומי לא יוצר כפילות; פריט עם תאריך חדש כן.
            # אם אין תאריך parsable — fallback לדיפולט (None יחזיר להתנהגות
            # רגילה של title+content).
            date_in_title = parse_iso_date(title)
            custom_hash = title if date_in_title is not None else None

            items.append(
                RawItem(
                    api_id=self.api_id,
                    raw_title=title,
                    raw_content=content,
                    source_url=self.source_url,
                    source_published_at=date_in_title,
                    custom_hash_input=custom_hash,
                )
            )

        logger.debug("source.google_gemini.fetched", count=len(items))
        return items
