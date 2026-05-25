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

    # סדר הבדיקות חשוב: error קודם (db_error / unexpected) — אחרת
    # users_checked=0 בעקבות כשל DB היה נראה כמו "משתמש לא נמצא".
    if summary.error == "db_error":
        await update.message.reply_text(
            "⚠️ שגיאת DB בעת טעינת המשתמש. בדוק לוגים."
        )
        return

    if summary.error == "unexpected":
        await update.message.reply_text(
            "❌ שגיאה לא-צפויה בזמן הריצה. ייתכן שיש claims תקועים "
            "ב-deliveries — בדוק לוגים לפני ניסיון חוזר."
        )
        return

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
        return

    if summary.send_failures > 0:
        # send_failures מוגדל רק במסלול שבו _dispatch_for_user תפס כשל
        # שליחה ושחרר claims בעצמו. חריגות לא-צפויות יוצאות במסלול error.
        await update.message.reply_text(
            "❌ ניסיון השליחה נכשל. ה-claims שוחררו — אפשר לנסות שוב."
        )
        return

    # אין מה לשלוח — מסבירים *למה* על בסיס ה-diagnostics.
    diag = summary.diagnostics or {}
    if diag.get("subscribed_count", 0) == 0:
        reason = "אין לך מנויים על אף API. שלח /apis כדי להירשם."
    elif diag.get("candidates", 0) == 0:
        # אם ה-counters נכשלו (או לא רצו) — לא ננחש; נציג "לא ידוע".
        if diag.get("counters_failed") or "total_for_subscriptions" not in diag:
            sub_reason = (
                "לא הצלחנו לאסוף counters נוספים לאבחון — בדוק לוגים "
                "(weekly.diag.counters_failed)."
            )
        else:
            total = diag["total_for_subscriptions"]
            in_window = diag["in_window_any_status"]
            raw_in_window = diag["raw_in_window"]
            if total == 0:
                sub_reason = (
                    "אין בכלל records ב-updates למנויים שלך — ה-collector "
                    "כנראה לא רץ עדיין (או שאין שינויים upstream)."
                )
            elif in_window == 0:
                sub_reason = (
                    f"יש {total} records היסטוריים אבל אף אחד לא ב-7 ימים "
                    f"האחרונים — אין שינויים upstream לאחרונה."
                )
            elif raw_in_window > 0:
                sub_reason = (
                    f"יש {raw_in_window} עדכונים ב-status=raw מהשבוע — "
                    f"ה-AI processor עדיין לא עיבד אותם (בדוק GEMINI_API_KEY "
                    f"ואת job 'process_ai_batch' ב-worker)."
                )
            else:
                sub_reason = (
                    f"יש {in_window} עדכונים מהשבוע אבל אף אחד עם "
                    f"status=processed וגם severity מתאימה — ייתכן שכולם "
                    f"skipped_noise/failed או שה-severity לא תואמת."
                )
        reason = (
            f"חלון: 7 ימים אחורה מעכשיו (לא מההרשמה).\n"
            f"מנויים: {diag.get('subscribed_count')} | "
            f"severity: {diag.get('min_severity')} | candidates: 0.\n\n"
            f"{sub_reason}"
        )
    elif diag.get("new_items", 0) == 0:
        reason = (
            f"כל ה-{diag.get('candidates')} העדכונים שתואמים כבר נשלחו "
            f"אליך (deliveries dedup).\n"
            f"already_delivered: {diag.get('already_delivered')}."
        )
    elif diag.get("claimed", 0) == 0:
        reason = (
            f"היו {diag.get('new_items')} פריטים חדשים אבל כולם נתפסו "
            f"בינתיים ע\"י תהליך אחר (race עם urgent/cron)."
        )
    else:
        # claimed>0 אבל digests_sent==0 — כנראה build_weekly_digest החזיר None.
        reason = (
            f"נתפסו {diag.get('claimed')} פריטים אבל ה-digest לא נבנה "
            f"(build_weekly_digest החזיר None). בדוק לוגים."
        )

    await update.message.reply_text(f"ℹ️ אין מה לשלוח.\n\n{reason}")
