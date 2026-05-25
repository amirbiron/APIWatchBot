"""פקודת /apis — הצגת מקלדת בחירת APIs לעריכה מחדש."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from app.bot.handlers._helpers import repo_from_context
from app.bot.keyboards import build_apis_keyboard
from app.logging_config import get_logger
from app.utils import anon_user_id

logger = get_logger(__name__)


async def apis_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None or update.message is None:
        return

    logger.info("bot.command.apis", user_hash=anon_user_id(user.id))

    repo = repo_from_context(context)
    if repo is None:
        await update.message.reply_text("⚠️ השירות עדיין מתאתחל. נסה שוב בעוד רגע.")
        return

    doc = await repo.get(user.id)
    if doc is None:
        await update.message.reply_text("עוד לא נרשמת. שלח /start כדי להתחיל.")
        return

    # מצב חוזר מאפשר שימוש חוזר באותו toggle handler.
    await repo.set_conversation_state(user.id, "selecting_apis")
    await update.message.reply_text(
        "בחר ספקים — לחץ על שורה כדי לסמן/לבטל, ובסיום על <b>סיום</b>:",
        parse_mode="HTML",
        reply_markup=build_apis_keyboard(doc.get("subscribed_apis", [])),
    )
