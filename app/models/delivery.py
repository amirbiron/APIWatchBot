"""מודל שליחה — תואם לסעיף 4.3 ב-docs/Spec.md."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

DeliveryType = Literal["urgent", "weekly_digest"]


class Delivery(BaseModel):
    """רשומת מעקב — מאיזה update נשלח לאיזה user. מונע שליחה כפולה."""

    # ObjectId-ים נשמרים כ-Any כדי לא לכפות תלות ב-bson כאן
    user_id: Any
    update_id: Any
    delivery_type: DeliveryType
    sent_at: datetime = Field(default_factory=datetime.utcnow)
