"""בדיקות ל-app/utils/notify.py."""

from __future__ import annotations

import httpx
import pytest


@pytest.mark.asyncio
async def test_notify_admin_calls_telegram_api(monkeypatch) -> None:
    """כשהקונפיג מלא — נשלחת בקשה ל-Bot API עם payload נכון."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("ADMIN_TELEGRAM_ID", "12345")

    from app.config import get_settings

    get_settings.cache_clear()

    from app.utils import notify as notify_module

    captured: list[dict] = []

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url: str, json: dict) -> httpx.Response:
            captured.append({"url": url, "json": json})
            return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr(notify_module.httpx, "AsyncClient", _FakeClient)

    try:
        # ה-caller אחראי על escape פר-ערך. ה-helper לא נוגע במחרוזת
        # כדי שלא יהרוס tags של עיצוב כמו <b>.
        await notify_module.notify_admin("<b>bold</b> + safe text")

        assert len(captured) == 1
        assert "fake-token" in captured[0]["url"]
        assert captured[0]["json"]["chat_id"] == 12345
        # ה-message מועבר as-is — Telegram יציג <b>bold</b> כטקסט מודגש.
        assert captured[0]["json"]["text"] == "<b>bold</b> + safe text"
        assert captured[0]["json"]["parse_mode"] == "HTML"
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_notify_admin_silent_when_unconfigured(monkeypatch) -> None:
    """admin_id חסר → לא נשלח request, אין שגיאה."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.delenv("ADMIN_TELEGRAM_ID", raising=False)

    from app.config import get_settings

    get_settings.cache_clear()

    from app.utils import notify as notify_module

    called = {"count": 0}

    class _FailIfCalled:
        def __init__(self, *args, **kwargs):
            called["count"] += 1

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    monkeypatch.setattr(notify_module.httpx, "AsyncClient", _FailIfCalled)

    try:
        # לא זורק — sukses
        await notify_module.notify_admin("nope")
        assert called["count"] == 0
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_notify_admin_swallows_api_error(monkeypatch) -> None:
    """כשל ב-Bot API לא יפיל את הקורא (collector תלוי באמינות שלנו)."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("ADMIN_TELEGRAM_ID", "12345")

    from app.config import get_settings

    get_settings.cache_clear()

    from app.utils import notify as notify_module

    class _BrokenClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, *args, **kwargs):
            raise httpx.NetworkError("simulated network down")

    monkeypatch.setattr(notify_module.httpx, "AsyncClient", _BrokenClient)

    try:
        # חייב להחזיר בלי לזרוק
        await notify_module.notify_admin("doesn't matter")
    finally:
        get_settings.cache_clear()
