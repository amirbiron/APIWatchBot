"""מודל משתמש — תואם לסעיף 4.1 ב-docs/Spec.md."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    """datetime tz-aware ב-UTC. mongodb client שלנו נטען עם tz_aware=True,
    אז כל datetime ש-default-factory יוצר חייב להיות aware כדי שהשוואות
    ('updated_at > X') לא יזרקו TypeError."""
    return datetime.now(timezone.utc)

# רמת חומרה מינימלית שמשתמש מוכן לקבל
Severity = Literal["critical", "important", "all"]
Frequency = Literal["weekly"]  # בעתיד: "daily"
ConversationState = Literal[
    "idle",
    "selecting_apis",
    "selecting_severity",
    "selecting_frequency",
    "confirming",
]


class User(BaseModel):
    """משתמש רשום במערכת. נשמר בקולקציה `users`."""

    telegram_id: int
    username: str | None = None
    first_name: str | None = None
    language_code: str | None = None

    # העדפות
    subscribed_apis: list[str] = Field(default_factory=list)
    min_severity: Severity = "important"
    frequency: Frequency = "weekly"
    receive_urgent_alerts: bool = True

    # מטא
    registered_at: datetime = Field(default_factory=_utcnow)
    last_active_at: datetime = Field(default_factory=_utcnow)
    paused: bool = False

    # מצב שיחה (לפלואו הרישום האינטראקטיבי בשלב 4)
    conversation_state: ConversationState = "idle"
