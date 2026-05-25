"""מקור Google Business Profile — HTML scraping.

מבנה ה-DOM (סעיף 5.2 ב-Spec): דף קצר יחסית, כל פריט הוא header
(`<h2>` או `<h3>`) ואחריו פסקאות. שימוש ב-extract_header_sections
המשותף — לוגיקה זהה ל-Gemini, רק בלי custom_hash.
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

_HEADER_TAGS = {"h2", "h3"}


class GoogleBusinessSource(BaseSource):
    api_id = "google_business"
    name_he = "Google Business Profile"
    source_url = "https://developers.google.com/my-business/content/change-log"

    async def fetch(self) -> list[RawItem]:
        data = await fetch_html(self._http, self.source_url, self.timeout_seconds)
        parser = await parse_html(data)

        items: list[RawItem] = []
        for title, content in extract_header_sections(parser, _HEADER_TAGS):
            items.append(
                RawItem(
                    api_id=self.api_id,
                    raw_title=title,
                    raw_content=content,
                    source_url=self.source_url,
                    source_published_at=parse_iso_date(title),
                )
            )

        logger.debug("source.google_business.fetched", count=len(items))
        return items
