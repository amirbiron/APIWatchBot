"""פקודת /start — בשלב 1: הודעת ברוכים הבאים סטטית בלבד.

הפלואו האינטראקטיבי המלא (בחירת APIs, רמת חומרה, תדירות) ייבנה בשלב 4.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from app.logging_config import get_logger

logger = get_logger(__name__)


WELCOME_MESSAGE = (
    "👋 ברוך הבא ל-<b>APIWatchBot</b>!\n\n"
    "אני בוט שעוקב בשבילך אחרי עדכונים מ-10 ספקי API פופולריים, "
    "ושולח לך סיכום בעברית רק על מה שמעניין אותך.\n\n"
    "🚧 כרגע אני בשלבי בנייה. הפקודות יתווספו בקרוב:\n"
    "• /settings — הגדרות אישיות\n"
    "• /apis — בחירת ספקים\n"
    "• /pause — השהיית התראות\n"
    "• /help — עזרה\n\n"
    "תודה על הסבלנות 🙏"
)


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """תגובה ל-/start. כרגע סטטית."""
    user = update.effective_user
    if user is None or update.message is None:
        return

    logger.info(
        "bot.command.start",
        telegram_id=user.id,
        username=user.username,
    )

    await update.message.reply_text(
        WELCOME_MESSAGE,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
