"""פקודת /resume — חידוש התראות."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from app.bot.handlers._helpers import repo_from_context
from app.logging_config import get_logger
from app.utils import anon_user_id

logger = get_logger(__name__)


async def resume_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None or update.message is None:
        return

    logger.info("bot.command.resume", user_hash=anon_user_id(user.id))

    repo = repo_from_context(context)
    if repo is None:
        await update.message.reply_text("⚠️ השירות עדיין מתאתחל. נסה שוב בעוד רגע.")
        return

    ok = await repo.set_paused(user.id, False)
    if not ok:
        await update.message.reply_text("עוד לא נרשמת. שלח /start כדי להתחיל.")
        return

    await update.message.reply_text(
        "▶️ התראות מחודשות. הסיכום הבא יישלח בזמן הרגיל."
    )
