"""פקודת /help — רשימת הפקודות הזמינות."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from app.logging_config import get_logger
from app.utils import anon_user_id

logger = get_logger(__name__)


HELP_MESSAGE = (
    "📖 <b>עזרה — APIWatchBot</b>\n\n"
    "<b>התחלה</b>\n"
    "• /start — הרשמה / חזרה לדף הבית\n"
    "• /about — על הבוט\n\n"
    "<b>הגדרות</b>\n"
    "• /settings — הצגת ההגדרות הנוכחיות\n"
    "• /apis — שינוי רשימת ספקים מנויים\n"
    "• /severity — שינוי רמת חומרה מינימלית\n\n"
    "<b>שליטה בהתראות</b>\n"
    "• /pause — השהיית התראות\n"
    "• /resume — חידוש התראות\n"
    "• /stop — מחיקת המשתמש מהמערכת\n\n"
    "❓ שאלות? פתחו issue ב-GitHub."
)


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None or update.message is None:
        return

    logger.info("bot.command.help", user_hash=anon_user_id(user.id))

    await update.message.reply_text(
        HELP_MESSAGE,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
