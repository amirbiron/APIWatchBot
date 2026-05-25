"""מודל מצב מערכת — תואם לסעיף 4.4 ב-docs/Spec.md."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SystemState(BaseModel):
    """key/value פנימי — למשל last_collect:openai."""

    key: str
    value: Any
    updated_at: datetime = Field(default_factory=_utcnow)
