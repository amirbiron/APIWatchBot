"""בדיקות ל-app/dispatcher/formatter.py."""

from __future__ import annotations

from datetime import datetime, timezone

from app.dispatcher.formatter import (
    MAX_TELEGRAM_MESSAGE_LEN,
    build_urgent_message,
    build_weekly_digest,
    format_date_range,
    split_long_message,
)


def _make_update(api_id="render", summary="עדכון x", severity="info", url="https://x"):
    return {
        "api_id": api_id,
        "summary_he": summary,
        "severity": severity,
        "source_url": url,
    }


def test_urgent_message_includes_summary_and_link() -> None:
    msg = build_urgent_message(
        _make_update(api_id="render", summary="התראה", url="https://render.com")
    )
    assert "התראה דחופה" in msg
    assert "Render" in msg  # שם תצוגה מ-SUBSCRIBABLE_APIS_BY_ID
    assert "התראה" in msg
    assert 'href="https://render.com"' in msg


def test_urgent_message_escapes_user_content() -> None:
    msg = build_urgent_message(
        _make_update(summary="<script>alert(1)</script>")
    )
    assert "<script>" not in msg
    assert "&lt;script&gt;" in msg


def test_weekly_digest_returns_none_for_empty() -> None:
    assert build_weekly_digest([], date_range="24-30 במאי") is None


def test_weekly_digest_groups_by_severity_in_order() -> None:
    updates = [
        _make_update(api_id="render", summary="i1", severity="info"),
        _make_update(api_id="openai", summary="c1", severity="critical"),
        _make_update(api_id="stripe", summary="im1", severity="important"),
    ]
    msg = build_weekly_digest(updates, date_range="24-30 במאי")

    assert msg is not None
    # סדר הקטגוריות: critical → important → info
    idx_critical = msg.index("קריטי")
    idx_important = msg.index("חשוב")
    idx_info = msg.index("מידע")
    assert idx_critical < idx_important < idx_info


def test_weekly_digest_skips_empty_sections() -> None:
    """אם אין critical, אסור שתהיה סקציית 'קריטי' ריקה."""
    msg = build_weekly_digest(
        [_make_update(severity="info", summary="x")],
        date_range="24-30 במאי",
    )
    assert msg is not None
    assert "מידע" in msg
    assert "קריטי" not in msg
    assert "חשוב" not in msg


def test_weekly_digest_escapes_summary() -> None:
    msg = build_weekly_digest(
        [_make_update(summary="A & B < C")],
        date_range="24-30 במאי",
    )
    assert msg is not None
    assert "&amp;" in msg
    assert "&lt;" in msg


def test_split_long_message_short_passes_through() -> None:
    assert split_long_message("hello") == ["hello"]


def test_split_long_message_splits_at_double_newline() -> None:
    """החיתוך מעדיף גבולות שורה כפולה (סקציות)."""
    big = ("a" * 100 + "\n\n" + "b" * 100 + "\n\n" + "c" * 100)
    chunks = split_long_message(big, max_len=120)
    assert len(chunks) >= 2
    # אף chunk לא חורג מהגבול
    for c in chunks:
        assert len(c) <= 120


def test_split_long_message_respects_max_len() -> None:
    big = "x" * (MAX_TELEGRAM_MESSAGE_LEN * 2)
    chunks = split_long_message(big)
    for c in chunks:
        assert len(c) <= MAX_TELEGRAM_MESSAGE_LEN


def test_format_date_range_same_month() -> None:
    start = datetime(2026, 5, 24, tzinfo=timezone.utc)
    end = datetime(2026, 5, 30, tzinfo=timezone.utc)
    assert format_date_range(start, end) == "24-30 במאי 2026"


def test_format_date_range_cross_month() -> None:
    start = datetime(2026, 5, 24, tzinfo=timezone.utc)
    end = datetime(2026, 6, 2, tzinfo=timezone.utc)
    result = format_date_range(start, end)
    assert "24 במאי" in result
    assert "2 ביוני" in result


def test_format_date_range_cross_year_includes_both_years() -> None:
    """28 בדצמבר 2026 → 4 בינואר 2027 — חייב להראות את שתי השנים."""
    start = datetime(2026, 12, 28, tzinfo=timezone.utc)
    end = datetime(2027, 1, 4, tzinfo=timezone.utc)
    result = format_date_range(start, end)
    assert "2026" in result
    assert "2027" in result
    assert "28 בדצמבר" in result
    assert "4 בינואר" in result
