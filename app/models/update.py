"""מודל פריט changelog — תואם לסעיף 4.2 ב-docs/Spec.md."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["critical", "important", "info"]
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
    severity: Severity | None = None
    is_urgent: bool = False
    categories: list[Category] = Field(default_factory=list)

    # מטא
    collected_at: datetime = Field(default_factory=datetime.utcnow)
    processed_at: datetime | None = None

    status: UpdateStatus = "raw"
