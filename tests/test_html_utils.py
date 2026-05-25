"""בדיקות ל-app/collectors/sources/_html_utils.py."""

from __future__ import annotations

import pytest
from selectolax.parser import HTMLParser

from app.collectors.sources._html_utils import (
    clean_text,
    parse_html,
    parse_iso_date,
)


def test_clean_text_handles_none() -> None:
    assert clean_text(None) == ""


def test_clean_text_normalizes_whitespace() -> None:
    parser = HTMLParser("<p>hello\n\t  world !</p>")
    node = parser.css_first("p")
    # nbsp + tabs + newlines הופכים לרווח יחיד; קצוות נחתכים
    assert clean_text(node) == "hello world !"


def test_clean_text_accepts_string() -> None:
    assert clean_text("  raw   text\n") == "raw text"


def test_parse_iso_date_recognizes_common_formats() -> None:
    assert parse_iso_date("2026-05-20") is not None
    assert parse_iso_date("May 20, 2026") is not None
    assert parse_iso_date("20 May 2026") is not None


def test_parse_iso_date_returns_utc_aware() -> None:
    result = parse_iso_date("2026-05-20")
    assert result is not None
    assert result.tzinfo is not None


def test_parse_iso_date_returns_none_for_garbage() -> None:
    """לא זורק על קלט לא מזוהה — מחזיר None."""
    assert parse_iso_date("yesterday") is None
    assert parse_iso_date("") is None
    assert parse_iso_date(None) is None


@pytest.mark.asyncio
async def test_parse_html_returns_parser() -> None:
    parser = await parse_html(b"<html><body><h1>hi</h1></body></html>")
    assert parser.css_first("h1").text() == "hi"


def test_extract_header_sections_basic() -> None:
    from app.collectors.sources._html_utils import extract_header_sections

    html = b"""
    <html><body>
    <h2>A</h2><p>a1</p><p>a2</p>
    <h2>B</h2><p>b1</p>
    <h2>C</h2><p>c1</p>
    </body></html>
    """
    parser = HTMLParser(html)
    sections = extract_header_sections(parser, {"h2"})

    assert len(sections) == 3
    assert sections[0] == ("A", "a1 a2")
    assert sections[1] == ("B", "b1")
    assert sections[2] == ("C", "c1")


def test_extract_header_sections_stops_at_any_header_in_set() -> None:
    """h2 ו-h3 שניהם פותחים סקציה — אוסף לא חוצה גבול ביניהם."""
    from app.collectors.sources._html_utils import extract_header_sections

    html = b"<html><body><h2>A</h2><p>a</p><h3>B</h3><p>b</p></body></html>"
    parser = HTMLParser(html)
    sections = extract_header_sections(parser, {"h2", "h3"})

    assert sections == [("A", "a"), ("B", "b")]


def test_extract_header_sections_skips_empty() -> None:
    """header בלי תוכן אחריו — לא נכנס לתוצאה."""
    from app.collectors.sources._html_utils import extract_header_sections

    html = b"<html><body><h2>Empty</h2><h2>With content</h2><p>x</p></body></html>"
    parser = HTMLParser(html)
    sections = extract_header_sections(parser, {"h2"})

    assert sections == [("With content", "x")]


def test_extract_header_sections_empty_tags_set() -> None:
    from app.collectors.sources._html_utils import extract_header_sections

    parser = HTMLParser(b"<h2>X</h2>")
    assert extract_header_sections(parser, set()) == []


# ============================================================================
# fetch_html_with_retries
# ============================================================================


@pytest.mark.asyncio
async def test_fetch_html_with_retries_succeeds_after_failures() -> None:
    """2 כשלים ראשונים → ניסיון שלישי מצליח → מחזיר תוכן."""
    import httpx

    from app.collectors.sources._html_utils import fetch_html_with_retries

    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] < 3:
            return httpx.Response(503, text="server busy")
        return httpx.Response(200, content=b"<html>ok</html>")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        data = await fetch_html_with_retries(
            client,
            "https://example.invalid/x",
            timeout=5,
            backoff_base=0,  # בלי המתנה בטסט
        )

    assert data == b"<html>ok</html>"
    assert attempts["count"] == 3


@pytest.mark.asyncio
async def test_fetch_html_with_retries_raises_after_max_attempts() -> None:
    """3 כשלים רצופים → מעלה את החריגה המקורית."""
    import httpx

    from app.collectors.sources._html_utils import fetch_html_with_retries

    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(500, text="boom")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await fetch_html_with_retries(
                client,
                "https://example.invalid/x",
                timeout=5,
                backoff_base=0,
            )

    assert attempts["count"] == 3


@pytest.mark.asyncio
async def test_fetch_html_with_retries_sends_browser_ua() -> None:
    """ההגנה היחידה שיש לנו מול Meta — וידוא ש-UA אמיתי נשלח."""
    import httpx

    from app.collectors.sources._html_utils import fetch_html_with_retries

    captured_uas: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_uas.append(request.headers.get("User-Agent", ""))
        return httpx.Response(200, content=b"<html></html>")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        await fetch_html_with_retries(
            client,
            "https://example.invalid/x",
            timeout=5,
            use_browser_ua=True,
            backoff_base=0,
        )

    assert "Chrome" in captured_uas[0]
    assert "Mozilla" in captured_uas[0]
