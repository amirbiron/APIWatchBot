"""מקור Google Gemini — HTML scraping.

מבנה דומה ל-GBP אבל סעיף 5.2 ב-Spec מדגיש:
"hash על רמת פריט בודד (לפי תאריך) ולא על הדף כולו, כי יש עדכונים
תוך-יומיים." לכן אנחנו מעבירים `custom_hash_input` ל-RawItem עם
ערך מבוסס תאריך הפריט — כך שהוספת שורה בתוך פריט קיים לא תייצר
פריט חדש, אבל פריט חדש (תאריך חדש) כן יזוהה.

אם תאריך לא נמצא בכותרת — נופלים ל-hash הדיפולטיבי (title+content).
"""

from __future__ import annotations

from app.collectors.base import BaseSource, RawItem
from app.collectors.sources._html_utils import (
    extract_header_sections,
    fetch_html,
    looks_like_date,
    parse_html,
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
        for title, content in extract_header_sections(parser, _HEADER_TAGS):
            # ה-trick של Gemini: hash דטרמיניסטי לפי הכותרת (שמכילה תאריך).
            # מעדכן תוך-יומי לא יוצר כפילות; פריט עם תאריך חדש כן.
            # אם הכותרת לא נראית כמו תאריך — fallback לדיפולט (None יחזיר
            # להתנהגות רגילה של title+content).
            # חילוץ התאריך עצמו ל-source_published_at עבר ל-Gemini בשלב
            # העיבוד — כאן רק מחליטים על מפתח ה-dedup.
            custom_hash = title if looks_like_date(title) else None

            items.append(
                RawItem(
                    api_id=self.api_id,
                    raw_title=title,
                    raw_content=content,
                    source_url=self.source_url,
                    custom_hash_input=custom_hash,
                )
            )

        logger.debug("source.google_gemini.fetched", count=len(items))
        return items
