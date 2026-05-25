"""בדיקות ל-UserRepository."""

from __future__ import annotations

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.bot.user_repository import UserRepository
from app.db.indexes import ensure_indexes


async def _fresh_repo():
    client = AsyncMongoMockClient()
    db = client["test_apiwatch_users"]
    await ensure_indexes(db)
    return UserRepository(db), db


@pytest.mark.asyncio
async def test_get_or_create_creates_new_user() -> None:
    repo, db = await _fresh_repo()
    doc, created = await repo.get_or_create(
        telegram_id=42, username="amir", first_name="Amir"
    )
    assert created is True
    assert doc["telegram_id"] == 42
    assert doc["min_severity"] == "important"
    assert doc["paused"] is False
    assert doc["conversation_state"] == "idle"


@pytest.mark.asyncio
async def test_get_or_create_is_idempotent() -> None:
    repo, db = await _fresh_repo()
    await repo.get_or_create(telegram_id=42)
    doc2, created2 = await repo.get_or_create(telegram_id=42)
    assert created2 is False
    # רק last_active_at משתנה — registered_at מהמסמך הראשון.
    assert doc2["registered_at"] is not None
    assert await db.users.count_documents({}) == 1


@pytest.mark.asyncio
async def test_toggle_subscription_adds_and_removes() -> None:
    repo, _ = await _fresh_repo()
    await repo.get_or_create(telegram_id=42)

    after_add = await repo.toggle_subscription(42, "openai")
    assert "openai" in after_add["subscribed_apis"]

    after_remove = await repo.toggle_subscription(42, "openai")
    assert "openai" not in after_remove["subscribed_apis"]


@pytest.mark.asyncio
async def test_toggle_subscription_returns_none_if_missing() -> None:
    repo, _ = await _fresh_repo()
    result = await repo.toggle_subscription(999, "openai")
    assert result is None


@pytest.mark.asyncio
async def test_toggle_subscription_concurrent_clicks_net_correctly() -> None:
    """2 clicks מקבילים על אותו api חייבים לתת net toggle של 2 פעמים
    (add ואז remove), לא 1 (התנהגות באג בדפוס check-then-act)."""
    import asyncio

    repo, _ = await _fresh_repo()
    await repo.get_or_create(telegram_id=42)

    # שני toggles מקבילים. ה-await gather מבטיח שהם יוצאים בו-זמנית.
    results = await asyncio.gather(
        repo.toggle_subscription(42, "openai"),
        repo.toggle_subscription(42, "openai"),
    )

    # שניהם חייבים להחזיר doc תקין (לא None — המשתמש קיים)
    assert all(r is not None for r in results)

    # המצב הסופי: api_id לא ברשימה (add + remove = net empty).
    # זה ה-correctness של ה-CAS — בלי זה היה possible שיגיע ל-1 add בלבד.
    final = await repo.get(42)
    assert "openai" not in final["subscribed_apis"]


@pytest.mark.asyncio
async def test_set_conversation_state_with_extra() -> None:
    repo, _ = await _fresh_repo()
    await repo.get_or_create(telegram_id=42)

    updated = await repo.set_conversation_state(
        42, "selecting_severity", extra={"min_severity": "critical"}
    )
    assert updated["conversation_state"] == "selecting_severity"
    assert updated["min_severity"] == "critical"


@pytest.mark.asyncio
async def test_set_conversation_state_with_expected_state() -> None:
    """מעבר מתבצע רק אם המצב הנוכחי תואם — מונע race."""
    repo, _ = await _fresh_repo()
    await repo.get_or_create(telegram_id=42)

    # idle → selecting_apis — תואם
    ok = await repo.set_conversation_state(
        42, "selecting_apis", expected_state="idle"
    )
    assert ok is not None

    # idle → ... אבל המצב הנוכחי הוא selecting_apis — לא תואם, אין עדכון
    rejected = await repo.set_conversation_state(
        42, "selecting_severity", expected_state="idle"
    )
    assert rejected is None


@pytest.mark.asyncio
async def test_set_paused() -> None:
    repo, _ = await _fresh_repo()
    await repo.get_or_create(telegram_id=42)

    assert await repo.set_paused(42, True) is True
    doc = await repo.get(42)
    assert doc["paused"] is True

    assert await repo.set_paused(42, False) is True
    doc = await repo.get(42)
    assert doc["paused"] is False


@pytest.mark.asyncio
async def test_set_paused_missing_user_returns_false() -> None:
    repo, _ = await _fresh_repo()
    assert await repo.set_paused(999, True) is False


@pytest.mark.asyncio
async def test_update_settings_partial() -> None:
    """None לא משנה — רק שדות שהועברו."""
    repo, _ = await _fresh_repo()
    await repo.get_or_create(telegram_id=42)
    original = await repo.get(42)
    assert original["min_severity"] == "important"

    updated = await repo.update_settings(42, min_severity="critical")
    assert updated["min_severity"] == "critical"
    # frequency לא הועבר → לא השתנה
    assert updated["frequency"] == "weekly"


@pytest.mark.asyncio
async def test_delete_removes_user() -> None:
    repo, db = await _fresh_repo()
    await repo.get_or_create(telegram_id=42)

    assert await repo.delete(42) is True
    assert await repo.get(42) is None
    assert await db.users.count_documents({}) == 0


@pytest.mark.asyncio
async def test_delete_missing_returns_false() -> None:
    repo, _ = await _fresh_repo()
    assert await repo.delete(999) is False
