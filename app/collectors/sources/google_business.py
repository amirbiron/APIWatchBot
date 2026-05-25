"""מקור Google Business Profile — HTML scraping.

מבנה ה-DOM (סעיף 5.2 ב-Spec): דף קצר יחסית, כל פריט הוא header
(`<h2>` או `<h3>`) ואחריו פסקאות. אנחנו אוספים את הסיבלינגס עד ה-header
הבא ברמה זהה.
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

# H2 הוא הרמה הסבירה ל"פריט changelog" באתרי Google Developers.
# אם המבנה השתנה לטובת h3, מספיק להוסיף "h3" לטופל הסלקטור.
_HEADER_TAGS = {"h2", "h3"}


class GoogleBusinessSource(BaseSource):
    api_id = "google_business"
    name_he = "Google Business Profile"
    source_url = "https://developers.google.com/my-business/content/change-log"

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
