"""מקור WhatsApp — שני sub-sources עם api_id="whatsapp" משותף.

Spec §5.2: "WhatsApp + Green API — שני מקורות, אותו api_id: 'whatsapp'".
משתמש שמנוי ל-"whatsapp" יקבל פריטים משני המקורות. dedup לפי
content_hash (שכולל api_id+title+content) מבטיח שאין כפילות, כי
הכותרות והתוכן שונים בין שני האתרים.

failure tracking נפרד פר source — בזכות source_id ייחודי שמתורגם
ל-source_key ב-BaseSource.
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


class WhatsAppMetaSource(BaseSource):
    """המקור הרשמי של Meta. שביר בדיוק כמו Graph API."""

    api_id = "whatsapp"
    source_id = "whatsapp_meta"
    name_he = "WhatsApp Business (Meta)"
    source_url = (
        "https://developers.facebook.com/documentation/business-messaging/whatsapp/changelog"
    )

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

        logger.debug("source.whatsapp_meta.fetched", count=len(items))
        return items


class WhatsAppGreenSource(BaseSource):
    """ספק חלופי (MkDocs). יציב יותר מ-Meta אבל עדיין HTML scraping."""

    api_id = "whatsapp"
    source_id = "whatsapp_green"
    name_he = "Green API"
    source_url = "https://green-api.com/en/docs/release/"

    async def fetch(self) -> list[RawItem]:
        # ה-retries כאן בעיקר ל-network blips; MkDocs לא חוסם UA סטנדרטי,
        # אבל ה-API אחיד בין שני sub-sources.
        data = await fetch_html_with_retries(
            self._http,
            self.source_url,
            self.timeout_seconds,
            max_attempts=3,
            use_browser_ua=False,
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

        logger.debug("source.whatsapp_green.fetched", count=len(items))
        return items
