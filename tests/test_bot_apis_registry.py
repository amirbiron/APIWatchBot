"""בדיקות ל-app/bot/apis_registry.py."""

from __future__ import annotations

from app.bot.apis_registry import (
    SUBSCRIBABLE_APIS,
    SUBSCRIBABLE_APIS_BY_ID,
    is_valid_api_id,
)


def test_registry_dedupes_by_api_id() -> None:
    """WhatsApp Meta + Green חולקים api_id='whatsapp' — צריך להופיע פעם אחת."""
    api_ids = [api.api_id for api in SUBSCRIBABLE_APIS]
    assert len(api_ids) == len(set(api_ids))


def test_registry_includes_expected_apis() -> None:
    """כל ה-9 הצפויים. אם מוסיפים מקור חדש או מסירים — מעדכנים פה."""
    api_ids = {api.api_id for api in SUBSCRIBABLE_APIS}
    expected = {
        "render",
        "openai",
        "twilio",
        "telegram",
        "stripe",
        "google_business",
        "google_gemini",
        "meta_graph",
        "whatsapp",
    }
    assert api_ids == expected


def test_registry_has_hebrew_names() -> None:
    """כל API צריך name_he לא ריק."""
    for api in SUBSCRIBABLE_APIS:
        assert api.name_he, f"API {api.api_id} בלי name_he"


def test_by_id_lookup() -> None:
    assert SUBSCRIBABLE_APIS_BY_ID["openai"].name_he == "OpenAI"
    # WhatsApp — לוקח את ה-name_he של הראשון ברישום (Meta)
    assert "WhatsApp" in SUBSCRIBABLE_APIS_BY_ID["whatsapp"].name_he


def test_is_valid_api_id() -> None:
    assert is_valid_api_id("openai") is True
    assert is_valid_api_id("nope") is False
    assert is_valid_api_id("") is False
