"""בניית ה-Application של python-telegram-bot והרצתו במצב webhook.

הגישה: יוצרים Application אחת, מאתחלים אותה בידיים (initialize/start),
וב-FastAPI route מזריקים updates דרך `application.update_queue`.
זה הדפוס המומלץ ל-PTB 21+ עם webhook מאחורי FastAPI.

ה-UserRepository מוזרק ל-`application.bot_data["user_repository"]`
ב-`app/main.py:lifespan` אחרי החיבור ל-MongoDB. ה-handlers שולפים אותו
דרך `repo_from_context(context)`.
"""

from __future__ import annotations

from telegram.ext import Application, CallbackQueryHandler, CommandHandler

from app.bot.handlers.about import about_handler
from app.bot.handlers.apis import apis_handler
from app.bot.handlers.callbacks import callback_router
from app.bot.handlers.help import help_handler
from app.bot.handlers.pause import pause_handler
from app.bot.handlers.resume import resume_handler
from app.bot.handlers.settings import settings_handler
from app.bot.handlers.severity import severity_handler
from app.bot.handlers.start import start_handler
from app.bot.handlers.stop import stop_handler
from app.bot.handlers.test_weekly import test_weekly_handler
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

    # פקודות
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("help", help_handler))
    application.add_handler(CommandHandler("about", about_handler))
    application.add_handler(CommandHandler("settings", settings_handler))
    application.add_handler(CommandHandler("apis", apis_handler))
    application.add_handler(CommandHandler("severity", severity_handler))
    application.add_handler(CommandHandler("pause", pause_handler))
    application.add_handler(CommandHandler("resume", resume_handler))
    application.add_handler(CommandHandler("stop", stop_handler))
    # פקודת אדמין — הפעלה ידנית של הסיכום השבועי (בודק הרשאה בעצמו).
    application.add_handler(CommandHandler("test_weekly", test_weekly_handler))

    # נתב יחיד לכל לחיצות הכפתורים — מפענח callback_data לפי prefix
    application.add_handler(CallbackQueryHandler(callback_router))

    logger.info(
        "bot.application.built",
        command_handlers=10,
        callback_handlers=1,
    )
    return application
