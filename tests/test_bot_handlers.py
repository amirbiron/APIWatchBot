"""בדיקות ל-handlers של הבוט.

עוקפים את PTB Application לחלוטין — בונים objects פשוטים שמדמים
את ה-Update/Message/CallbackQuery, ומריצים את ההandlers ישירות עם
context שמכיל את ה-repo. המטרה: לבדוק את הלוגיקה, לא את ה-framework.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.bot.user_repository import UserRepository
from app.db.indexes import ensure_indexes


# --- mocks ---


@dataclass
class _FakeUser:
    id: int
    username: str | None = "amir"
    first_name: str | None = "Amir"
    language_code: str | None = "he"


@dataclass
class _FakeMessage:
    replies: list[dict] = field(default_factory=list)

    async def reply_text(self, text: str, **kwargs) -> None:
        self.replies.append({"text": text, **kwargs})


@dataclass
class _FakeCallbackQuery:
    data: str
    from_user: _FakeUser
    answers: list[dict] = field(default_factory=list)
    edits: list[dict] = field(default_factory=list)

    async def answer(self, text: str = "", show_alert: bool = False) -> None:
        self.answers.append({"text": text, "show_alert": show_alert})

    async def edit_message_text(self, text: str, **kwargs) -> None:
        self.edits.append({"text": text, **kwargs})

    async def edit_message_reply_markup(self, reply_markup=None) -> None:
        self.edits.append({"reply_markup": reply_markup})


@dataclass
class _FakeUpdate:
    effective_user: _FakeUser | None
    message: _FakeMessage | None = None
    callback_query: _FakeCallbackQuery | None = None


@dataclass
class _FakeContext:
    bot_data: dict[str, Any] = field(default_factory=dict)


# --- fixtures ---


async def _make_context_with_user(telegram_id: int = 42):
    """יוצר context עם repo טרי + משתמש מוכן."""
    client = AsyncMongoMockClient()
    db = client["t"]
    await ensure_indexes(db)
    repo = UserRepository(db)
    ctx = _FakeContext(bot_data={"user_repository": repo})
    return ctx, repo, db


# --- /start ---


@pytest.mark.asyncio
async def test_start_new_user_enters_apis_selection() -> None:
    from app.bot.handlers.start import start_handler

    ctx, repo, _ = await _make_context_with_user()
    msg = _FakeMessage()
    update = _FakeUpdate(effective_user=_FakeUser(id=42), message=msg)

    await start_handler(update, ctx)

    # נוצר משתמש עם state=selecting_apis ו-in_initial_setup=True
    doc = await repo.get(42)
    assert doc["conversation_state"] == "selecting_apis"
    assert doc["in_initial_setup"] is True

    # נשלחה הודעת ברוך הבא + מקלדת
    assert len(msg.replies) == 1
    assert "ברוך הבא" in msg.replies[0]["text"]
    assert msg.replies[0]["reply_markup"] is not None


@pytest.mark.asyncio
async def test_start_existing_user_with_subscriptions_welcomes_back() -> None:
    from app.bot.handlers.start import start_handler

    ctx, repo, _ = await _make_context_with_user()
    await repo.get_or_create(telegram_id=42)
    await repo.toggle_subscription(42, "openai")

    msg = _FakeMessage()
    update = _FakeUpdate(effective_user=_FakeUser(id=42), message=msg)
    await start_handler(update, ctx)

    assert len(msg.replies) == 1
    assert "ברוך השב" in msg.replies[0]["text"]
    # אין מקלדת — רק טקסט
    assert msg.replies[0].get("reply_markup") is None


# --- /pause /resume /stop ---


@pytest.mark.asyncio
async def test_pause_handler_sets_paused_true() -> None:
    from app.bot.handlers.pause import pause_handler

    ctx, repo, _ = await _make_context_with_user()
    await repo.get_or_create(telegram_id=42)

    update = _FakeUpdate(
        effective_user=_FakeUser(id=42), message=_FakeMessage()
    )
    await pause_handler(update, ctx)
    doc = await repo.get(42)
    assert doc["paused"] is True


@pytest.mark.asyncio
async def test_resume_handler_sets_paused_false() -> None:
    from app.bot.handlers.resume import resume_handler

    ctx, repo, _ = await _make_context_with_user()
    await repo.get_or_create(telegram_id=42)
    await repo.set_paused(42, True)

    update = _FakeUpdate(
        effective_user=_FakeUser(id=42), message=_FakeMessage()
    )
    await resume_handler(update, ctx)
    doc = await repo.get(42)
    assert doc["paused"] is False


@pytest.mark.asyncio
async def test_stop_handler_deletes_user() -> None:
    from app.bot.handlers.stop import stop_handler

    ctx, repo, _ = await _make_context_with_user()
    await repo.get_or_create(telegram_id=42)

    update = _FakeUpdate(
        effective_user=_FakeUser(id=42), message=_FakeMessage()
    )
    await stop_handler(update, ctx)
    assert await repo.get(42) is None


@pytest.mark.asyncio
async def test_stop_handler_when_not_registered() -> None:
    from app.bot.handlers.stop import stop_handler

    ctx, repo, _ = await _make_context_with_user()
    msg = _FakeMessage()
    update = _FakeUpdate(effective_user=_FakeUser(id=999), message=msg)
    await stop_handler(update, ctx)
    assert "לא נמצאת" in msg.replies[0]["text"]


# --- callbacks ---


@pytest.mark.asyncio
async def test_api_toggle_callback() -> None:
    from app.bot.handlers.callbacks import callback_router

    ctx, repo, _ = await _make_context_with_user()
    await repo.get_or_create(telegram_id=42)

    cb = _FakeCallbackQuery(data="api:t:openai", from_user=_FakeUser(id=42))
    update = _FakeUpdate(effective_user=None, callback_query=cb)
    await callback_router(update, ctx)

    doc = await repo.get(42)
    assert "openai" in doc["subscribed_apis"]
    # answer נקרא + edit על המקלדת
    assert len(cb.answers) == 1
    assert any("reply_markup" in e for e in cb.edits)


@pytest.mark.asyncio
async def test_api_toggle_invalid_api_id_ignored() -> None:
    from app.bot.handlers.callbacks import callback_router

    ctx, repo, _ = await _make_context_with_user()
    await repo.get_or_create(telegram_id=42)

    cb = _FakeCallbackQuery(data="api:t:nonexistent", from_user=_FakeUser(id=42))
    update = _FakeUpdate(effective_user=None, callback_query=cb)
    await callback_router(update, ctx)

    # לא הוסף שום מנוי
    doc = await repo.get(42)
    assert doc["subscribed_apis"] == []


@pytest.mark.asyncio
async def test_api_done_in_initial_flow_advances_to_severity() -> None:
    from app.bot.handlers.callbacks import callback_router

    ctx, repo, _ = await _make_context_with_user()
    # סימולציה של /start — משתמש בפלואו הראשי עם בחירה אחת
    await repo.get_or_create(telegram_id=42)
    await repo.set_conversation_state(
        42, "selecting_apis", extra={"in_initial_setup": True}
    )
    await repo.toggle_subscription(42, "openai")

    cb = _FakeCallbackQuery(data="api:done", from_user=_FakeUser(id=42))
    update = _FakeUpdate(effective_user=None, callback_query=cb)
    await callback_router(update, ctx)

    doc = await repo.get(42)
    assert doc["conversation_state"] == "selecting_severity"


@pytest.mark.asyncio
async def test_api_done_outside_initial_flow_finishes() -> None:
    """/apis flow — done רק שומר ומחזיר ל-idle, לא מתקדם."""
    from app.bot.handlers.callbacks import callback_router

    ctx, repo, _ = await _make_context_with_user()
    await repo.get_or_create(telegram_id=42)
    await repo.toggle_subscription(42, "openai")
    await repo.set_conversation_state(42, "selecting_apis")  # ללא in_initial_setup

    cb = _FakeCallbackQuery(data="api:done", from_user=_FakeUser(id=42))
    update = _FakeUpdate(effective_user=None, callback_query=cb)
    await callback_router(update, ctx)

    doc = await repo.get(42)
    assert doc["conversation_state"] == "idle"


@pytest.mark.asyncio
async def test_api_done_with_zero_selected_blocks() -> None:
    from app.bot.handlers.callbacks import callback_router

    ctx, repo, _ = await _make_context_with_user()
    await repo.get_or_create(telegram_id=42)
    await repo.set_conversation_state(
        42, "selecting_apis", extra={"in_initial_setup": True}
    )

    cb = _FakeCallbackQuery(data="api:done", from_user=_FakeUser(id=42))
    update = _FakeUpdate(effective_user=None, callback_query=cb)
    await callback_router(update, ctx)

    # נשאר ב-selecting_apis, וanswered עם alert
    doc = await repo.get(42)
    assert doc["conversation_state"] == "selecting_apis"

    # ה-alert חייב להופיע כ-answer יחיד עם show_alert=True ועם הטקסט הנכון.
    # בעבר היה bug ש-query.answer() נקרא 2 פעמים — הראשון בראוטר, השני
    # ב-handler עם הטקסט. Telegram מתיר answer יחיד; הראשון "בלע" את ה-alert.
    assert len(cb.answers) == 1
    assert cb.answers[0]["show_alert"] is True
    assert "בחר לפחות ספק אחד" in cb.answers[0]["text"]


@pytest.mark.asyncio
async def test_callbacks_answer_exactly_once() -> None:
    """כל handler חייב לקרוא query.answer() בדיוק פעם אחת.
    קריאה כפולה זורקת BadRequest מ-Telegram."""
    from app.bot.handlers.callbacks import callback_router

    ctx, repo, _ = await _make_context_with_user()
    await repo.get_or_create(telegram_id=42)

    # toggle נקרא ענה פעם אחת
    cb = _FakeCallbackQuery(data="api:t:openai", from_user=_FakeUser(id=42))
    await callback_router(
        _FakeUpdate(effective_user=None, callback_query=cb), ctx
    )
    assert len(cb.answers) == 1


@pytest.mark.asyncio
async def test_severity_callback_in_initial_advances_to_frequency() -> None:
    from app.bot.handlers.callbacks import callback_router

    ctx, repo, _ = await _make_context_with_user()
    await repo.get_or_create(telegram_id=42)
    await repo.set_conversation_state(
        42, "selecting_severity", extra={"in_initial_setup": True}
    )

    cb = _FakeCallbackQuery(data="sev:critical", from_user=_FakeUser(id=42))
    update = _FakeUpdate(effective_user=None, callback_query=cb)
    await callback_router(update, ctx)

    doc = await repo.get(42)
    assert doc["min_severity"] == "critical"
    assert doc["conversation_state"] == "selecting_frequency"


@pytest.mark.asyncio
async def test_severity_callback_outside_initial_saves_only() -> None:
    from app.bot.handlers.callbacks import callback_router

    ctx, repo, _ = await _make_context_with_user()
    await repo.get_or_create(telegram_id=42)
    await repo.set_conversation_state(42, "selecting_severity")  # ללא in_initial

    cb = _FakeCallbackQuery(data="sev:all", from_user=_FakeUser(id=42))
    update = _FakeUpdate(effective_user=None, callback_query=cb)
    await callback_router(update, ctx)

    doc = await repo.get(42)
    assert doc["min_severity"] == "all"
    assert doc["conversation_state"] == "idle"


@pytest.mark.asyncio
async def test_final_callback_resets_initial_flag() -> None:
    from app.bot.handlers.callbacks import callback_router

    ctx, repo, _ = await _make_context_with_user()
    await repo.get_or_create(telegram_id=42)
    await repo.set_conversation_state(
        42, "confirming", extra={"in_initial_setup": True}
    )

    cb = _FakeCallbackQuery(data="done:final", from_user=_FakeUser(id=42))
    update = _FakeUpdate(effective_user=None, callback_query=cb)
    await callback_router(update, ctx)

    doc = await repo.get(42)
    assert doc["conversation_state"] == "idle"
    assert doc["in_initial_setup"] is False


@pytest.mark.asyncio
async def test_callback_unknown_data_silent() -> None:
    """callback_data לא מזוהה — לא קורס, רק לוג."""
    from app.bot.handlers.callbacks import callback_router

    ctx, repo, _ = await _make_context_with_user()
    await repo.get_or_create(telegram_id=42)

    cb = _FakeCallbackQuery(data="totally:bogus", from_user=_FakeUser(id=42))
    update = _FakeUpdate(effective_user=None, callback_query=cb)
    # לא זורק
    await callback_router(update, ctx)


# --- /apis /severity /settings ---


@pytest.mark.asyncio
async def test_apis_handler_sets_state_without_initial_flag() -> None:
    from app.bot.handlers.apis import apis_handler

    ctx, repo, _ = await _make_context_with_user()
    await repo.get_or_create(telegram_id=42)

    update = _FakeUpdate(
        effective_user=_FakeUser(id=42), message=_FakeMessage()
    )
    await apis_handler(update, ctx)

    doc = await repo.get(42)
    assert doc["conversation_state"] == "selecting_apis"
    assert doc.get("in_initial_setup") is not True


@pytest.mark.asyncio
async def test_apis_handler_clears_stale_initial_flag() -> None:
    """תרחיש: משתמש התחיל /start, נטש באמצע (נשאר in_initial_setup=True),
    ועכשיו פותח /apis. ה-flag חייב להתאפס כדי שה-callback לא יחטוף אותו
    לפלואו הראשי."""
    from app.bot.handlers.apis import apis_handler
    from app.bot.handlers.callbacks import callback_router

    ctx, repo, _ = await _make_context_with_user()
    await repo.get_or_create(telegram_id=42)
    # סימולציה: משתמש נטש /start באמצע
    await repo.set_conversation_state(
        42, "selecting_apis", extra={"in_initial_setup": True}
    )

    # עכשיו מתחיל /apis
    await apis_handler(
        _FakeUpdate(effective_user=_FakeUser(id=42), message=_FakeMessage()),
        ctx,
    )

    doc = await repo.get(42)
    assert doc.get("in_initial_setup") is False

    # ובהמשך — done בלי בחירות אינו מקדם לפלואו ראשי, ו-done עם בחירות
    # מסיים ל-idle ולא ל-selecting_severity.
    await repo.toggle_subscription(42, "openai")
    cb = _FakeCallbackQuery(data="api:done", from_user=_FakeUser(id=42))
    await callback_router(
        _FakeUpdate(effective_user=None, callback_query=cb), ctx
    )
    doc = await repo.get(42)
    assert doc["conversation_state"] == "idle"  # standalone — מסיים מיד


@pytest.mark.asyncio
async def test_severity_handler_clears_stale_initial_flag() -> None:
    """אותו תרחיש עבור /severity: stale flag לא יחטוף אותו לפלואו הראשי."""
    from app.bot.handlers.callbacks import callback_router
    from app.bot.handlers.severity import severity_handler

    ctx, repo, _ = await _make_context_with_user()
    await repo.get_or_create(telegram_id=42)
    await repo.set_conversation_state(
        42, "selecting_apis", extra={"in_initial_setup": True}
    )

    # /severity מתחיל
    await severity_handler(
        _FakeUpdate(effective_user=_FakeUser(id=42), message=_FakeMessage()),
        ctx,
    )

    doc = await repo.get(42)
    assert doc.get("in_initial_setup") is False
    assert doc["conversation_state"] == "selecting_severity"

    # ובחירת severity מסיימת ל-idle (לא מתקדמת ל-frequency).
    cb = _FakeCallbackQuery(data="sev:critical", from_user=_FakeUser(id=42))
    await callback_router(
        _FakeUpdate(effective_user=None, callback_query=cb), ctx
    )
    doc = await repo.get(42)
    assert doc["conversation_state"] == "idle"
    assert doc["min_severity"] == "critical"


@pytest.mark.asyncio
async def test_settings_handler_shows_summary() -> None:
    from app.bot.handlers.settings import settings_handler

    ctx, repo, _ = await _make_context_with_user()
    await repo.get_or_create(telegram_id=42)
    await repo.toggle_subscription(42, "openai")

    msg = _FakeMessage()
    update = _FakeUpdate(effective_user=_FakeUser(id=42), message=msg)
    await settings_handler(update, ctx)

    assert "OpenAI" in msg.replies[0]["text"]
    assert "/apis" in msg.replies[0]["text"]


@pytest.mark.asyncio
async def test_settings_handler_unregistered_redirects_to_start() -> None:
    from app.bot.handlers.settings import settings_handler

    ctx, repo, _ = await _make_context_with_user()
    msg = _FakeMessage()
    update = _FakeUpdate(effective_user=_FakeUser(id=999), message=msg)
    await settings_handler(update, ctx)
    assert "/start" in msg.replies[0]["text"]
