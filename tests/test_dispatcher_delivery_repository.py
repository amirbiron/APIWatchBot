"""בדיקות ל-app/dispatcher/delivery_repository.py."""

from __future__ import annotations

import asyncio

import pytest
from bson import ObjectId
from mongomock_motor import AsyncMongoMockClient

from app.db.indexes import ensure_indexes
from app.dispatcher.delivery_repository import DeliveryRepository


async def _fresh_repo():
    client = AsyncMongoMockClient()
    db = client["test_deliveries"]
    await ensure_indexes(db)
    return DeliveryRepository(db), db


@pytest.mark.asyncio
async def test_claim_first_time_succeeds() -> None:
    repo, db = await _fresh_repo()
    user_id = ObjectId()
    update_id = ObjectId()

    assert await repo.try_claim(user_id, update_id, "urgent") is True
    assert await db.deliveries.count_documents({}) == 1


@pytest.mark.asyncio
async def test_claim_second_time_returns_false() -> None:
    repo, db = await _fresh_repo()
    user_id = ObjectId()
    update_id = ObjectId()

    assert await repo.try_claim(user_id, update_id, "urgent") is True
    # delivery_type שונה — עדיין נחסם, כי ה-unique index הוא (user, update) בלבד
    assert await repo.try_claim(user_id, update_id, "weekly_digest") is False
    assert await db.deliveries.count_documents({}) == 1


@pytest.mark.asyncio
async def test_claim_concurrent_only_one_wins() -> None:
    """2 הרצות שמתפסות את אותו slot באותו רגע — רק אחת מצליחה."""
    repo, db = await _fresh_repo()
    user_id = ObjectId()
    update_id = ObjectId()

    results = await asyncio.gather(
        repo.try_claim(user_id, update_id, "urgent"),
        repo.try_claim(user_id, update_id, "urgent"),
    )
    # אחד True, אחד False
    assert sorted(results) == [False, True]
    assert await db.deliveries.count_documents({}) == 1


@pytest.mark.asyncio
async def test_get_delivered_update_ids_filters_correctly() -> None:
    repo, _ = await _fresh_repo()
    user_id = ObjectId()
    sent_id = ObjectId()
    pending_id = ObjectId()
    other_user_id = ObjectId()
    other_sent_id = ObjectId()

    # נשלחו: sent_id למשתמש שלנו, other_sent_id למשתמש אחר
    await repo.try_claim(user_id, sent_id, "urgent")
    await repo.try_claim(other_user_id, other_sent_id, "urgent")

    delivered = await repo.get_delivered_update_ids(
        user_id, [sent_id, pending_id, other_sent_id]
    )
    assert delivered == {sent_id}


@pytest.mark.asyncio
async def test_get_delivered_empty_input_returns_empty() -> None:
    repo, _ = await _fresh_repo()
    result = await repo.get_delivered_update_ids(ObjectId(), [])
    assert result == set()
