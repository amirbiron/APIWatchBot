"""מחלקת בסיס וטיפוסים משותפים לכל הקולקטורים.

כל מקור (Render, OpenAI, Stripe, ...) יורש מ-BaseSource ומממש fetch().
ה-Runner מריץ את כולם במקביל ושומר את ה-RawItems שחזרו ל-DB.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import ClassVar

import httpx


@dataclass(frozen=True)
class RawItem:
    """פריט גולמי שנאסף ממקור כלשהו — לפני dedup ולפני AI.

    `frozen=True` כדי שיהיה hashable וניתן לשימוש ב-set/dict.
    """

    api_id: str
    raw_title: str
    raw_content: str
    source_url: str
    source_published_at: datetime | None = None
    # שדה נוסף לעקיפת hash דיפולטיבי במקרים מיוחדים
    # (לדוגמה: Gemini עם hash per-item לפי תאריך — סעיף 5.2 ב-Spec).
    custom_hash_input: str | None = field(default=None, repr=False)

    @property
    def content_hash(self) -> str:
        """sha256 לזיהוי כפילויות. כולל api_id כדי שאותו טקסט מ-2 מקורות
        לא ייחשב כאותו פריט.

        אם סופק `custom_hash_input` — נשתמש בו במקום בשרשור הדיפולטיבי.
        זה הכרחי למקורות שבהם raw_content משתנה ב-trim/whitespace בלי
        שינוי משמעות (לדוגמה Gemini).
        """
        if self.custom_hash_input is not None:
            payload = f"{self.api_id}::{self.custom_hash_input}"
        else:
            payload = f"{self.api_id}::{self.raw_title}::{self.raw_content}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class BaseSource(ABC):
    """כל מקור איסוף יורש ממחלקה הזו.

    מאפיינים כ-class vars (לא instance vars) — הם קבועים פר מקור.
    """

    # מזהה ייחודי שיישמר ב-DB (`updates.api_id`). באנגלית, lowercase.
    api_id: ClassVar[str]
    # שם תצוגה בעברית (יוצג בהודעות למשתמש).
    name_he: ClassVar[str]
    # ה-URL הראשי של המקור (לוגינג + הצגה).
    source_url: ClassVar[str]
    # timeout דיפולטיבי לבקשת HTTP. ניתן ל-override במקור.
    timeout_seconds: ClassVar[float] = 30.0
    # מזהה פר-instance למצב פנימי (system_state keys). אופציונלי —
    # ברירת מחדל ריק שמתורגם ל-api_id ב-source_key. נדרש כאשר 2+ classes
    # חולקים api_id (לדוגמה: WhatsApp Meta + Green API) ועדיין צריכים
    # failure counter נפרד.
    source_id: ClassVar[str] = ""

    def __init__(self, http_client: httpx.AsyncClient) -> None:
        # ה-client משותף בין כל המקורות (חוסך connections).
        self._http = http_client

    @property
    def source_key(self) -> str:
        """מפתח ייחודי פר-instance ל-state. מתרגם source_id ריק ל-api_id."""
        return self.source_id or self.api_id

    @abstractmethod
    async def fetch(self) -> list[RawItem]:
        """מחזיר רשימת פריטים גולמיים מהמקור. חייב להיות אסינכרוני.

        מותר לזרוק httpx.HTTPError לכשלי רשת/HTTP — CollectorRunner._run_one
        תופס אותו ומתעד את המקור ככשל בלי להפיל אחרים. גם חריגות אחרות
        נתפסות שם כ-`unexpected:` (ה-`except Exception` הרחב), אבל עדיף
        לטפל בהן במקום אם הן צפויות.
        """
