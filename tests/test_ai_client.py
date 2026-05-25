"""בדיקות ל-GeminiClient — מוקדות על retry ועל parsing.

מוקים את ה-SDK ברמת `_client.aio.models.generate_content` כדי לא
לדבר עם Gemini אמיתי בבדיקות.
"""

from __future__ import annotations

import json

import pytest

from app.ai.client import GeminiAPIError, GeminiClient


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


def _make_client_with_responses(monkeypatch, responses: list) -> GeminiClient:
    """יוצר GeminiClient ש-aio.models.generate_content מחזיר/זורק לפי `responses`.

    כל איבר ברשימה הוא או FakeResponse או Exception.
    """
    client = GeminiClient(api_key="fake")

    call_count = {"n": 0}

    async def fake_generate(*args, **kwargs):
        idx = call_count["n"]
        call_count["n"] += 1
        if idx >= len(responses):
            raise AssertionError(f"unexpected extra call #{idx + 1}")
        item = responses[idx]
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(client._client.aio.models, "generate_content", fake_generate)
    return client


VALID_PAYLOAD = {
    "is_noise": False,
    "summary_he": "פיצ'ר חדש",
    "severity": "important",
    "is_urgent": False,
    "categories": ["new_feature"],
}


@pytest.mark.asyncio
async def test_client_returns_parsed_dict(monkeypatch) -> None:
    client = _make_client_with_responses(
        monkeypatch, [_FakeResponse(json.dumps(VALID_PAYLOAD))]
    )
    result = await client.generate("any prompt")
    assert result == VALID_PAYLOAD


@pytest.mark.asyncio
async def test_client_retries_once_on_api_error(monkeypatch) -> None:
    """כשל ראשון → ניסיון שני → מצליח."""
    client = _make_client_with_responses(
        monkeypatch,
        [
            RuntimeError("transient API error"),
            _FakeResponse(json.dumps(VALID_PAYLOAD)),
        ],
    )
    result = await client.generate("any prompt")
    assert result["severity"] == "important"


@pytest.mark.asyncio
async def test_client_raises_after_max_attempts(monkeypatch) -> None:
    """שני כשלים → GeminiAPIError."""
    client = _make_client_with_responses(
        monkeypatch,
        [RuntimeError("first"), RuntimeError("second")],
    )
    with pytest.raises(GeminiAPIError, match="failed after 2 attempts"):
        await client.generate("any prompt")


@pytest.mark.asyncio
async def test_client_raises_on_invalid_json(monkeypatch) -> None:
    """structured output אמור למנוע זאת, אבל מגנים מפני SDK bugs."""
    client = _make_client_with_responses(
        monkeypatch, [_FakeResponse("not really json")]
    )
    # Note: ניסיון אחד נכשל, ניסיון שני גם אם נמשיך לחזיר אותו טקסט
    # יעלה GeminiAPIError בסוף.
    with pytest.raises(GeminiAPIError):
        # שני ניסיונות נכשלים
        client2 = _make_client_with_responses(
            monkeypatch,
            [_FakeResponse("not json"), _FakeResponse("also not json")],
        )
        await client2.generate("any prompt")


@pytest.mark.asyncio
async def test_client_raises_on_empty_response(monkeypatch) -> None:
    client = _make_client_with_responses(
        monkeypatch,
        [_FakeResponse(""), _FakeResponse("")],
    )
    with pytest.raises(GeminiAPIError):
        await client.generate("any prompt")
