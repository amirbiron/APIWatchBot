"""פקודת /stop — מחיקה מלאה של המשתמש מהמערכת (Spec §7.1)."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from app.bot.handlers._helpers import repo_from_context
from app.logging_config import get_logger
from app.utils import anon_user_id

logger = get_logger(__name__)


async def stop_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None or update.message is None:
        return

    logger.info("bot.command.stop", user_hash=anon_user_id(user.id))

    repo = repo_from_context(context)
    if repo is None:
        await update.message.reply_text("⚠️ השירות עדיין מתאתחל. נסה שוב בעוד רגע.")
        return

    deleted = await repo.delete(user.id)
    if not deleted:
        await update.message.reply_text("לא נמצאת רשום במערכת.")
        return

    await update.message.reply_text(
        "🗑️ נמחקת מהמערכת. אם תרצה לחזור, פשוט שלח /start."
    )
