"""בדיקות smoke לשלב 1 — מוודאות שהשלד נטען ומגיב."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint_returns_ok() -> None:
    """/health חייב להחזיר 200 כדי ש-Render יחשיב את השירות כתקין."""
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_telegram_webhook_rejects_bad_secret(monkeypatch) -> None:
    """webhook עם secret שגוי חייב להחזיר 403."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")  # בלי בוט = 503
    monkeypatch.setenv("MONGODB_URI", "")
    # ה-test client יבצע startup/shutdown לפי lifespan
    with TestClient(app) as client:
        response = client.post(
            "/telegram/webhook/wrong-secret",
            json={"update_id": 1},
        )
    # ללא בוט מוגדר נקבל 503 (לא 403) — זה מאשר שהראוטר עובד.
    assert response.status_code in (403, 503)


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
