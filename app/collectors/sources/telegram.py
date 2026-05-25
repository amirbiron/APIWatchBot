"""מקור Telegram Bot API — HTML scraping של core.telegram.org/bots/api-changelog.

מבנה ה-DOM (סעיף 5.2 ב-Spec): כל פריט מתחיל ב-`<h4>` עם תאריך, ואחריו
תוכן עד ה-`<h4>` הבא. אנחנו סורקים את ה-headers ולכל אחד אוספים את
ה-siblings עד ה-anchor הבא או סוף ה-document.
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


class TelegramSource(BaseSource):
    api_id = "telegram"
    name_he = "Telegram Bot API"
    source_url = "https://core.telegram.org/bots/api-changelog"

    async def fetch(self) -> list[RawItem]:
        data = await fetch_html(self._http, self.source_url, self.timeout_seconds)
        parser = await parse_html(data)

        items: list[RawItem] = []
        headers = parser.css("h4")

        for header in headers:
            title = clean_text(header)
            if not title:
                continue

            # אוספים את כל ה-siblings עד ה-h4 הבא
            content_parts: list[str] = []
            sibling = header.next
            while sibling is not None and sibling.tag != "h4":
                text = clean_text(sibling)
                if text:
                    content_parts.append(text)
                sibling = sibling.next

            content = " ".join(content_parts).strip()
            if not content:
                # header בלי תוכן (נדיר) — נדלג
                continue

            items.append(
                RawItem(
                    api_id=self.api_id,
                    raw_title=title,
                    raw_content=content,
                    source_url=self.source_url,
                    source_published_at=parse_iso_date(title),
                )
            )

        logger.debug("source.telegram.fetched", count=len(items))
        return items
