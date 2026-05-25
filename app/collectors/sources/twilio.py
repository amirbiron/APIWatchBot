"""מקור Twilio — RSS סטנדרטי, ישר לעניין (סעיף 5.2 ב-Spec)."""

from __future__ import annotations

from app.collectors.sources._feed_utils import BaseFeedSource


class TwilioSource(BaseFeedSource):
    api_id = "twilio"
    name_he = "Twilio"
    source_url = "https://www.twilio.com/en-us/changelog.feed.xml"
