"""בדיקות smoke לשלב 1 — מוודאות שהשלד נטען ומגיב."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app, lifespan


def test_health_endpoint_returns_ok() -> None:
    """/health חייב להחזיר 200 כדי ש-Render יחשיב את השירות כתקין."""
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_telegram_webhook_returns_503_when_bot_not_configured(monkeypatch) -> None:
    """כשאין token, telegram_configured=False ו-bot_app=None — נקבל 503 דטרמיניסטית."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("MONGODB_URI", "")
    # ה-test client יבצע startup/shutdown לפי lifespan
    with TestClient(app) as client:
        response = client.post(
            "/telegram/webhook/wrong-secret",
            json={"update_id": 1},
        )
    assert response.status_code == 503


def test_settings_paths_are_derived() -> None:
    """webhook path חייב להיגזר נכון מ-secret."""
    from app.config import Settings

    s = Settings(telegram_webhook_secret="abc123", telegram_webhook_base_url="https://example.com")
    assert s.telegram_webhook_path == "/telegram/webhook/abc123"
    assert s.telegram_webhook_url == "https://example.com/telegram/webhook/abc123"


def test_settings_without_base_url_returns_none() -> None:
    from app.config import Settings

    s = Settings(telegram_webhook_secret="abc123", telegram_webhook_base_url="")
    assert s.telegram_webhook_url is None


def test_settings_without_secret_returns_none() -> None:
    """בלי secret אסור שיהיה path/URL — כדי להבטיח שלא נרשום webhook לא מאובטח."""
    from app.config import Settings

    s = Settings(telegram_webhook_secret="", telegram_webhook_base_url="https://example.com")
    assert s.telegram_webhook_path is None
    assert s.telegram_webhook_url is None


@pytest.mark.asyncio
async def test_lifespan_cleans_up_on_startup_failure(monkeypatch) -> None:
    """אם startup נכשל באמצע (אחרי שמשאבים נתפסו), ה-finally חייב לרוץ
    ולשחרר אותם. בלי זה — process leak ב-prod כשרישום webhook נכשל."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("MONGODB_URI", "mongodb://fake")

    # ניקוי cache של get_settings — אחרת ENV החדש לא נטען
    from app.config import get_settings

    get_settings.cache_clear()

    from app import main as main_module

    cleanup_calls: list[str] = []

    async def fake_close_mongo() -> None:
        cleanup_calls.append("mongo_closed")

    async def fake_connect() -> object:
        cleanup_calls.append("mongo_connected")
        return object()

    async def fake_ensure_indexes(db: object) -> None:
        raise RuntimeError("simulated index failure mid-startup")

    monkeypatch.setattr(main_module, "connect_to_mongo", fake_connect)
    monkeypatch.setattr(main_module, "ensure_indexes", fake_ensure_indexes)
    monkeypatch.setattr(main_module, "close_mongo_connection", fake_close_mongo)

    from fastapi import FastAPI

    dummy_app = FastAPI()
    try:
        with pytest.raises(RuntimeError, match="simulated"):
            async with lifespan(dummy_app):
                pass  # pragma: no cover — לא אמורים להגיע ל-yield

        # זה הלב של הבדיקה — אסור ש-mongo יישאר פתוח אחרי כשל startup
        assert "mongo_connected" in cleanup_calls
        assert "mongo_closed" in cleanup_calls
    finally:
        # החזרת המצב הראשוני כדי לא להשפיע על בדיקות אחרות
        get_settings.cache_clear()


def test_telegram_configured_requires_all_three() -> None:
    from app.config import Settings

    s_no_token = Settings(
        telegram_bot_token="", telegram_webhook_secret="s", telegram_webhook_base_url="https://x"
    )
    s_no_url = Settings(
        telegram_bot_token="t", telegram_webhook_secret="s", telegram_webhook_base_url=""
    )
    s_no_secret = Settings(
        telegram_bot_token="t", telegram_webhook_secret="", telegram_webhook_base_url="https://x"
    )
    s_full = Settings(
        telegram_bot_token="t", telegram_webhook_secret="s", telegram_webhook_base_url="https://x"
    )

    assert s_no_token.telegram_configured is False
    assert s_no_url.telegram_configured is False
    assert s_no_secret.telegram_configured is False
    assert s_full.telegram_configured is True
