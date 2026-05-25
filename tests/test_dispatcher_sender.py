"""בדיקות ל-app/dispatcher/sender.py."""

from __future__ import annotations

import asyncio
import time

import httpx
import pytest

from app.dispatcher.sender import TelegramSender


def _make_sender_with_handler(handler) -> TelegramSender:
    """יוצר TelegramSender עם MockTransport. מחליף את ה-httpx.AsyncClient."""
    sender = TelegramSender(bot_token="fake-token")
    # מחליפים את ה-client הפנימי
    transport = httpx.MockTransport(handler)
    asyncio.get_event_loop().run_until_complete(sender._client.aclose())
    sender._client = httpx.AsyncClient(transport=transport, timeout=5.0)
    return sender


@pytest.mark.asyncio
async def test_sender_posts_correct_payload() -> None:
    captured: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True})

    sender = TelegramSender(bot_token="fake-token")
    sender._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        result = await sender.send(chat_id=12345, text="<b>hi</b>")
        assert result.success is True
        assert result.status == "sent"
        assert captured[0]["chat_id"] == 12345
        assert captured[0]["text"] == "<b>hi</b>"
        assert captured[0]["parse_mode"] == "HTML"
    finally:
        await sender.close()


@pytest.mark.asyncio
async def test_sender_swallows_403_blocked() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={"ok": False, "error_code": 403, "description": "Forbidden: bot was blocked"},
        )

    sender = TelegramSender(bot_token="fake")
    sender._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        result = await sender.send(chat_id=999, text="x")
        assert result.success is False
        assert result.status == "blocked"
    finally:
        await sender.close()


@pytest.mark.asyncio
async def test_sender_retries_on_429() -> None:
    """ניסיון ראשון 429 + retry_after=0 → ניסיון שני 200."""
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return httpx.Response(
                429,
                json={
                    "ok": False,
                    "parameters": {"retry_after": 0},
                    "description": "Too Many Requests",
                },
            )
        return httpx.Response(200, json={"ok": True})

    sender = TelegramSender(bot_token="fake")
    sender._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        result = await sender.send(chat_id=1, text="x")
        assert result.success is True
        assert call_count["n"] == 2
    finally:
        await sender.close()


@pytest.mark.asyncio
async def test_sender_chat_not_found_returns_clear_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"ok": False, "description": "Bad Request: chat not found"},
        )

    sender = TelegramSender(bot_token="fake")
    sender._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        result = await sender.send(chat_id=1, text="x")
        assert result.success is False
        assert result.status == "chat_not_found"
    finally:
        await sender.close()


@pytest.mark.asyncio
async def test_sender_rate_limit_throttles() -> None:
    """3 הודעות ברצף — אורך הריצה חייב להיות לפחות 2 * MIN_INTERVAL."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    sender = TelegramSender(bot_token="fake")
    sender._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        start = time.monotonic()
        for i in range(3):
            await sender.send(chat_id=i, text="x")
        elapsed = time.monotonic() - start
        # 3 הודעות = 2 הפרשי המתנה של ~40ms = ~80ms מינימום
        assert elapsed >= 0.06
    finally:
        await sender.close()


@pytest.mark.asyncio
async def test_sender_network_error_returns_error_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated down")

    sender = TelegramSender(bot_token="fake")
    sender._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        result = await sender.send(chat_id=1, text="x")
        assert result.success is False
        assert result.status == "error"
    finally:
        await sender.close()
