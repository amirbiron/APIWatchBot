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
    def telegram_webhook_path(self) -> str:
        """ה-path המקומי שאליו Telegram יפנה. ה-secret בתוך ה-path מקשה על ניחוש."""
        secret = self.telegram_webhook_secret.get_secret_value()
        return f"/telegram/webhook/{secret}" if secret else "/telegram/webhook"

    @property
    def telegram_webhook_url(self) -> str | None:
        """URL מלא לרישום מול Telegram — None אם חסר base URL."""
        if not self.telegram_webhook_base_url:
            return None
        base = self.telegram_webhook_base_url.rstrip("/")
        return f"{base}{self.telegram_webhook_path}"

    @property
    def telegram_configured(self) -> bool:
        """האם יש לנו מספיק נתונים כדי להפעיל את הבוט."""
        return bool(self.telegram_bot_token.get_secret_value())

    @property
    def mongodb_configured(self) -> bool:
        return bool(self.mongodb_uri)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """ערך יחיד למשך חיי התהליך — חוסך re-parse של ENV בכל קריאה."""
    return Settings()
