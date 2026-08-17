"""Reads Versailles ticket-calendar day statuses via a plain HTTP request.

Unlike the Colosseum and Louvre sites, this endpoint has no bot-blocking --
confirmed by a direct, cookie-less curl POST returning a real 200 with
calendar data. No browser is needed.

The site's own day classes are "open" (bookable), "closed" (not bookable
that day, e.g. a weekly closure), and "disabled" (outside the bookable
horizon) -- the latter two both map to "unavailable" here, since neither
means a booking can actually be made.
"""

import re

import httpx

_DAY_PATTERN = re.compile(
    r'id="agenda--calendar--date-(\d{4}-\d{2}-\d{2})"[^>]*'
    r'class="agenda--calendar-slot (\w+)'
)


def fetch_month_html(year, month):
    response = httpx.post(
        "https://ticket.chateauversailles.fr/en/api/calendar",
        data={"month": month, "year": year},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()["#markup"]


def parse_month_days(html):
    """Parse the calendar HTML fragment into day statuses.

    Returns {date_str ("YYYY-MM-DD"): status ("available" | "unavailable")}.
    """
    return {
        date_str: "available" if css_class == "open" else "unavailable"
        for date_str, css_class in _DAY_PATTERN.findall(html)
    }
