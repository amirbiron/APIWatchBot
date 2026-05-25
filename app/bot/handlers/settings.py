"""פקודת /settings — תפריט טקסט שמראה הגדרות ומציע פקודות שינוי."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from app.bot.handlers._helpers import format_user_summary, repo_from_context
from app.logging_config import get_logger
from app.utils import anon_user_id

logger = get_logger(__name__)


_MENU = (
    "\n\n<b>פעולות זמינות</b>\n"
    "• /apis — שינוי רשימת ספקים\n"
    "• /severity — שינוי רמת חומרה\n"
    "• /pause — השהיית התראות\n"
    "• /resume — חידוש התראות\n"
    "• /stop — מחיקת המשתמש מהמערכת\n"
    "• /help — עזרה כללית"
)


async def settings_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None or update.message is None:
        return

    logger.info("bot.command.settings", user_hash=anon_user_id(user.id))

    repo = repo_from_context(context)
    if repo is None:
        await update.message.reply_text("⚠️ השירות עדיין מתאתחל. נסה שוב בעוד רגע.")
        return

    doc = await repo.get(user.id)
    if doc is None:
        await update.message.reply_text(
            "עוד לא נרשמת. שלח /start כדי להתחיל."
        )
        return

    await update.message.reply_text(
        f"{format_user_summary(doc)}{_MENU}",
        parse_mode="HTML",
    )
