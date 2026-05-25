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
