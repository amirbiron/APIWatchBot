"""רישום מרכזי של כל המקורות הפעילים.

כאן מתווסף כל מקור חדש בעתיד — קל לראות מה מנוטר ומה לא.
"""

from __future__ import annotations

import httpx

from app.collectors.base import BaseSource
from app.collectors.sources.google_business import GoogleBusinessSource
from app.collectors.sources.google_gemini import GoogleGeminiSource
from app.collectors.sources.meta_graph import MetaGraphSource
from app.collectors.sources.openai import OpenAISource
from app.collectors.sources.render import RenderSource
from app.collectors.sources.stripe import StripeSource
from app.collectors.sources.telegram import TelegramSource
from app.collectors.sources.twilio import TwilioSource
from app.collectors.sources.whatsapp import WhatsAppGreenSource, WhatsAppMetaSource

# סוג המקור — class ולא instance — כדי שה-Runner ייצור אותם עם ה-http client.
SourceClass = type[BaseSource]

ALL_SOURCES: list[SourceClass] = [
    # Wave 1 — RSS feeds
    RenderSource,
    OpenAISource,
    TwilioSource,
    # Wave 2 — HTML scraping (יציב)
    TelegramSource,
    StripeSource,
    GoogleBusinessSource,
    GoogleGeminiSource,
    # Wave 3 — HTML scraping שביר (retries + admin alerts)
    MetaGraphSource,
    WhatsAppMetaSource,
    WhatsAppGreenSource,
    # Anthropic (SPA + Playwright) — ייתווסף ב-PR נפרד.
]


def build_sources(http_client: httpx.AsyncClient) -> list[BaseSource]:
    """instantiation של כל המקורות עם client משותף."""
    return [cls(http_client) for cls in ALL_SOURCES]
