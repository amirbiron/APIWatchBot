"""בניית ה-Application של python-telegram-bot והרצתו במצב webhook.

הגישה: יוצרים Application אחת, מאתחלים אותה בידיים (initialize/start),
וב-FastAPI route מזריקים updates דרך `application.update_queue`.
זה הדפוס המומלץ ל-PTB 21+ עם webhook מאחורי FastAPI.
"""

from __future__ import annotations

from telegram.ext import Application, CommandHandler

from app.bot.handlers.help import help_handler
from app.bot.handlers.start import start_handler
from app.config import get_settings
from app.logging_config import get_logger

logger = get_logger(__name__)


def build_application() -> Application:
    """בונה Application עם כל ה-handlers — בלי להפעיל network."""
    settings = get_settings()
    token = settings.telegram_bot_token.get_secret_value()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN חסר — לא ניתן לבנות את הבוט.")

    application = (
        Application.builder()
        .token(token)
        # ל-webhook mode אין צורך ב-Updater (חוסך משאבים)
        .updater(None)
        .build()
    )

    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("help", help_handler))

    logger.info("bot.application.built", handlers=2)
    return application
