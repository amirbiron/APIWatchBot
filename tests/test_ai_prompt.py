"""בדיקות לפרומפט ול-schema של ה-AI Layer."""

from __future__ import annotations

from app.ai.prompt import RESPONSE_SCHEMA, build_prompt


def test_build_prompt_includes_all_fields() -> None:
    """כל שדות ה-item חייבים להיות מוטמעים בפרומפט — אחרת ה-AI יסכם
    על בסיס חלקי."""
    prompt = build_prompt(
        api_name="openai",
        raw_title="Deprecation of gpt-3.5-turbo-0301",
        raw_content="The model will be removed on June 13, 2026.",
        source_url="https://example.com/changelog/foo",
    )

    assert "openai" in prompt
    assert "Deprecation of gpt-3.5-turbo-0301" in prompt
    assert "June 13, 2026" in prompt
    assert "https://example.com/changelog/foo" in prompt


def test_build_prompt_is_in_hebrew() -> None:
    """ה-prompt חייב להיות בעברית כדי לכוון את המודל לפלט עברי."""
    prompt = build_prompt(
        api_name="x", raw_title="t", raw_content="c", source_url="https://x"
    )
    # מספיק לחפש מילה עברית נפוצה
    assert "עברית" in prompt


def test_response_schema_required_fields() -> None:
    """כל השדות שה-processor מצפה אליהם חייבים להיות ב-required."""
    required = set(RESPONSE_SCHEMA["required"])
    expected = {"is_noise", "summary_he", "severity", "is_urgent", "categories"}
    assert required == expected


def test_response_schema_severity_enum_matches_update_model() -> None:
    """ערכי ה-severity בschema חייבים להתאים ל-UpdateSeverity במודלים."""
    severity_enum = set(RESPONSE_SCHEMA["properties"]["severity"]["enum"])
    assert severity_enum == {"critical", "important", "info"}


def test_response_schema_categories_enum_complete() -> None:
    """ה-categories חייב לכלול את כל הטיפוסים מ-Spec §4.2."""
    cats = set(RESPONSE_SCHEMA["properties"]["categories"]["items"]["enum"])
    expected = {
        "deprecation",
        "breaking",
        "new_feature",
        "pricing",
        "security",
        "bugfix",
        "performance",
    }
    assert cats == expected
