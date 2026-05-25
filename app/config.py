"""טעינת תצורת המערכת ממשתני סביבה עם ולידציה ע"י Pydantic."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """כל ההגדרות נטענות מ-.env או ממשתני סביבה של המערכת."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Telegram
    telegram_bot_token: SecretStr = Field(default=SecretStr(""))
    telegram_webhook_secret: SecretStr = Field(default=SecretStr(""))
    # ה-URL הציבורי של השירות (לדוגמה https://api-watch-web.onrender.com).
    # נשתמש בו בעת רישום ה-webhook מול Telegram ב-startup.
    telegram_webhook_base_url: str = ""
    admin_telegram_id: int | None = None

    # MongoDB
    mongodb_uri: str = ""
    mongodb_db_name: str = "apiwatch"

    # Google AI — לא בשימוש בשלב 1
    gemini_api_key: SecretStr = Field(default=SecretStr(""))

    # General
    environment: Literal["development", "staging", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    timezone: str = "Asia/Jerusalem"

    @property
    def telegram_webhook_path(self) -> str | None:
        """ה-path המקומי שאליו Telegram יפנה. path קבוע — האימות
        מתבצע דרך ה-header X-Telegram-Bot-Api-Secret-Token (compare_digest).

        עברנו מ-path מבוסס-secret ל-path קבוע כדי שה-secret לא ידלוף
        ללוגי גישה של Render / reverse proxy שמתעדים URLs. ה-header מספק
        אימות שווה ערך — זו ההמלצה הרשמית של Telegram.

        מחזיר None אם אין secret מוגדר — אסור לרשום webhook ללא הגנת
        secret_token. ההגדרה של telegram_configured כבר אוכפת זאת
        גלובלית; ה-בדיקה כאן היא הגנת רוחב.
        """
        if not self.telegram_webhook_secret.get_secret_value():
            return None
        return "/telegram/webhook"

    @property
    def telegram_webhook_url(self) -> str | None:
        """URL מלא לרישום מול Telegram — None אם חסר base URL או secret."""
        path = self.telegram_webhook_path
        if not self.telegram_webhook_base_url or path is None:
            return None
        base = self.telegram_webhook_base_url.rstrip("/")
        return f"{base}{path}"

    @property
    def telegram_configured(self) -> bool:
        """דורש את שלושת הרכיבים: token, base URL, וsecret. בלי שלושתם
        לא נפעיל את הבוט — עדיף שלא לרוץ מאשר לרוץ עם הגנה חסרה."""
        return (
            bool(self.telegram_bot_token.get_secret_value())
            and bool(self.telegram_webhook_base_url)
            and bool(self.telegram_webhook_secret.get_secret_value())
        )

    @property
    def admin_notify_configured(self) -> bool:
        """האם אפשר לשלוח התראות אדמין. דורש token + admin_id, אבל לא
        webhook URL — worker שולח דרך Bot API ישירות, לא דרך ה-FastAPI."""
        return (
            bool(self.telegram_bot_token.get_secret_value())
            and self.admin_telegram_id is not None
        )

    @property
    def mongodb_configured(self) -> bool:
        return bool(self.mongodb_uri)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """ערך יחיד למשך חיי התהליך — חוסך re-parse של ENV בכל קריאה."""
    return Settings()
