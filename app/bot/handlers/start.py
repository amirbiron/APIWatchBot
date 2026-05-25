"""פקודת /start — פלואו הרשמה אינטראקטיבי מלא (Spec §7.2).

מתחיל מבחירת APIs ועובר דרך severity → frequency → urgent → סיום.
ה-state נשמר ב-`User.conversation_state` כדי שיציץ גם אחרי restart.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from app.bot.handlers._helpers import format_user_summary, repo_from_context
from app.bot.keyboards import build_apis_keyboard
from app.logging_config import get_logger
from app.utils import anon_user_id

logger = get_logger(__name__)


_WELCOME_NEW = (
    "👋 ברוך הבא ל-<b>APIWatchBot</b>!\n\n"
    "אעקוב בשבילך אחרי שינויים ב-API-ים שמעניינים אותך ואשלח רק מה שחשוב.\n\n"
    "בוא נגדיר. <b>בחר אילו ספקים לעקוב</b> — לחץ על שורה כדי לסמן/לבטל, "
    "ובסיום על <b>סיום</b>:"
)


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None or update.message is None:
        return

    logger.info("bot.command.start", user_hash=anon_user_id(user.id))

    repo = repo_from_context(context)
    if repo is None:
        await update.message.reply_text("⚠️ השירות עדיין מתאתחל. נסה שוב בעוד רגע.")
        return

    doc, created = await repo.get_or_create(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
        language_code=user.language_code,
    )

    if not created and doc.get("subscribed_apis"):
        # משתמש קיים שכבר הגדיר את עצמו — welcome back + סיכום
        summary = format_user_summary(doc)
        await update.message.reply_text(
            f"👋 ברוך השב!\n\n{summary}\n\n"
            "שינוי הגדרות: /settings",
            parse_mode="HTML",
        )
        return

    # משתמש חדש (או קיים אבל בלי מנויים — חוזרים לתחילת הפלואו).
    # ה-flag `in_initial_setup` מאפשר ל-callback router להבחין בין הפלואו
    # הראשי (שמתקדם אוטומטית לשלבים הבאים) לבין /apis ו-/severity
    # (שמסיימים מיד אחרי בחירה).
    await repo.set_conversation_state(
        user.id,
        "selecting_apis",
        extra={"in_initial_setup": True},
    )
    await update.message.reply_text(
        _WELCOME_NEW,
        parse_mode="HTML",
        reply_markup=build_apis_keyboard(doc.get("subscribed_apis", [])),
    )
