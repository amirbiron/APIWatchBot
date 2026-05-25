"""בדיקות לכל מקור — מוודאות parsing נכון של feed fixtures.

הגישה: יוצרים httpx.MockTransport שמחזיר את ה-XML מהקבצים.
זה מהיר ולא דורש רשת.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.collectors.sources.google_business import GoogleBusinessSource
from app.collectors.sources.google_gemini import GoogleGeminiSource
from app.collectors.sources.meta_graph import MetaGraphSource
from app.collectors.sources.openai import OpenAISource
from app.collectors.sources.render import RenderSource
from app.collectors.sources.stripe import StripeSource
from app.collectors.sources.telegram import TelegramSource
from app.collectors.sources.twilio import TwilioSource
from app.collectors.sources.whatsapp import WhatsAppGreenSource, WhatsAppMetaSource

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _mock_client_with_fixture(fixture_name: str) -> httpx.AsyncClient:
    """מחזיר httpx.AsyncClient שמחזיר את ה-fixture בכל request."""
    data = (FIXTURES_DIR / fixture_name).read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=data, headers={"content-type": "application/xml"})

    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(transport=transport)


@pytest.mark.asyncio
async def test_render_source_parses_feed() -> None:
    async with _mock_client_with_fixture("render_feed.xml") as client:
        source = RenderSource(client)
        items = await source.fetch()

    assert len(items) == 2
    assert items[0].api_id == "render"
    assert items[0].raw_title == "Improved deploy performance"
    assert items[0].source_url.endswith("improved-deploy-performance")
    assert items[0].source_published_at is not None


@pytest.mark.asyncio
async def test_openai_source_filters_changelog_only() -> None:
    """ה-fixture מכיל 3 entries — רק 2 הם changelog. הבלוג צריך להיסנן."""
    async with _mock_client_with_fixture("openai_feed.xml") as client:
        source = OpenAISource(client)
        items = await source.fetch()

    assert len(items) == 2  # רק 2 entries עם /api/docs/changelog
    for item in items:
        assert "/api/docs/changelog" in item.source_url
        assert item.api_id == "openai"


@pytest.mark.asyncio
async def test_twilio_source_parses_feed() -> None:
    async with _mock_client_with_fixture("twilio_feed.xml") as client:
        source = TwilioSource(client)
        items = await source.fetch()

    assert len(items) == 1
    assert items[0].api_id == "twilio"
    assert "Opus" in items[0].raw_content


@pytest.mark.asyncio
async def test_source_raises_on_http_error() -> None:
    """בקשה שמחזירה 500 חייבת לזרוק — ה-Runner יתפוס."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        source = RenderSource(client)
        with pytest.raises(httpx.HTTPStatusError):
            await source.fetch()


# ============================================================================
# Wave 2 — HTML scraping
# ============================================================================


@pytest.mark.asyncio
async def test_telegram_source_parses_html() -> None:
    """ה-fixture מכיל 3 כותרות h4 — חייבים להתקבל 3 items עם content
    מצטבר מה-siblings עד ה-h4 הבא."""
    async with _mock_client_with_fixture("telegram_changelog.html") as client:
        source = TelegramSource(client)
        items = await source.fetch()

    assert len(items) == 3
    assert items[0].api_id == "telegram"
    assert items[0].raw_title == "May 20, 2026"
    assert "setMessageReaction" in items[0].raw_content
    assert "can_send_polls" in items[0].raw_content  # סיבלינג שני נאסף
    # source_published_at נחלץ מהכותרת
    assert items[0].source_published_at is not None
    assert items[0].source_published_at.year == 2026
    assert items[0].source_published_at.month == 5


@pytest.mark.asyncio
async def test_stripe_source_parses_table() -> None:
    """ה-fixture מכיל 3 שורות נתונים + שורת header. רק 3 הראשונות מתקבלות."""
    async with _mock_client_with_fixture("stripe_changelog.html") as client:
        source = StripeSource(client)
        items = await source.fetch()

    assert len(items) == 3
    assert items[0].api_id == "stripe"
    assert "trial_will_end" in items[0].raw_content
    assert items[0].source_published_at is not None
    assert items[0].source_published_at.day == 20

    # שורת ה-th לא נכנסה
    assert all("Description" not in i.raw_content for i in items)


