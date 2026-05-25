"""FastAPI entrypoint — מאחד את חיבור ה-DB ואת ה-webhook של טלגרם בתהליך אחד."""

from __future__ import annotations

import hmac
from contextlib import asynccontextmanager
from http import HTTPStatus
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Request, Response
from telegram import Update
from telegram.ext import Application

from app.bot.application import build_application
from app.config import Settings, get_settings
from app.db.client import close_mongo_connection, connect_to_mongo
from app.db.indexes import ensure_indexes
from app.logging_config import configure_logging, get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """מנהל את מחזור החיים: startup → yield → shutdown.

    חשוב: כל רכישת משאב מתבצעת בתוך ה-try, ומסומנת ב-flag נפרד. אם
    שלב מתקדם בתהליך ה-startup נכשל (למשל register_webhook אחרי שכבר
    הפעלנו את ה-bot processor), ה-finally עדיין רץ ומשחרר כל מה שנתפס
    בפועל — אין משאב שדולף וה-process יכול לצאת נקי.
    """
    settings = get_settings()
    configure_logging(
        level=settings.log_level,
        json_output=settings.environment != "development",
    )
    logger.info("app.startup", environment=settings.environment)

    bot_app: Application | None = None
    # flags שמתעדים בדיוק מה הצליח, כדי שה-cleanup יעשה רק את מה שצריך
    mongo_connected = False
    bot_initialized = False
    bot_started = False

    # שומרים גם במצב התחלתי כדי שה-route יקבל ערך גם אם startup נכשל מוקדם
    app.state.bot_app = None
    app.state.settings = settings

    try:
        # MongoDB — אופציונלי בפיתוח. בפרוד חייב לעבוד.
        if settings.mongodb_configured:
            db = await connect_to_mongo()
            mongo_connected = True
            await ensure_indexes(db)
        else:
            logger.warning("app.startup.mongo.skipped", reason="MONGODB_URI חסר")

        # Telegram bot — גם אופציונלי בפיתוח.
        if settings.telegram_configured:
            bot_app = build_application()
            await bot_app.initialize()
            bot_initialized = True
            await bot_app.start()
            bot_started = True
            await _register_webhook(bot_app, settings)
            app.state.bot_app = bot_app
        else:
            logger.warning("app.startup.telegram.skipped", reason="TELEGRAM_BOT_TOKEN חסר")

        yield
    finally:
        logger.info("app.shutdown")

        # שחרור משאבים בסדר הפוך לרכישה. כל שלב עטוף בנפרד כדי שכשל
        # באחד לא ימנע ניקוי של האחרים.
        if bot_started and bot_app is not None:
            try:
                await bot_app.stop()
            except Exception:
                logger.exception("app.shutdown.bot_stop_failed")
        if bot_initialized and bot_app is not None:
            try:
                await bot_app.shutdown()
            except Exception:
                logger.exception("app.shutdown.bot_shutdown_failed")
        if mongo_connected:
            try:
                await close_mongo_connection()
            except Exception:
                logger.exception("app.shutdown.mongo_close_failed")


async def _register_webhook(bot_app: Application, settings: Settings) -> None:
    """רישום webhook מול Telegram — רק אם יש לנו URL ציבורי."""
    webhook_url = settings.telegram_webhook_url
    if not webhook_url:
        logger.warning(
            "telegram.webhook.skipped",
            reason="TELEGRAM_WEBHOOK_BASE_URL חסר — הבוט יקבל הודעות רק אם webhook נרשם ידנית",
        )
        return

    secret = settings.telegram_webhook_secret.get_secret_value() or None
    await bot_app.bot.set_webhook(
        url=webhook_url,
        secret_token=secret,
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=False,
    )
    # רושמים רק את ה-host — ה-path מכיל את ה-secret ואסור שייכנס ללוגים
    from urllib.parse import urlparse

    parsed = urlparse(webhook_url)
    logger.info("telegram.webhook.registered", host=parsed.netloc)


app = FastAPI(
    title="APIWatchBot",
    description="בוט טלגרם המנטר 10 ספקי API ושולח עדכונים מותאמים אישית בעברית.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, str]:
    """Render משתמש בזה כ-health check. אסור שיכשל אם DB זמני לא זמין."""
    return {"status": "ok"}


# ה-path מכיל את ה-secret כדי להקשות על ניחוש.
# בנוסף אנחנו מאמתים את הכותרת X-Telegram-Bot-Api-Secret-Token כאמצעי שני.
@app.post("/telegram/webhook/{secret}")
async def telegram_webhook(secret: str, request: Request) -> Response:
    """נקודת הקצה שאליה Telegram שולח updates."""
    settings: Settings = request.app.state.settings
    bot_app: Application | None = request.app.state.bot_app

    if bot_app is None:
        raise HTTPException(status_code=HTTPStatus.SERVICE_UNAVAILABLE, detail="bot not configured")

    # אם הגענו לכאן אז telegram_configured=True, כלומר ה-secret מוגדר.
    # אסור לדלג על האימות בשום תרחיש — בלי secret מאומת = אסור לעבד את ה-update.
    expected_secret = settings.telegram_webhook_secret.get_secret_value()
    if not expected_secret:
        # הגנת רוחב — לא אמור לקרות אם config נכון, אבל לא נסכן.
        logger.error("telegram.webhook.misconfigured", reason="empty secret in handler")
        raise HTTPException(status_code=HTTPStatus.SERVICE_UNAVAILABLE)

    # שתי בדיקות — secret ב-path + header. שתיהן ב-compare_digest כדי להימנע
    # מ-timing side channel שיאפשר ניחוש הדרגתי. שתיהן רצות תמיד (לא
    # קצרצרת) כדי שהזמן יישאר קבוע.
    path_ok = hmac.compare_digest(secret, expected_secret)
    header_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    header_ok = hmac.compare_digest(header_secret, expected_secret)
    if not (path_ok and header_ok):
        # לא רושמים מי משתי הבדיקות נכשלה — מידע פר-בדיקה היה מאפשר
        # לתוקף שגונב logs לדעת לאיזה ערוץ הוא צריך לכוון את התקיפה
        # (path vs header), ומחליש את ההגנה הדו-שכבתית.
        logger.warning("telegram.webhook.unauthorized")
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN)

    try:
        payload = await request.json()
    except ValueError:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="invalid JSON")

    update = Update.de_json(payload, bot_app.bot)
    if update is None:
        return Response(status_code=HTTPStatus.OK)

    # מכניסים ל-queue ומחזירים מיד 200 — PTB יעבד אסינכרונית.
    # בלי await על העיבוד נמנעים מ-timeout אם handler איטי.
    await bot_app.update_queue.put(update)
    return Response(status_code=HTTPStatus.OK)
