"""מקור OpenAI — RSS משולב (גם בלוגים וגם changelog).

לפי סעיף 5.2 ב-Spec: סינון URL — רק פריטים שמכילים `/api/docs/changelog`.
"""

from __future__ import annotations

from app.collectors.sources._feed_utils import BaseFeedSource


class OpenAISource(BaseFeedSource):
    api_id = "openai"
    name_he = "OpenAI"
    source_url = "https://developers.openai.com/rss.xml"

    # התוכן ב-RSS של OpenAI מכיל גם announcements ובלוגים לא רלוונטיים.
    url_filter = "/api/docs/changelog"
