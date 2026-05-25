"""בדיקות ל-CollectorRunner ול-storage עם DB אמיתי (mongomock-motor)."""

from __future__ import annotations

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.collectors.base import BaseSource, RawItem
from app.collectors.runner import CollectorRunner
from app.collectors.storage import save_raw_items
from app.db.indexes import ensure_indexes


class _FakeSource(BaseSource):
    """מקור מזויף שמחזיר רשימה קבועה — לבדיקת ה-Runner בלי רשת."""

    api_id = "fake"
    name_he = "Fake"
    source_url = "https://example.invalid/feed"

    def __init__(self, items: list[RawItem]) -> None:
        self._items = items
        # אין שימוש ב-http — לא נקרא ל-super().__init__

    async def fetch(self) -> list[RawItem]:
        return self._items


class _FailingSource(BaseSource):
    api_id = "broken"
    name_he = "Broken"
    source_url = "https://broken.invalid/feed"

    def __init__(self) -> None:
        pass

    async def fetch(self) -> list[RawItem]:
        raise RuntimeError("boom")


async def _fresh_db():
    client = AsyncMongoMockClient()
    db = client["test_apiwatch"]
    await ensure_indexes(db)
    return db


@pytest.mark.asyncio
async def test_save_raw_items_inserts_new() -> None:
    db = await _fresh_db()
    items = [
        RawItem(api_id="x", raw_title="a", raw_content="1", source_url="https://a"),
        RawItem(api_id="x", raw_title="b", raw_content="2", source_url="https://b"),
    ]
    inserted, duplicates = await save_raw_items(db, items)
    assert inserted == 2
    assert duplicates == 0
    assert await db.updates.count_documents({}) == 2


@pytest.mark.asyncio
async def test_save_raw_items_dedup_atomic() -> None:
    """כלל 2 ב-CLAUDE.md: הרצה שנייה של אותו פריט לא יוצרת כפילות."""
    db = await _fresh_db()
    items = [RawItem(api_id="x", raw_title="t", raw_content="c", source_url="https://x")]

    inserted_a, dup_a = await save_raw_items(db, items)
    inserted_b, dup_b = await save_raw_items(db, items)

    assert inserted_a == 1
    assert dup_a == 0
    assert inserted_b == 0
    assert dup_b == 1
    assert await db.updates.count_documents({}) == 1


@pytest.mark.asyncio
async def test_runner_handles_source_failure() -> None:
    """כשל במקור אחד לא מפיל אחרים."""
    db = await _fresh_db()
    good = _FakeSource([RawItem(api_id="fake", raw_title="t", raw_content="c", source_url="https://x")])
    bad = _FailingSource()

    runner = CollectorRunner(sources=[bad, good], db=db)
    summary = await runner.run_all()

    assert summary.total_inserted == 1
    assert "broken" in summary.failed_sources
    assert "fake" not in summary.failed_sources


@pytest.mark.asyncio
async def test_runner_updates_system_state() -> None:
    db = await _fresh_db()
    source = _FakeSource([RawItem(api_id="fake", raw_title="t", raw_content="c", source_url="https://x")])
    runner = CollectorRunner(sources=[source], db=db)
    await runner.run_all()

    last_run = await db.system_state.find_one({"key": "last_collect_run"})
    assert last_run is not None
    assert last_run["value"]["total_inserted"] == 1

    per_source = await db.system_state.find_one({"key": "last_collect:fake"})
    assert per_source is not None


@pytest.mark.asyncio
async def test_runner_run_all_does_not_throw_on_state_write_failure() -> None:
    """run_all חייב להחזיר RunSummary גם אם ה-system_state write נכשל.
    APScheduler היה מסמן את ה-job כ-failed וגורם ל-retry/alert מיותרים."""
    db = await _fresh_db()
    source = _FakeSource([RawItem(api_id="fake", raw_title="t", raw_content="c", source_url="https://x")])
    runner = CollectorRunner(sources=[source], db=db)

    # מחליפים את system_state ב-collection שזורק על update_one
    class _BrokenCollection:
        async def update_one(self, *args, **kwargs):
            raise RuntimeError("simulated mongo outage")

    runner._db = type("DB", (), {"updates": db.updates, "system_state": _BrokenCollection()})()

    # חייב להחזיר summary, לא לזרוק
    summary = await runner.run_all()
    assert summary.total_inserted == 1
    assert "fake" not in summary.failed_sources  # ה-fetch הצליח, ה-state write לא רלוונטי


@pytest.mark.asyncio
async def test_runner_stores_all_required_fields() -> None:
    """וידוא שהדוקומנט שנכנס ל-DB תואם לסכמת Updates ב-Spec סעיף 4.2."""
    db = await _fresh_db()
    items = [RawItem(api_id="render", raw_title="t", raw_content="c", source_url="https://r")]
    await save_raw_items(db, items)

    doc = await db.updates.find_one({})
    assert doc is not None
    for field in [
        "api_id",
        "raw_title",
        "raw_content",
        "source_url",
        "content_hash",
        "collected_at",
        "status",
    ]:
        assert field in doc, f"חסר שדה: {field}"
    assert doc["status"] == "raw"
