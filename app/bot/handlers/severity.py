"""פקודת /severity — הצגת מקלדת בחירת רמת חומרה לעריכה."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from app.bot.handlers._helpers import repo_from_context
from app.bot.keyboards import build_severity_keyboard
from app.logging_config import get_logger
from app.utils import anon_user_id

logger = get_logger(__name__)


async def severity_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None or update.message is None:
        return

    logger.info("bot.command.severity", user_hash=anon_user_id(user.id))

    repo = repo_from_context(context)
    if repo is None:
        await update.message.reply_text("⚠️ השירות עדיין מתאתחל. נסה שוב בעוד רגע.")
        return

    doc = await repo.get(user.id)
    if doc is None:
        await update.message.reply_text("עוד לא נרשמת. שלח /start כדי להתחיל.")
        return

    # מצב מיוחד — re-pick של severity מחוץ לפלואו הראשי. ה-callback handler
    # מזהה את הסיטואציה לפי conversation_state ולא מקדם אוטומטית לשלב הבא.
    await repo.set_conversation_state(user.id, "selecting_severity")
    await update.message.reply_text(
        "בחר רמת חומרה מינימלית:",
        reply_markup=build_severity_keyboard(doc.get("min_severity")),
    )
