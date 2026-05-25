"""מקור Meta Graph API — HTML scraping שביר.

Spec §5.2: "httpx.get + retries + User-Agent מסווה. חוסר יציבות גבוה —
להוסיף fallback: אם נכשל 3 פעמים ברצף, לשלוח התראה לאדמין."

ה-retries וה-UA מסופקים ע"י fetch_html_with_retries; ה-alert ע"י
CollectorRunner._update_source_state (failures counter פר source_key).
"""

from __future__ import annotations

from app.collectors.base import BaseSource, RawItem
from app.collectors.sources._html_utils import (
    extract_header_sections,
    fetch_html_with_retries,
    parse_html,
    parse_iso_date,
)
from app.logging_config import get_logger

logger = get_logger(__name__)

_HEADER_TAGS = {"h2", "h3"}


class MetaGraphSource(BaseSource):
    api_id = "meta_graph"
    name_he = "Meta Graph API"
    source_url = "https://developers.facebook.com/docs/graph-api/changelog/"

    async def fetch(self) -> list[RawItem]:
        data = await fetch_html_with_retries(
            self._http,
            self.source_url,
            self.timeout_seconds,
            max_attempts=3,
            use_browser_ua=True,
        )
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

        logger.debug("source.meta_graph.fetched", count=len(items))
        return items
