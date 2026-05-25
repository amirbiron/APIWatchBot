"""מקור Render — Atom feed סטנדרטי. הכי קל מבין כל המקורות."""

from __future__ import annotations

from app.collectors.base import BaseSource, RawItem
from app.collectors.sources._feed_utils import entry_to_raw_item, fetch_feed_bytes, parse_feed
from app.logging_config import get_logger

logger = get_logger(__name__)


class RenderSource(BaseSource):
    api_id = "render"
    name_he = "Render"
    source_url = "https://render.com/changelog/feed.xml"

    async def fetch(self) -> list[RawItem]:
        data = await fetch_feed_bytes(self._http, self.source_url, self.timeout_seconds)
        feed = await parse_feed(data)

        items: list[RawItem] = []
        for entry in feed.entries:
            item = entry_to_raw_item(self.api_id, entry)
            if item is not None:
                items.append(item)

        logger.debug("source.render.fetched", count=len(items))
        return items
