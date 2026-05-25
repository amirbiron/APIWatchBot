"""פונקציות עזר משותפות ל-handlers."""

from __future__ import annotations

import html
from typing import Any

from telegram.ext import ContextTypes

from app.bot.apis_registry import SUBSCRIBABLE_APIS_BY_ID
from app.bot.user_repository import UserRepository

# שמות תצוגה לרמות severity (התאמה למקלדת).
_SEVERITY_LABELS = {
    "critical": "🔴 רק קריטי",
    "important": "🟡 חשוב ומעלה",
    "all": "🟢 הכל",
}

_FREQ_LABELS = {
    "weekly": "📅 שבועי",
}


def repo_from_context(context: ContextTypes.DEFAULT_TYPE) -> UserRepository | None:
    """מחלץ UserRepository מ-bot_data. None אם עוד לא הוזרק (startup partial)."""
    return context.bot_data.get("user_repository")


def format_user_summary(user_doc: dict[str, Any]) -> str:
    """סיכום HTML של ההגדרות של המשתמש — למסך welcome-back ולסיום פלואו."""
    subscribed_ids = user_doc.get("subscribed_apis", []) or []
    names = [
        html.escape(SUBSCRIBABLE_APIS_BY_ID[a].name_he)
        for a in subscribed_ids
        if a in SUBSCRIBABLE_APIS_BY_ID
    ]
    apis_line = ", ".join(names) if names else "— אין —"

    severity_label = _SEVERITY_LABELS.get(
        user_doc.get("min_severity", "important"), "—"
    )
    freq_label = _FREQ_LABELS.get(user_doc.get("frequency", "weekly"), "—")
    urgent = "כן" if user_doc.get("receive_urgent_alerts", True) else "לא"
    paused_note = "\n⏸️ <i>התראות מושהות כרגע (/resume לחידוש)</i>" if user_doc.get(
        "paused"
    ) else ""

    return (
        f"<b>הגדרות נוכחיות</b>\n"
        f"• ספקים: {apis_line}\n"
        f"• רמת חומרה: {severity_label}\n"
        f"• תדירות: {freq_label}\n"
        f"• התראות דחופות: {urgent}"
        f"{paused_note}"
    )
