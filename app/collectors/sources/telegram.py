"""מקור Telegram Bot API — HTML scraping של core.telegram.org/bots/api-changelog.

מבנה ה-DOM (סעיף 5.2 ב-Spec): כל פריט מתחיל ב-`<h4>` עם תאריך, ואחריו
תוכן עד ה-`<h4>` הבא. הלוגיקה הזו מאוחסנת ב-extract_header_sections.
"""

from __future__ import annotations

from app.collectors.base import BaseSource, RawItem
from app.collectors.sources._html_utils import (
    extract_header_sections,
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
        for title, content in extract_header_sections(parser, {"h4"}):
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