@pytest.mark.asyncio
async def test_google_business_parses_items() -> None:
    """3 כותרות h2 → 3 items. ה-h1 הראשי לא נחשב כפריט."""
    async with _mock_client_with_fixture("google_business_changelog.html") as client:
        source = GoogleBusinessSource(client)
        items = await source.fetch()

    assert len(items) == 3
    assert items[0].api_id == "google_business"
    assert items[0].raw_title == "May 20, 2026"
    assert "service area" in items[0].raw_content


@pytest.mark.asyncio
async def test_google_gemini_uses_custom_hash_by_date() -> None:
    """קריטי לסעיף 5.2 ב-Spec: שינוי בתוכן של פריט עם אותו תאריך לא
    יוצר פריט חדש (אין רעש מעדכונים תוך-יומיים), אבל פריט עם תאריך
    חדש כן יזוהה כחדש."""
    async with _mock_client_with_fixture("google_gemini_changelog.html") as client:
        source = GoogleGeminiSource(client)
        items_run1 = await source.fetch()

    assert len(items_run1) == 3
    assert items_run1[0].api_id == "google_gemini"

    # שני items נפרדים עם אותו תאריך אבל תוכן שונה — חייבים להיות אותו hash
    from app.collectors.base import RawItem

    base = RawItem(
        api_id="google_gemini",
        raw_title="May 20, 2026",
        raw_content="original text",
        source_url="https://x",
        custom_hash_input="May 20, 2026",
    )
    after_edit = RawItem(
        api_id="google_gemini",
        raw_title="May 20, 2026",
        raw_content="updated text with more details",
        source_url="https://x",
        custom_hash_input="May 20, 2026",
    )
    assert base.content_hash == after_edit.content_hash

    # פריט עם תאריך אחר — hash שונה
    different_date = RawItem(
        api_id="google_gemini",
        raw_title="May 21, 2026",
        raw_content="original text",
        source_url="https://x",
        custom_hash_input="May 21, 2026",
    )
    assert different_date.content_hash != base.content_hash


@pytest.mark.asyncio
async def test_html_source_handles_empty_page() -> None:
    """דף ריק/בלי headers — לא זורק, מחזיר רשימה ריקה."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html><body><p>nothing</p></body></html>")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        items = await TelegramSource(client).fetch()
    assert items == []


# ============================================================================
# Wave 3 — Fragile HTML scraping (retries + admin alert)
# ============================================================================


@pytest.mark.asyncio
async def test_meta_graph_parses_html() -> None:
    async with _mock_client_with_fixture("meta_graph_changelog.html") as client:
        source = MetaGraphSource(client)
        items = await source.fetch()

    assert len(items) == 3
    assert items[0].api_id == "meta_graph"
    assert "v23.0" in items[0].raw_content
    assert items[1].source_published_at is not None


@pytest.mark.asyncio
async def test_whatsapp_meta_parses_html() -> None:
    async with _mock_client_with_fixture("whatsapp_meta_changelog.html") as client:
        source = WhatsAppMetaSource(client)
        items = await source.fetch()

    assert len(items) == 2
    # api_id משותף עם Green API לצורך subscription matching
    assert items[0].api_id == "whatsapp"
    # source_key נפרד לצורך failure tracking
    assert source.source_key == "whatsapp_meta"


@pytest.mark.asyncio
async def test_whatsapp_green_parses_html() -> None:
    async with _mock_client_with_fixture("whatsapp_green_changelog.html") as client:
        source = WhatsAppGreenSource(client)
        items = await source.fetch()

    assert len(items) == 3
    assert items[0].api_id == "whatsapp"
    assert source.source_key == "whatsapp_green"
    # api_id משותף עם Meta אבל hash שונה בזכות תוכן שונה
    assert items[0].content_hash != ""


def test_source_key_defaults_to_api_id() -> None:
    """ל-source בלי source_id מוגדר — source_key=api_id (תאימות לאחור)."""
    from app.collectors.sources.render import RenderSource

    # יוצרים instance בלי client אמיתי — לא קוראים ל-fetch
    source = RenderSource.__new__(RenderSource)
    assert source.source_key == "render"


def test_whatsapp_sources_share_api_id_but_distinct_keys() -> None:
    """וידוא: api_id משותף לצורך subscription, source_key שונה לצורך state."""
    meta = WhatsAppMetaSource.__new__(WhatsAppMetaSource)
    green = WhatsAppGreenSource.__new__(WhatsAppGreenSource)
    assert meta.api_id == green.api_id == "whatsapp"
    assert meta.source_key != green.source_key
