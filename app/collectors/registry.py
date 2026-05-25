"""רישום מרכזי של כל המקורות הפעילים.

כאן מתווסף כל מקור חדש בעתיד — קל לראות מה מנוטר ומה לא.
"""

from __future__ import annotations

import httpx

from app.collectors.base import BaseSource
from app.collectors.sources.openai import OpenAISource
from app.collectors.sources.render import RenderSource
from app.collectors.sources.twilio import TwilioSource

# סוג המקור — class ולא instance — כדי שה-Runner ייצור אותם עם ה-http client.
SourceClass = type[BaseSource]

ALL_SOURCES: list[SourceClass] = [
    RenderSource,
    OpenAISource,
    TwilioSource,
    # Wave 2 ו-3 ייתווספו ב-PR הבא.
]


def build_sources(http_client: httpx.AsyncClient) -> list[BaseSource]:
    """instantiation של כל המקורות עם client משותף."""
    return [cls(http_client) for cls in ALL_SOURCES]
