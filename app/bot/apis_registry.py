"""רשימת ה-APIs שמשתמש יכול להירשם אליהם.

מקור האמת היחיד הוא `ALL_SOURCES`, אבל יש לנו 10 instances של מקורות
ורק 9 api_id ייחודיים (WhatsApp Meta ו-Green חולקים api_id="whatsapp").
ה-registry הזה מבצע dedup ושומר על שם תצוגה אחד פר api_id.

לפי הסדר: השם של ה-class הראשון ש-api_id הזה הוקצה אליו זוכה. אם
WhatsAppMetaSource רשום ראשון, הוא יקבע את ה-name_he ל-"whatsapp".
"""

from __future__ import annotations

from dataclasses import dataclass

from app.collectors.registry import ALL_SOURCES


@dataclass(frozen=True)
class SubscribableAPI:
    """מה שמוצג למשתמש בבחירת מנוי."""

    api_id: str
    name_he: str


def _build_registry() -> list[SubscribableAPI]:
    """dedup לפי api_id; שומר על סדר ההופעה ב-ALL_SOURCES."""
    seen: dict[str, SubscribableAPI] = {}
    for source_cls in ALL_SOURCES:
        if source_cls.api_id in seen:
            continue
        seen[source_cls.api_id] = SubscribableAPI(
            api_id=source_cls.api_id,
            name_he=source_cls.name_he,
        )
    return list(seen.values())


SUBSCRIBABLE_APIS: list[SubscribableAPI] = _build_registry()


# מילון לחיפוש מהיר ע"י api_id (נוח ל-validators ב-callbacks).
SUBSCRIBABLE_APIS_BY_ID: dict[str, SubscribableAPI] = {
    api.api_id: api for api in SUBSCRIBABLE_APIS
}


def is_valid_api_id(api_id: str) -> bool:
    """לאימות callback data שמגיע מהמשתמש."""
    return api_id in SUBSCRIBABLE_APIS_BY_ID
