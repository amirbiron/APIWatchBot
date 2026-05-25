"""בדיקות ל-UrgentDispatcher."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from bson import ObjectId
from mongomock_motor import AsyncMongoMockClient

from app.db.indexes import ensure_indexes
from app.dispatcher.sender import SendResult
from app.dispatcher.urgent import UrgentDispatcher


class _FakeSender:
    def __init__(self, results: dict[int, SendResult] | None = None) -> None:
        # results: per chat_id; default = success
        self._results = results or {}
        self.sent: list[tuple[int, str]] = []

    async def send(self, chat_id: int, text: str) -> SendResult:
        self.sent.append((chat_id, text))
        return self._results.get(chat_id, SendResult(success=True, status="sent"))


async def _fresh_db():
    client = AsyncMongoMockClient()
    db = client["test_dispatcher_urgent"]
    await ensure_indexes(db)
    return db


async def _insert_user(
    db,
    telegram_id: int,
    *,
    subscribed: list[str],
    paused: bool = False,
    receive_urgent: bool = True,
) -> ObjectId:
    result = await db.users.insert_one(
        {
            "telegram_id": telegram_id,
            "subscribed_apis": subscribed,
            "paused": paused,
            "receive_urgent_alerts": receive_urgent,
            "min_severity": "important",
            "frequency": "weekly",
        }
    )
    return result.inserted_id


async def _insert_urgent_update(
    db,
    api_id: str,
    *,
    processed_at: datetime | None = None,
) -> ObjectId:
    result = await db.updates.insert_one(
        {
            "api_id": api_id,
            "raw_title": "t",
            "raw_content": "c",
            "source_url": "https://x",
            "content_hash": f"h-{api_id}-{processed_at}",
            "summary_he": "סיכום דחוף",
            "severity": "critical",
            "is_urgent": True,
            "categories": ["deprecation"],
            "status": "processed",
            "processed_at": processed_at or datetime.now(timezone.utc),
        }
    )
    return result.inserted_id


@pytest.mark.asyncio
async def test_urgent_picks_subscribed_active_users() -> None:
    db = await _fresh_db()
    sender = _FakeSender()

    # 3 משתמשים: מנוי פעיל, מנוי מושהה, לא מנוי
    await _insert_user(db, 1, subscribed=["render"])
    await _insert_user(db, 2, subscribed=["render"], paused=True)
    await _insert_user(db, 3, subscribed=["openai"])

    await _insert_urgent_update(db, "render")

    summary = await UrgentDispatcher(db=db, sender=sender).run()

    assert summary.messages_sent == 1
    assert sender.sent[0][0] == 1


@pytest.mark.asyncio
async def test_urgent_respects_receive_urgent_alerts_false() -> None:
    db = await _fresh_db()
    sender = _FakeSender()

    await _insert_user(db, 1, subscribed=["render"], receive_urgent=False)
    await _insert_urgent_update(db, "render")

    summary = await UrgentDispatcher(db=db, sender=sender).run()
    assert summary.messages_sent == 0
    assert sender.sent == []


@pytest.mark.asyncio
async def test_urgent_skips_already_delivered() -> None:
    db = await _fresh_db()
    sender = _FakeSender()

    user_id = await _insert_user(db, 1, subscribed=["render"])
    update_id = await _insert_urgent_update(db, "render")

    # שליחה ראשונה
    summary1 = await UrgentDispatcher(db=db, sender=sender).run()
    assert summary1.messages_sent == 1

    # שליחה שנייה — לא חוזרים על אותו פריט
    sender.sent.clear()
    summary2 = await UrgentDispatcher(db=db, sender=sender).run()
    assert summary2.messages_sent == 0
    assert summary2.already_delivered == 1


@pytest.mark.asyncio
async def test_urgent_one_failed_send_doesnt_block_others() -> None:
    db = await _fresh_db()
    # משתמש 99 נכשל (blocked), 1 ו-2 מצליחים
    sender = _FakeSender(
        results={99: SendResult(success=False, status="blocked")}
    )

    await _insert_user(db, 99, subscribed=["render"])
    await _insert_user(db, 1, subscribed=["render"])
    await _insert_user(db, 2, subscribed=["render"])
    await _insert_urgent_update(db, "render")

    summary = await UrgentDispatcher(db=db, sender=sender).run()
    assert summary.messages_sent == 2
    assert summary.send_failures == 1


@pytest.mark.asyncio
async def test_urgent_ignores_old_updates() -> None:
    db = await _fresh_db()
    sender = _FakeSender()

    await _insert_user(db, 1, subscribed=["render"])
    # processed לפני 48 שעות — מחוץ לחלון 24 השעות
    await _insert_urgent_update(
        db, "render", processed_at=datetime.now(timezone.utc) - timedelta(hours=48)
    )

    summary = await UrgentDispatcher(db=db, sender=sender).run()
    assert summary.updates_checked == 0
    assert sender.sent == []
