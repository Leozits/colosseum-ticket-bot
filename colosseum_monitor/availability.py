"""Pure functions for interpreting the ticketing calendar's day-status DOM state."""

import re

_ITALIAN_MONTHS = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5, "giugno": 6,
    "luglio": 7, "agosto": 8, "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
}


def parse_calendar_title(title):
    """Parse a jQuery UI datepicker title (e.g. "Settembre 2026") into (year, month)."""
    match = re.search(r"([A-Za-zÀ-ÿ]+)\D*(\d{4})", title)
    if not match:
        raise ValueError(f"Unrecognized calendar title: {title!r}")
    month = _ITALIAN_MONTHS.get(match.group(1).lower())
    if month is None:
        raise ValueError(f"Unrecognized month name: {match.group(1)!r}")
    return int(match.group(2)), month


def classify_day_status(css_class, is_link):
    """Classify a calendar day cell from its CSS class and whether it's a clickable <a>.

    "soldout" and "closing" mirror the site's own legend (closing_day covers both
    "closed" and "sold out" in the site's own wording) -- "available" is any day
    still rendered as a clickable link without either marker.
    """
    if "soldout_day" in css_class:
        return "soldout"
    if "closing_day" in css_class:
        return "closing"
    if is_link:
        return "available"
    return "unknown"


def find_status_changes(previous, current):
    """Return every date whose status differs from its previous recorded status."""
    changes = []
    for date_str, status in current.items():
        prev_status = previous.get(date_str)
        if prev_status != status:
            changes.append({"date": date_str, "from": prev_status, "to": status})
    return changes


def find_newly_available(previous, current):
    """Return dates that just became "available" (weren't before, or weren't tracked)."""
    return [
        date_str
        for date_str, status in current.items()
        if status == "available" and previous.get(date_str) != "available"
    ]
