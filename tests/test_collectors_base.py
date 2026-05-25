"""בדיקות יחידה ל-RawItem ולוגיקת ה-hash."""

from __future__ import annotations

from datetime import datetime, timezone

from app.collectors.base import RawItem


def _make(api_id: str = "render", title: str = "t", content: str = "c", **kw) -> RawItem:
    return RawItem(api_id=api_id, raw_title=title, raw_content=content, source_url="https://x", **kw)


def test_content_hash_is_deterministic() -> None:
    item1 = RawItem(api_id="render", raw_title="t", raw_content="c", source_url="https://x")
    item2 = RawItem(api_id="render", raw_title="t", raw_content="c", source_url="https://y")
    # source_url לא נכלל ב-hash — שני הפריטים אמורים להיות זהים
    assert item1.content_hash == item2.content_hash


def test_content_hash_includes_api_id() -> None:
    """אותו טקסט מ-2 ספקים שונים חייב להיות hash שונה."""
    item_a = _make(api_id="render", title="Deploy faster", content="x")
    item_b = _make(api_id="openai", title="Deploy faster", content="x")
    assert item_a.content_hash != item_b.content_hash


def test_content_hash_changes_with_title() -> None:
    assert _make(title="A").content_hash != _make(title="B").content_hash


def test_content_hash_changes_with_content() -> None:
    assert _make(content="A").content_hash != _make(content="B").content_hash


def test_custom_hash_input_overrides_default() -> None:
    """מקור שצריך hash בעלי משמעות (Gemini — לפי תאריך) יכול לעקוף."""
    item1 = _make(api_id="gemini", title="long content A", content="long content A", custom_hash_input="2026-05-20")
    item2 = _make(api_id="gemini", title="completely different", content="totally different content", custom_hash_input="2026-05-20")
    # כי ה-custom_hash_input זהה — אותו hash
    assert item1.content_hash == item2.content_hash


def test_raw_item_is_frozen() -> None:
    item = _make()
    try:
        item.raw_title = "modified"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("RawItem חייב להיות frozen — שינוי שדות אסור")


def test_source_published_at_optional() -> None:
    item = _make(source_published_at=datetime(2026, 5, 20, tzinfo=timezone.utc))
    # אסור שיזרוק — datetime הוא hashable
    _ = item.content_hash
