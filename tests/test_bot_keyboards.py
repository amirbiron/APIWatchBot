"""בדיקות לבוני המקלדות ב-app/bot/keyboards.py."""

from __future__ import annotations

from app.bot.apis_registry import SUBSCRIBABLE_APIS
from app.bot.keyboards import (
    build_apis_keyboard,
    build_final_confirm_keyboard,
    build_frequency_keyboard,
    build_severity_keyboard,
    build_urgent_keyboard,
)


def test_apis_keyboard_marks_subscribed() -> None:
    """ה-API שמופיע ב-subscribed מסומן ב-✅; השאר ב-⬜."""
    kb = build_apis_keyboard(subscribed_apis=["openai"])
    rows = kb.inline_keyboard
    # שורה אחרונה היא "סיום"; שורות לפניה הן ה-APIs
    api_rows = rows[:-1]
    assert len(api_rows) == len(SUBSCRIBABLE_APIS)

    for row in api_rows:
        button = row[0]
        if button.callback_data == "api:t:openai":
            assert "✅" in button.text
        else:
            assert "⬜" in button.text

    # כפתור הסיום
    assert rows[-1][0].callback_data == "api:done"


def test_apis_keyboard_empty_subscriptions() -> None:
    kb = build_apis_keyboard(subscribed_apis=[])
    for row in kb.inline_keyboard[:-1]:
        assert "⬜" in row[0].text


def test_severity_keyboard_marks_current() -> None:
    kb = build_severity_keyboard(current="critical")
    texts = [row[0].text for row in kb.inline_keyboard]
    # הנוכחי מסומן ב-• בתחילת הטקסט
    assert any(t.startswith("• ") for t in texts)
    # callback_data תקין
    cbs = [row[0].callback_data for row in kb.inline_keyboard]
    assert set(cbs) == {"sev:critical", "sev:important", "sev:all"}


def test_severity_keyboard_no_current() -> None:
    kb = build_severity_keyboard(current=None)
    for row in kb.inline_keyboard:
        assert not row[0].text.startswith("• ")


def test_frequency_keyboard_only_weekly() -> None:
    kb = build_frequency_keyboard()
    assert len(kb.inline_keyboard) == 1
    assert kb.inline_keyboard[0][0].callback_data == "freq:weekly"


def test_urgent_keyboard_has_yes_no() -> None:
    kb = build_urgent_keyboard()
    assert len(kb.inline_keyboard[0]) == 2
    cbs = {b.callback_data for b in kb.inline_keyboard[0]}
    assert cbs == {"urg:1", "urg:0"}


def test_final_confirm_keyboard() -> None:
    kb = build_final_confirm_keyboard()
    assert kb.inline_keyboard[0][0].callback_data == "done:final"
