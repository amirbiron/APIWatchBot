"""בדיקות לכל מקור — מוודאות parsing נכון של feed fixtures.

הגישה: יוצרים httpx.MockTransport שמחזיר את ה-XML מהקבצים.
זה מהיר ולא דורש רשת.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.collectors.sources.openai import OpenAISource
from app.collectors.sources.render import RenderSource
from app.collectors.sources.twilio import TwilioSource

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
