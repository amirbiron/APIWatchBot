"""מודל פריט changelog — תואם לסעיף 4.2 ב-docs/Spec.md."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    """tz-aware UTC — תואם ל-mongo client עם tz_aware=True."""
    return datetime.now(timezone.utc)

# הסיווג שה-AI נותן לפריט עצמו.
# שונה מ-`MinSeverity` שב-user.py — כאן זה ערך, שם זה סף סינון.
UpdateSeverity = Literal["critical", "important", "info"]
UpdateStatus = Literal["raw", "processed", "failed", "skipped_noise"]
Category = Literal[
    "deprecation",
    "breaking",
    "new_feature",
    "pricing",
    "security",
    "bugfix",
    "performance",
]


class Update(BaseModel):
    """פריט changelog יחיד מספק API. נשמר בקולקציה `updates`."""

    api_id: str

    # תוכן גולמי
    raw_title: str
    raw_content: str
    source_url: str
    source_published_at: datetime | None = None

    # מזהה ייחודי לזיהוי כפילויות
    content_hash: str

    # תוצרי עיבוד AI — ממולאים בשלב 3
    summary_he: str | None = None
    severity: UpdateSeverity | None = None
    is_urgent: bool = False
    categories: list[Category] = Field(default_factory=list)

    # מטא
    collected_at: datetime = Field(default_factory=_utcnow)
    processed_at: datetime | None = None

    status: UpdateStatus = "raw"
