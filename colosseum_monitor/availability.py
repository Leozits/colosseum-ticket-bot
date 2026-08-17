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


def classify_slot_status(is_disabled):
    """Classify a time-slot radio input from whether it carries the disabled attribute."""
    return "closed" if is_disabled else "available"
