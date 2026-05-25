"""פקודת אדמין /test_weekly — הפעלה ידנית של לוגיקת הסיכום השבועי.

רץ רק עבור ה-telegram_id של האדמין (settings.admin_telegram_id).
משתמש באותו pipeline של WeeklyDispatcher.run — כולל dedup דרך
deliveries, claim, send, release on failure — כדי שלא יהיה הפרש
התנהגות בין הריצה הידנית לזו של ה-cron.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from app.config import get_settings
from app.db.client import get_db
from app.dispatcher.sender import TelegramSender
from app.dispatcher.weekly import WeeklyDispatcher
from app.logging_config import get_logger
from app.utils import anon_user_id

logger = get_logger(__name__)


async def test_weekly_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    user = update.effective_user
    if user is None or update.message is None:
        return

    settings = get_settings()
    admin_id = settings.admin_telegram_id

    # הגנת הרשאה — לא חושפים שהפקודה קיימת למי שלא אדמין.
    if admin_id is None or user.id != admin_id:
        logger.warning(
            "bot.command.test_weekly.unauthorized",
            user_hash=anon_user_id(user.id),
        )
        return

    logger.info("bot.command.test_weekly", user_hash=anon_user_id(user.id))

    token = settings.telegram_bot_token.get_secret_value()
    if not token:
        await update.message.reply_text("⚠️ הבוט לא מוגדר נכון (חסר token).")
        return

    try:
        db = get_db()
    except Exception:
        logger.exception("bot.command.test_weekly.db_unavailable")
        await update.message.reply_text("⚠️ ה-DB לא זמין כרגע.")
        return

    await update.message.reply_text("⏳ מריץ סיכום שבועי ידני…")

    sender = TelegramSender(token)
    try:
        dispatcher = WeeklyDispatcher(db, sender)
        summary = await dispatcher.run_for_telegram_id(admin_id)
    finally:
        await sender.close()

    if summary.users_checked == 0:
        await update.message.reply_text(
            "ℹ️ לא נמצא משתמש עם ה-telegram_id הזה ב-DB."
        )
        return

    if summary.digests_sent > 0:
        await update.message.reply_text(
            "✅ הסיכום נשלח. (שים לב: הפריטים סומנו ב-deliveries — "
            "ה-cron הקרוב לא יחזור עליהם.)"
        )
    elif summary.send_failures > 0:
        await update.message.reply_text(
            "❌ ניסיון השליחה נכשל. ה-claims שוחררו — אפשר לנסות שוב."
        )
    else:
        await update.message.reply_text(
            "ℹ️ אין עדכונים חדשים לשלוח (כל הפריטים נשלחו כבר או שאין מה לסכם)."
        )
