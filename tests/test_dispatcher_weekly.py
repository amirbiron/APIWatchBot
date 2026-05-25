"""בדיקות ל-WeeklyDispatcher."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from bson import ObjectId
from mongomock_motor import AsyncMongoMockClient

from app.db.indexes import ensure_indexes
from app.dispatcher.sender import SendResult
from app.dispatcher.weekly import WeeklyDispatcher


class _FakeSender:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send(self, chat_id: int, text: str) -> SendResult:
        self.sent.append((chat_id, text))
        return SendResult(success=True, status="sent")


async def _fresh_db():
    client = AsyncMongoMockClient()
    db = client["test_dispatcher_weekly"]
    await ensure_indexes(db)
    return db


async def _insert_user(
    db,
    telegram_id: int,
    *,
    subscribed: list[str],
    min_severity: str = "important",
    paused: bool = False,
    frequency: str = "weekly",
) -> ObjectId:
    result = await db.users.insert_one(
        {
            "telegram_id": telegram_id,
            "subscribed_apis": subscribed,
            "min_severity": min_severity,
            "frequency": frequency,
            "paused": paused,
            "receive_urgent_alerts": True,
        }
    )
    return result.inserted_id


async def _insert_processed_update(
    db,
    api_id: str,
    *,
    severity: str = "important",
    processed_at: datetime | None = None,
) -> ObjectId:
    result = await db.updates.insert_one(
        {
            "api_id": api_id,
            "raw_title": f"t-{severity}",
            "raw_content": "c",
            "source_url": "https://x",
            "content_hash": f"h-{api_id}-{severity}-{processed_at}",
            "summary_he": f"סיכום {severity}",
            "severity": severity,
            "is_urgent": False,
            "categories": ["new_feature"],
            "status": "processed",
            "processed_at": processed_at or datetime.now(timezone.utc),
        }
    )
    return result.inserted_id


@pytest.mark.asyncio
async def test_weekly_filters_by_severity_and_subscriptions() -> None:
    db = await _fresh_db()
    sender = _FakeSender()

    # משתמש מנוי ל-render בלבד, רוצה רק critical+important
    await _insert_user(
        db, 1, subscribed=["render"], min_severity="important"
    )

    await _insert_processed_update(db, "render", severity="critical")  # ✓
    await _insert_processed_update(db, "render", severity="important")  # ✓
    await _insert_processed_update(db, "render", severity="info")  # ✗ (severity)
    await _insert_processed_update(db, "openai", severity="critical")  # ✗ (api)

    summary = await WeeklyDispatcher(db=db, sender=sender).run()

    assert summary.digests_sent == 1
    # הסיכום מכיל רק 2 פריטים (critical + important של render)
    msg = sender.sent[0][1]
    assert msg.count("▪️") == 2


@pytest.mark.asyncio
async def test_weekly_skips_user_with_no_matches() -> None:
    """לא שולחים digest ריק (Spec §8.2)."""
    db = await _fresh_db()
    sender = _FakeSender()

    await _insert_user(db, 1, subscribed=["render"])
    # אין updates של render במאגר
    await _insert_processed_update(db, "openai", severity="critical")

    summary = await WeeklyDispatcher(db=db, sender=sender).run()
    assert summary.digests_sent == 0
    assert sender.sent == []


@pytest.mark.asyncio
async def test_weekly_skips_paused_users() -> None:
    db = await _fresh_db()
    sender = _FakeSender()

    await _insert_user(db, 1, subscribed=["render"], paused=True)
    await _insert_processed_update(db, "render", severity="critical")

    summary = await WeeklyDispatcher(db=db, sender=sender).run()
    assert summary.users_checked == 0


@pytest.mark.asyncio
async def test_weekly_excludes_items_already_delivered_as_urgent() -> None:
    """אם פריט נשלח כ-urgent השבוע, הוא לא חוזר בסיכום השבועי."""
    db = await _fresh_db()
    sender = _FakeSender()

    user_id = await _insert_user(
        db, 1, subscribed=["render"], min_severity="important"
    )
    sent_id = await _insert_processed_update(db, "render", severity="critical")
    await _insert_processed_update(db, "render", severity="important")  # חדש

    # סימולציה: הפריט הראשון כבר נשלח כ-urgent
    await db.deliveries.insert_one(
        {
            "user_id": user_id,
            "update_id": sent_id,
            "delivery_type": "urgent",
            "sent_at": datetime.now(timezone.utc),
        }
    )

    summary = await WeeklyDispatcher(db=db, sender=sender).run()
    assert summary.digests_sent == 1
    # הסיכום מכיל רק את הפריט החדש
    assert sender.sent[0][1].count("▪️") == 1


@pytest.mark.asyncio
async def test_weekly_min_severity_all_includes_info() -> None:
    db = await _fresh_db()
    sender = _FakeSender()

    await _insert_user(db, 1, subscribed=["render"], min_severity="all")
    await _insert_processed_update(db, "render", severity="info")

    summary = await WeeklyDispatcher(db=db, sender=sender).run()
    assert summary.digests_sent == 1


@pytest.mark.asyncio
async def test_weekly_min_severity_critical_excludes_others() -> None:
    db = await _fresh_db()
    sender = _FakeSender()

    await _insert_user(db, 1, subscribed=["render"], min_severity="critical")
    await _insert_processed_update(db, "render", severity="important")
    await _insert_processed_update(db, "render", severity="info")

    summary = await WeeklyDispatcher(db=db, sender=sender).run()
    assert summary.digests_sent == 0


@pytest.mark.asyncio
async def test_weekly_records_delivery_per_update() -> None:
    db = await _fresh_db()
    sender = _FakeSender()

    user_id = await _insert_user(db, 1, subscribed=["render"])
    await _insert_processed_update(db, "render", severity="critical")
    await _insert_processed_update(db, "render", severity="important")

    await WeeklyDispatcher(db=db, sender=sender).run()

    delivered_count = await db.deliveries.count_documents(
        {"user_id": user_id, "delivery_type": "weekly_digest"}
    )
    assert delivered_count == 2


@pytest.mark.asyncio
async def test_weekly_user_with_no_subscriptions_skipped() -> None:
    db = await _fresh_db()
    sender = _FakeSender()

    await _insert_user(db, 1, subscribed=[])
    await _insert_processed_update(db, "render", severity="critical")

    summary = await WeeklyDispatcher(db=db, sender=sender).run()
    assert summary.digests_sent == 0
