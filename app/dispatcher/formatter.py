"""בונה הודעות HTML למשתמש (urgent + weekly digest).

עיקרון: כל ערך שמגיע מ-DB/AI עובר html.escape *לפני* ההטמעה (כלל 6
ב-CLAUDE.md). ה-tags של עיצוב (`<b>`, `<a>`) נשארים פעילים.
"""

from __future__ import annotations

import html
from datetime import datetime
from typing import Any

from app.bot.apis_registry import SUBSCRIBABLE_APIS_BY_ID
from app.logging_config import get_logger

logger = get_logger(__name__)

# מקסימום אורך הודעה בטלגרם.
MAX_TELEGRAM_MESSAGE_LEN = 4096

# סדר התצוגה של הקטגוריות בסיכום השבועי.
_SEVERITY_DISPLAY: list[tuple[str, str, str]] = [
    ("critical", "🔴", "קריטי"),
    ("important", "🟡", "חשוב"),
    ("info", "🟢", "מידע"),
]

_DIVIDER = "━━━━━━━━━━━━━━━"


def _api_display_name(api_id: str) -> str:
    """ה-name_he מה-registry. fallback ל-api_id אם לא ידוע."""
    api = SUBSCRIBABLE_APIS_BY_ID.get(api_id)
    return api.name_he if api else api_id


def _format_update_line(update: dict[str, Any]) -> str:
    """שורת פריט בסיכום השבועי."""
    api_name = html.escape(_api_display_name(update.get("api_id", "")))
    summary = html.escape((update.get("summary_he") or "").strip())
    url = html.escape(update.get("source_url", ""))
    return (
        f"▪️ <b>{api_name}</b>: {summary}\n"
        f'🔗 <a href="{url}">פרטים</a>'
    )


def build_urgent_message(update: dict[str, Any]) -> str:
    """הודעת התראה דחופה — Spec §7.4."""
    api_name = html.escape(_api_display_name(update.get("api_id", "")))
    summary = html.escape((update.get("summary_he") or "").strip())
    url = html.escape(update.get("source_url", ""))

    return (
        f"⚠️ <b>התראה דחופה — {api_name}</b>\n\n"
        f"{summary}\n\n"
        f'🔗 <a href="{url}">פרטים</a>'
    )


def build_weekly_digest(
    updates: list[dict[str, Any]],
    *,
    date_range: str,
) -> str | None:
    """סיכום שבועי — Spec §7.3. מחזיר None אם אין פריטים בכלל.

    `updates` כבר מסונן לפי subscribed_apis ו-min_severity של המשתמש.
    """
    if not updates:
        return None

    # קיבוץ לפי severity
    by_severity: dict[str, list[dict[str, Any]]] = {
        "critical": [],
        "important": [],
        "info": [],
    }
    for u in updates:
        sev = u.get("severity")
        if sev in by_severity:
            by_severity[sev].append(u)

    parts: list[str] = [
        f"📡 <b>סיכום שבועי — APIWatchBot</b>",
        html.escape(date_range),
        "",
    ]

    for sev_key, emoji, label in _SEVERITY_DISPLAY:
        items = by_severity[sev_key]
        if not items:
            continue
        parts.append(f"{emoji} <b>{label}</b>")
        parts.append(_DIVIDER)
        parts.append("")
        for item in items:
            parts.append(_format_update_line(item))
            parts.append("")

    parts.append(_DIVIDER)
    parts.append("💡 שינוי הגדרות: /settings")

    return "\n".join(parts)


def split_long_message(
    message: str,
    *,
    max_len: int = MAX_TELEGRAM_MESSAGE_LEN,
) -> list[str]:
    """מפצל הודעה ארוכה לחלקים שאינם עוברים את ה-limit.

    אסטרטגיה:
    1. אם בסדר — מחזיר רשימה של 1 איבר.
    2. ניסיון לחתוך בגבולות "ריקות" — שורה כפולה.
    3. fallback hard split על תווים אם אין breakpoint סביר.

    כל חלק עומד בעצמו (HTML tags לא יישברו) — אנחנו חותכים רק על
    גבולות שורה ולא בתוך tag.
    """
    if len(message) <= max_len:
        return [message]

    chunks: list[str] = []
    remaining = message

    while len(remaining) > max_len:
        # חפש גבול שורה כפולה (סקציה) הכי קרוב מהסוף
        candidate = remaining[:max_len]
        split_at = candidate.rfind("\n\n")
        if split_at == -1 or split_at < max_len // 2:
            # אין break סביר — נסה שורה רגילה
            split_at = candidate.rfind("\n")
        if split_at == -1 or split_at < max_len // 2:
            # ממש אין — חיתוך קשה
            split_at = max_len

        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()

    if remaining:
        chunks.append(remaining)

    return chunks


def format_date_range(start: datetime, end: datetime) -> str:
    """`24-30 במאי 2026` — תואם דוגמה מ-Spec §7.3."""
    months_he = {
        1: "ינואר", 2: "פברואר", 3: "מרץ", 4: "אפריל",
        5: "מאי", 6: "יוני", 7: "יולי", 8: "אוגוסט",
        9: "ספטמבר", 10: "אוקטובר", 11: "נובמבר", 12: "דצמבר",
    }
    if start.month == end.month and start.year == end.year:
        return f"{start.day}-{end.day} ב{months_he[end.month]} {end.year}"
    # cross-month: "24 במאי - 2 ביוני 2026"
    # אם חצינו שנה (לדוגמה 28 בדצמבר → 4 בינואר), חשוב להציג את שתי
    # השנים כדי שלא נוצר רושם של "פער של שנה" שגוי.
    if start.year != end.year:
        return (
            f"{start.day} ב{months_he[start.month]} {start.year} - "
            f"{end.day} ב{months_he[end.month]} {end.year}"
        )
    return (
        f"{start.day} ב{months_he[start.month]} - "
        f"{end.day} ב{months_he[end.month]} {end.year}"
    )
