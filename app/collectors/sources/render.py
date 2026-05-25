"""מקור Render — Atom feed סטנדרטי. הכי קל מבין כל המקורות."""

from __future__ import annotations

from app.collectors.sources._feed_utils import BaseFeedSource


class RenderSource(BaseFeedSource):
    api_id = "render"
    name_he = "Render"
    source_url = "https://render.com/changelog/feed.xml"
