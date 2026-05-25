"""מקור OpenAI — RSS משולב (גם בלוגים וגם changelog).

לפי סעיף 5.2 ב-Spec: סינון URL — רק פריטים שמכילים `/api/docs/changelog`.
"""

from __future__ import annotations

from app.collectors.base import BaseSource, RawItem
from app.collectors.sources._feed_utils import entry_to_raw_item, fetch_feed_bytes, parse_feed
from app.logging_config import get_logger

logger = get_logger(__name__)


class OpenAISource(BaseSource):
    api_id = "openai"
    name_he = "OpenAI"
    source_url = "https://developers.openai.com/rss.xml"

    # רק entries שה-link שלהם מכיל את הסטרינג הזה ייכללו.
    # התוכן ב-RSS של OpenAI מכיל גם announcements לא רלוונטיים.
    _URL_FILTER = "/api/docs/changelog"

    async def fetch(self) -> list[RawItem]:
        data = await fetch_feed_bytes(self._http, self.source_url, self.timeout_seconds)
        feed = await parse_feed(data)

        items: list[RawItem] = []
        for entry in feed.entries:
            item = entry_to_raw_item(self.api_id, entry, url_filter=self._URL_FILTER)
            if item is not None:
                items.append(item)

        logger.debug("source.openai.fetched", count=len(items), total=len(feed.entries))
        return items
