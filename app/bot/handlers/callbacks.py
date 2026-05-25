"""נתב יחיד לכל ה-CallbackQueryHandler.

מקבל ה-callback_data, מנתח את prefix, ומפעיל את ה-handler המתאים.
פורמטים מתועדים ב-app/bot/keyboards.py:
    api:t:<api_id>   — toggle subscription
    api:done         — finish APIs step → advance to severity
    sev:<level>      — pick severity (advances in flow, or saves only)
    freq:<value>     — pick frequency
    urg:<bool>       — pick urgent preference
    done:final       — final confirm
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from app.bot.apis_registry import is_valid_api_id
from app.bot.handlers._helpers import format_user_summary, repo_from_context
from app.bot.keyboards import (
    build_apis_keyboard,
    build_frequency_keyboard,
    build_severity_keyboard,
    build_urgent_keyboard,
    build_final_confirm_keyboard,
)
from app.logging_config import get_logger
from app.utils import anon_user_id

logger = get_logger(__name__)


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """נקודת כניסה יחידה לכל לחיצות הכפתורים."""
    query = update.callback_query
    if query is None or query.from_user is None:
        return

    # answer מיד כדי שטלגרם יסיר את "טוען..." מהכפתור.
    await query.answer()

    repo = repo_from_context(context)
    if repo is None:
        await query.edit_message_text("⚠️ השירות עדיין מתאתחל.")
        return

    data = query.data or ""
    user_id = query.from_user.id

    logger.info(
        "bot.callback",
        user_hash=anon_user_id(user_id),
        data=data,
    )

    # routing לפי prefix
    if data.startswith("api:t:"):
        await _handle_api_toggle(query, repo, user_id, data[len("api:t:"):])
    elif data == "api:done":
        await _handle_api_done(query, repo, user_id)
    elif data.startswith("sev:"):
        await _handle_severity(query, repo, user_id, data[len("sev:"):])
    elif data.startswith("freq:"):
        await _handle_frequency(query, repo, user_id, data[len("freq:"):])
    elif data.startswith("urg:"):
        await _handle_urgent(query, repo, user_id, data[len("urg:"):])
    elif data == "done:final":
        await _handle_final(query, repo, user_id)
    else:
        logger.warning("bot.callback.unknown", data=data)


# ----- handlers per prefix -----


async def _handle_api_toggle(query, repo, user_id: int, api_id: str) -> None:
    if not is_valid_api_id(api_id):
        logger.warning("bot.callback.invalid_api", api_id=api_id)
        return

    updated = await repo.toggle_subscription(user_id, api_id)
    if updated is None:
        await query.edit_message_text("לא נמצאת במערכת. שלח /start כדי להירשם.")
        return

    # רק עדכון מקלדת — הטקסט נשאר זהה כדי שלא יהיה רעש.
    await query.edit_message_reply_markup(
        reply_markup=build_apis_keyboard(updated.get("subscribed_apis", []))
    )


async def _handle_api_done(query, repo, user_id: int) -> None:
    """סיום שלב בחירת APIs. אם זה הפלואו הראשי — מתקדם ל-severity.
    אם זה /apis (re-pick), מסיים בלי לקדם."""
    doc = await repo.get(user_id)
    if doc is None:
        await query.edit_message_text("לא נמצאת במערכת. שלח /start.")
        return

    selected = doc.get("subscribed_apis", []) or []
    if not selected:
        await query.answer(text="בחר לפחות ספק אחד", show_alert=True)
        return

    # ה-/apis flow מסתיים פה. הפלואו הראשי ממשיך ל-severity.
    # נזהה לפי האם המשתמש כבר הוגדר במלואו (יש subscribed + יש severity).
    # אם הוא בפלואו הראשי, severity שלו עוד דיפולטיבי ("important") אבל
    # זה לא מבדיל. ניתן להבדיל לפי האם זו ההרשמה הראשונה — נשתמש ב-flag
    # "in_initial_setup" שמסומן בכניסה לפלואו. אם לא קיים, זה /apis.
    in_initial = doc.get("in_initial_setup", False)
    if in_initial:
        await repo.set_conversation_state(user_id, "selecting_severity")
        await query.edit_message_text(
            "👍 נבחר. עכשיו <b>מה רמת החומרה המינימלית</b> שתרצה לקבל?",
            parse_mode="HTML",
            reply_markup=build_severity_keyboard(doc.get("min_severity")),
        )
    else:
        await repo.set_conversation_state(user_id, "idle")
        await query.edit_message_text(
            "✅ רשימת הספקים עודכנה. /settings לסיכום."
        )


async def _handle_severity(query, repo, user_id: int, value: str) -> None:
    if value not in {"critical", "important", "all"}:
        return

    doc = await repo.get(user_id)
    if doc is None:
        await query.edit_message_text("לא נמצאת במערכת.")
        return

    in_initial = doc.get("in_initial_setup", False)
    if in_initial:
        updated = await repo.set_conversation_state(
            user_id,
            "selecting_frequency",
            extra={"min_severity": value},
        )
        await query.edit_message_text(
            "👍 עכשיו <b>באיזו תדירות</b>?",
            parse_mode="HTML",
            reply_markup=build_frequency_keyboard(
                (updated or {}).get("frequency", "weekly")
            ),
        )
    else:
        await repo.update_settings(user_id, min_severity=value)
        await repo.set_conversation_state(user_id, "idle")
        await query.edit_message_text(
            f"✅ רמת החומרה עודכנה ל-<b>{value}</b>. /settings לסיכום.",
            parse_mode="HTML",
        )


async def _handle_frequency(query, repo, user_id: int, value: str) -> None:
    if value != "weekly":
        return  # כרגע רק שבועי

    doc = await repo.get(user_id)
    if doc is None:
        return

    await repo.set_conversation_state(
        user_id, "confirming", extra={"frequency": value}
    )
    await query.edit_message_text(
        "👍 שלב אחרון: <b>האם לקבל התראה מיידית</b> כשמשהו דחוף קורה "
        "(לדוגמה deprecation שתופס לתוקף תוך כמה ימים)?",
        parse_mode="HTML",
        reply_markup=build_urgent_keyboard(doc.get("receive_urgent_alerts")),
    )


async def _handle_urgent(query, repo, user_id: int, value: str) -> None:
    receive = value == "1"
    updated = await repo.set_conversation_state(
        user_id, "confirming", extra={"receive_urgent_alerts": receive}
    )
    if updated is None:
        return

    summary = format_user_summary(updated)
    await query.edit_message_text(
        f"{summary}\n\nלאישור סופי:",
        parse_mode="HTML",
        reply_markup=build_final_confirm_keyboard(),
    )


async def _handle_final(query, repo, user_id: int) -> None:
    """סיום פלואו ההרשמה — מנקה את הflag הזמני ומחזיר ל-idle."""
    updated = await repo.set_conversation_state(
        user_id, "idle", extra={"in_initial_setup": False}
    )
    if updated is None:
        return

    await query.edit_message_text(
        "🚀 הכל מוכן! נשלח לך את הסיכום הראשון ביום ראשון בבוקר. "
        "אם משהו דחוף יקרה לפני זה — נדע.\n\n"
        "שינוי הגדרות: /settings",
    )
