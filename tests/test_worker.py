"""בדיקות ל-worker/__main__.py — מתמקדות בניהול lifecycle נקי."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_worker_closes_mongo_on_ensure_indexes_failure(monkeypatch) -> None:
    """אם ensure_indexes נכשל אחרי שmongo כבר התחבר — close_mongo_connection
    חייב להיקרא בכל זאת. בלי זה — דליפת חיבור ב-Render workers."""
    monkeypatch.setenv("MONGODB_URI", "mongodb://fake")
    monkeypatch.setenv("TIMEZONE", "Asia/Jerusalem")

    from app.config import get_settings

    get_settings.cache_clear()

    from worker import __main__ as worker_main

    cleanup_calls: list[str] = []

    async def fake_connect() -> object:
        cleanup_calls.append("mongo_connected")
        return object()

    async def fake_ensure_indexes(db: object) -> None:
        raise RuntimeError("simulated index failure")

    async def fake_close_mongo() -> None:
        cleanup_calls.append("mongo_closed")

    monkeypatch.setattr(worker_main, "connect_to_mongo", fake_connect)
    monkeypatch.setattr(worker_main, "ensure_indexes", fake_ensure_indexes)
    monkeypatch.setattr(worker_main, "close_mongo_connection", fake_close_mongo)

    try:
        with pytest.raises(RuntimeError, match="simulated"):
            await worker_main.main()

        # ה-cleanup חייב לרוץ למרות שהכשל היה אחרי connect
        assert "mongo_connected" in cleanup_calls
        assert "mongo_closed" in cleanup_calls
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_worker_closes_mongo_on_scheduler_start_failure(monkeypatch) -> None:
    """גם אם scheduler.start נכשל (לדוגמה: שעון מערכת מקולקל) — mongo נסגר."""
    monkeypatch.setenv("MONGODB_URI", "mongodb://fake")
    monkeypatch.setenv("TIMEZONE", "Asia/Jerusalem")

    from app.config import get_settings

    get_settings.cache_clear()

    from worker import __main__ as worker_main

    cleanup_calls: list[str] = []

    async def fake_connect() -> object:
        cleanup_calls.append("mongo_connected")
        return object()

    async def fake_ensure_indexes(db: object) -> None:
        pass

    async def fake_close_mongo() -> None:
        cleanup_calls.append("mongo_closed")

    class _BrokenScheduler:
        def start(self) -> None:
            raise RuntimeError("scheduler boom")

        def shutdown(self, wait: bool = False) -> None:
            cleanup_calls.append("scheduler_shutdown_called")

        def get_jobs(self) -> list:
            return []

    def fake_build_scheduler(*args, **kwargs):
        return _BrokenScheduler()

    monkeypatch.setattr(worker_main, "connect_to_mongo", fake_connect)
    monkeypatch.setattr(worker_main, "ensure_indexes", fake_ensure_indexes)
    monkeypatch.setattr(worker_main, "close_mongo_connection", fake_close_mongo)
    monkeypatch.setattr(worker_main, "build_scheduler", fake_build_scheduler)

    try:
        with pytest.raises(RuntimeError, match="scheduler boom"):
            await worker_main.main()

        assert "mongo_connected" in cleanup_calls
        assert "mongo_closed" in cleanup_calls
        # scheduler לא הצליח להתחיל → shutdown לא נקרא (scheduler_started=False)
        assert "scheduler_shutdown_called" not in cleanup_calls
    finally:
        get_settings.cache_clear()
