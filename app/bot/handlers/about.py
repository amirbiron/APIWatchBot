"""פקודת /about — תיאור קצר של הבוט."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from app.logging_config import get_logger
from app.utils import anon_user_id

logger = get_logger(__name__)

_ABOUT = (
    "🤖 <b>APIWatchBot</b>\n\n"
    "בוט שעוקב אחרי שינויים ב-API-ים של 10 ספקים פופולריים, מסכם בעברית, "
    "ושולח לך רק את מה שמעניין אותך — בתדירות שאתה בוחר.\n\n"
    "פיתוח: <a href=\"https://github.com/amirbiron/APIWatchBot\">amirbiron/APIWatchBot</a>"
)


async def about_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None or update.message is None:
        return

    logger.info("bot.command.about", user_hash=anon_user_id(user.id))
    await update.message.reply_text(
        _ABOUT,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
