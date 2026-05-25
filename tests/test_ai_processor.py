"""בדיקות ל-AIProcessor — דפוס זהה ל-test_collectors_runner."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.ai.client import GeminiAPIError
from app.ai.processor import AIProcessor
from app.db.indexes import ensure_indexes


class _FakeAIClient:
    """מחליף את GeminiClient. מחזיר תשובות מתוכננות לפי api_id."""

    def __init__(self, responses_by_api_id: dict[str, Any]) -> None:
        self._responses = responses_by_api_id
        self.calls: list[str] = []

    async def generate(self, prompt: str) -> dict[str, Any]:
        # זיהוי המקור לפי "API: <id>" שמופיע בפרומפט
        api_id = ""
        for line in prompt.splitlines():
            if line.startswith("API:"):
                api_id = line.split(":", 1)[1].strip()
                break
        self.calls.append(api_id)

        response = self._responses.get(api_id)
        if isinstance(response, Exception):
            raise response
        if response is None:
            raise AssertionError(f"no fake response configured for api_id={api_id!r}")
        return response


async def _fresh_db():
    client = AsyncMongoMockClient()
    db = client["test_apiwatch_ai"]
    await ensure_indexes(db)
    return db


async def _seed_raw(db, api_id: str, title: str = "t", content: str = "c") -> Any:
    """מכניס raw item ומחזיר את ה-_id."""
    doc = {
        "api_id": api_id,
        "raw_title": title,
        "raw_content": content,
        "source_url": "https://example.com/x",
        "content_hash": f"hash-{api_id}-{title}",
        "summary_he": None,
        "severity": None,
        "is_urgent": False,
        "categories": [],
        "collected_at": datetime.now(timezone.utc),
        "processed_at": None,
        "status": "raw",
    }
    result = await db.updates.insert_one(doc)
    return result.inserted_id


@pytest.mark.asyncio
async def test_processor_marks_noise_as_skipped(monkeypatch) -> None:
    db = await _fresh_db()
    item_id = await _seed_raw(db, "render")

    ai = _FakeAIClient(
        {
            "render": {
                "is_noise": True,
                "summary_he": "",
                "severity": "info",
                "is_urgent": False,
                "categories": [],
            }
        }
    )

    from app.ai import processor as proc_mod

    monkeypatch.setattr(proc_mod, "notify_admin", _noop_notify)

    summary = await AIProcessor(db=db, ai_client=ai).run_batch()

    assert summary.skipped_noise == 1
    assert summary.processed == 0

    doc = await db.updates.find_one({"_id": item_id})
    assert doc["status"] == "skipped_noise"
    assert doc["processed_at"] is not None


@pytest.mark.asyncio
async def test_processor_writes_full_result(monkeypatch) -> None:
    db = await _fresh_db()
    item_id = await _seed_raw(db, "openai", title="Deprecation")

    payload = {
        "is_noise": False,
        "summary_he": "GPT-3.5-turbo-0301 ייפסק ב-13 ביוני.",
        "severity": "critical",
        "is_urgent": True,
        "categories": ["deprecation", "breaking"],
    }
    ai = _FakeAIClient({"openai": payload})

    from app.ai import processor as proc_mod

    monkeypatch.setattr(proc_mod, "notify_admin", _noop_notify)

    summary = await AIProcessor(db=db, ai_client=ai).run_batch()

    assert summary.processed == 1
    assert summary.failed == 0

    doc = await db.updates.find_one({"_id": item_id})
    assert doc["status"] == "processed"
    assert doc["summary_he"] == payload["summary_he"]
    assert doc["severity"] == "critical"
    assert doc["is_urgent"] is True
    assert doc["categories"] == ["deprecation", "breaking"]


@pytest.mark.asyncio
async def test_processor_marks_failed_on_persistent_error(monkeypatch) -> None:
    db = await _fresh_db()
    item_id = await _seed_raw(db, "twilio")

    ai = _FakeAIClient({"twilio": GeminiAPIError("nope")})

    from app.ai import processor as proc_mod

    notified: list[str] = []
    monkeypatch.setattr(proc_mod, "notify_admin", _capture(notified))

    summary = await AIProcessor(db=db, ai_client=ai).run_batch()

    assert summary.failed == 1
    assert summary.processed == 0

    doc = await db.updates.find_one({"_id": item_id})
    assert doc["status"] == "failed"
    # הודעת השגיאה נשמרת ב-DB לאבחון בלי צורך לחצב לוגים
    assert "nope" in doc.get("last_error", "")

    # התראת אדמין מקובצת — קוראים פעם אחת בכל ה-batch.
    assert len(notified) == 1


@pytest.mark.asyncio
async def test_processor_sends_one_admin_alert_per_batch(monkeypatch) -> None:
    """גם אם 3 items נכשלים — רק התראה אחת מקובצת נשלחת."""
    db = await _fresh_db()
    for i in range(3):
        await _seed_raw(db, "stripe", title=f"item-{i}")

    ai = _FakeAIClient({"stripe": GeminiAPIError("boom")})

    from app.ai import processor as proc_mod

    notified: list[str] = []
    monkeypatch.setattr(proc_mod, "notify_admin", _capture(notified))

    summary = await AIProcessor(db=db, ai_client=ai).run_batch()

    assert summary.failed == 3
    assert len(notified) == 1
    assert "3" in notified[0]


@pytest.mark.asyncio
async def test_processor_processes_only_raw_status(monkeypatch) -> None:
    """items עם status שונה מ-raw לא נבחרים."""
    db = await _fresh_db()
    raw_id = await _seed_raw(db, "render")
    # פריט שכבר עבד — אסור לבחור שוב
    await db.updates.update_one(
        {"_id": raw_id}, {"$set": {"status": "processed"}}
    )
    # פריט raw חדש
    new_raw = await _seed_raw(db, "render", title="new")

    ai = _FakeAIClient(
        {
            "render": {
                "is_noise": False,
                "summary_he": "x",
                "severity": "info",
                "is_urgent": False,
                "categories": [],
            }
        }
    )

    from app.ai import processor as proc_mod

    monkeypatch.setattr(proc_mod, "notify_admin", _noop_notify)

    summary = await AIProcessor(db=db, ai_client=ai).run_batch()

    assert summary.fetched == 1  # רק ה-raw החדש
    assert ai.calls == ["render"]
    assert summary.processed == 1

    # ה-processed המקורי לא השתנה
    doc_original = await db.updates.find_one({"_id": raw_id})
    assert doc_original["status"] == "processed"
    assert doc_original.get("summary_he") in (None, "")


@pytest.mark.asyncio
async def test_processor_writes_state(monkeypatch) -> None:
    db = await _fresh_db()
    await _seed_raw(db, "render")

    ai = _FakeAIClient(
        {
            "render": {
                "is_noise": False,
                "summary_he": "x",
                "severity": "info",
                "is_urgent": False,
                "categories": [],
            }
        }
    )

    from app.ai import processor as proc_mod

    monkeypatch.setattr(proc_mod, "notify_admin", _noop_notify)

    await AIProcessor(db=db, ai_client=ai).run_batch()

    state = await db.system_state.find_one({"key": "last_ai_run"})
    assert state is not None
    assert state["value"]["processed"] == 1
    assert state["value"]["fetched"] == 1


@pytest.mark.asyncio
async def test_processor_survives_db_write_failure(monkeypatch) -> None:
    """כשל ב-DB write פר item לא יפיל את ה-batch (no-throw contract)."""
    db = await _fresh_db()
    await _seed_raw(db, "render")
    await _seed_raw(db, "render", title="second")

    ai = _FakeAIClient(
        {
            "render": {
                "is_noise": False,
                "summary_he": "x",
                "severity": "info",
                "is_urgent": False,
                "categories": [],
            }
        }
    )

    # מעטפים את db.updates עם wrapper ש-update_one זורק תמיד
    class _BrokenUpdates:
        def __init__(self, real):
            self._real = real

        def find(self, *args, **kwargs):
            return self._real.find(*args, **kwargs)

        async def update_one(self, *args, **kwargs):
            raise RuntimeError("simulated mongo outage")

    broken_db = type(
        "DB",
        (),
        {
            "updates": _BrokenUpdates(db.updates),
            "system_state": db.system_state,
        },
    )()

    from app.ai import processor as proc_mod

    notified: list[str] = []
    monkeypatch.setattr(proc_mod, "notify_admin", _capture(notified))

    # ה-batch לא זורק למרות שכל ה-update_one זורקים
    summary = await AIProcessor(db=broken_db, ai_client=ai).run_batch()
    assert summary.fetched == 2
    # האיכוסים מסומנים כ-failed כי ה-DB write נכשל
    assert summary.failed == 2


@pytest.mark.asyncio
async def test_processor_empty_batch_short_circuits(monkeypatch) -> None:
    """אין items → לא קוראים ל-AI ולא שולחים alert."""
    db = await _fresh_db()
    ai = _FakeAIClient({})

    from app.ai import processor as proc_mod

    notified: list[str] = []
    monkeypatch.setattr(proc_mod, "notify_admin", _capture(notified))

    summary = await AIProcessor(db=db, ai_client=ai).run_batch()

    assert summary.fetched == 0
    assert ai.calls == []
    assert notified == []


# --- helpers ---


async def _noop_notify(message: str) -> None:
    pass


def _capture(target: list[str]):
    async def _fake(message: str) -> None:
        target.append(message)

    return _fake
