"""כלי עזר ומחלקת בסיס משותפים לכל המקורות מבוססי RSS/Atom (feedparser)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from time import struct_time
from typing import Any, ClassVar

import feedparser
import httpx

from app.collectors.base import BaseSource, RawItem
from app.logging_config import get_logger

logger = get_logger(__name__)


async def fetch_feed_bytes(http: httpx.AsyncClient, url: str, timeout: float) -> bytes:
    """משיכת הזנת RSS/Atom גולמית. zorek raise_for_status כדי שכשלים יעלו ל-Runner."""
    response = await http.get(url, timeout=timeout)
    response.raise_for_status()
    return response.content


async def parse_feed(data: bytes) -> Any:
    """feedparser הוא sync וכבד יחסית — מריצים ב-thread כדי לא לחסום event loop."""
    return await asyncio.to_thread(feedparser.parse, data)


def struct_time_to_datetime(t: struct_time | None) -> datetime | None:
    """ממיר את שדה published_parsed של feedparser ל-datetime UTC."""
    if t is None:
        return None
    try:
        # feedparser מחזיר תמיד UTC ב-published_parsed
        return datetime(*t[:6], tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def entry_to_raw_item(
    api_id: str,
    entry: Any,
    *,
    url_filter: str | None = None,
) -> RawItem | None:
    """ממיר entry של feedparser ל-RawItem. מחזיר None אם הפריט לא תקין.

    `url_filter`: אם סופק, רק entries שה-link שלהם מכיל את הסטרינג יעברו.
    שימוש: OpenAI מפרסם באותה הזנה גם blogs וגם changelog — נסנן רק changelog.
    """
    title = (entry.get("title") or "").strip()
    link = (entry.get("link") or "").strip()

    if not title or not link:
        return None

    if url_filter is not None and url_filter not in link:
        return None

    # תוכן יכול להגיע ב-summary, description, או content[0].value
    content = (
        entry.get("summary")
        or entry.get("description")
        or (entry.get("content", [{}])[0].get("value") if entry.get("content") else "")
        or ""
    ).strip()

    published = struct_time_to_datetime(entry.get("published_parsed")) or struct_time_to_datetime(
        entry.get("updated_parsed")
    )

    return RawItem(
        api_id=api_id,
        raw_title=title,
        raw_content=content,
        source_url=link,
        source_published_at=published,
    )


class BaseFeedSource(BaseSource):
    """מחלקת בסיס למקורות RSS/Atom.

    תת-מחלקה צריכה להגדיר רק את ה-class vars (api_id, name_he, source_url),
    ואופציונלית `url_filter` לסינון לפי URL של ה-entry (לדוגמה OpenAI
    שמשתף RSS עם blog ו-changelog ורק changelog רלוונטי).

    אין צורך לעקוף את `fetch()` — הדפוס זהה לכל ה-feeds.
    """

    # אם מוגדר, רק entries שה-link שלהם מכיל את הסטרינג ייכללו.
    url_filter: ClassVar[str | None] = None

    async def fetch(self) -> list[RawItem]:
        data = await fetch_feed_bytes(self._http, self.source_url, self.timeout_seconds)
        feed = await parse_feed(data)

        items: list[RawItem] = []
        for entry in feed.entries:
            item = entry_to_raw_item(self.api_id, entry, url_filter=self.url_filter)
            if item is not None:
                items.append(item)

        logger.debug(
            "source.feed.fetched",
            api_id=self.api_id,
            count=len(items),
            total=len(feed.entries),
        )
        return items
