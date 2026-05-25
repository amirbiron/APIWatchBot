"""מקור Stripe — HTML scraping של docs.stripe.com/changelog.

מבנה ה-DOM (סעיף 5.2 ב-Spec): טבלה — לכל `<tr>` יש עמודה עם תאריך
ועמודה עם תיאור. שורת ה-header מסוננת ע"י בדיקה ש-יש לפחות 2 cells
של `<td>` (וכך מדלגים על `<th>`).
"""

from __future__ import annotations

from app.collectors.base import BaseSource, RawItem
from app.collectors.sources._html_utils import (
    clean_text,
    fetch_html,
    parse_html,
    parse_iso_date,
)
from app.logging_config import get_logger

logger = get_logger(__name__)


class StripeSource(BaseSource):
    api_id = "stripe"
    name_he = "Stripe"
    source_url = "https://docs.stripe.com/changelog"

    async def fetch(self) -> list[RawItem]:
        data = await fetch_html(self._http, self.source_url, self.timeout_seconds)
        parser = await parse_html(data)

        items: list[RawItem] = []
        for row in parser.css("tr"):
            cells = row.css("td")
            if len(cells) < 2:
                # שורת header (רק <th>) או שורה חלקית — דילוג
                continue

            date_str = clean_text(cells[0])
            description = clean_text(cells[1])

            if not description:
                continue

            # ה-title הוא 80 התווים הראשונים של ה-description, או התאריך עצמו
            # אם אין תיאור משמעותי. ה-AI ייצור title טוב יותר בשלב 3.
            title = description[:80] + ("…" if len(description) > 80 else "")

            items.append(
                RawItem(
                    api_id=self.api_id,
                    raw_title=title,
                    raw_content=description,
                    source_url=self.source_url,
                    source_published_at=parse_iso_date(date_str),
                )
            )

        logger.debug("source.stripe.fetched", count=len(items))
        return items
