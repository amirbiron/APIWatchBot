"""בוני InlineKeyboardMarkup לפלואו הרישום ולפקודות /apis ו-/severity.

callback_data format (קומפקטי כי Telegram מגביל ל-64 בייט):
    api:t:<api_id>   — toggle של ה-API ברשימת המנויים
    api:done         — סיום שלב בחירת APIs
    sev:<level>      — בחירת severity (critical/important/all)
    freq:<value>     — בחירת תדירות (לעת עתה רק weekly)
    urg:<bool>       — אישור התראות דחופות (1/0)
    done:final       — אישור סופי בסוף הפלואו
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.apis_registry import SUBSCRIBABLE_APIS

# סמלים לציון בחירה במקלדת.
_CHECKED = "✅"
_UNCHECKED = "⬜"


def build_apis_keyboard(subscribed_apis: list[str]) -> InlineKeyboardMarkup:
    """מקלדת בחירת APIs. לחיצה על שורה = toggle. בסוף יש כפתור "סיום"."""
    subscribed = set(subscribed_apis)
    rows: list[list[InlineKeyboardButton]] = []
    for api in SUBSCRIBABLE_APIS:
        mark = _CHECKED if api.api_id in subscribed else _UNCHECKED
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{mark} {api.name_he}",
                    callback_data=f"api:t:{api.api_id}",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="✔️ סיום", callback_data="api:done")]
    )
    return InlineKeyboardMarkup(rows)


def build_severity_keyboard(current: str | None = None) -> InlineKeyboardMarkup:
    """3 כפתורים לרמת חומרה מינימלית. הנוכחי מסומן ב-•."""
    options = [
        ("critical", "🔴 רק קריטי"),
        ("important", "🟡 חשוב ומעלה"),
        ("all", "🟢 הכל"),
    ]
    rows = [
        [
            InlineKeyboardButton(
                text=f"• {label}" if value == current else label,
                callback_data=f"sev:{value}",
            )
        ]
        for value, label in options
    ]
    return InlineKeyboardMarkup(rows)


def build_frequency_keyboard(current: str | None = None) -> InlineKeyboardMarkup:
    """כרגע רק שבועי פעיל. יומי יתווסף בעתיד (Spec §11)."""
    rows = [
        [
            InlineKeyboardButton(
                text=("• 📅 סיכום שבועי" if current == "weekly" else "📅 סיכום שבועי"),
                callback_data="freq:weekly",
            )
        ],
    ]
    return InlineKeyboardMarkup(rows)


def build_urgent_keyboard(current: bool | None = None) -> InlineKeyboardMarkup:
    """כן/לא להתראות דחופות."""
    yes_text = "• ✅ כן" if current is True else "✅ כן"
    no_text = "• ❌ לא" if current is False else "❌ לא"
    rows = [
        [
            InlineKeyboardButton(text=yes_text, callback_data="urg:1"),
            InlineKeyboardButton(text=no_text, callback_data="urg:0"),
        ]
    ]
    return InlineKeyboardMarkup(rows)


def build_final_confirm_keyboard() -> InlineKeyboardMarkup:
    """אישור סופי בסוף פלואו הרישום."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(text="🚀 סיים והפעל", callback_data="done:final")]]
    )
