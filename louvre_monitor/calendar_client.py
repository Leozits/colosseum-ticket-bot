"""Reads Louvre ticket-calendar day statuses via genuine browser interaction.

The site is behind Cloudflare bot management: a bare HTTP request gets a 403
with a `Cf-Mitigated: challenge` header and a "Just a moment..." interstitial
-- confirmed by direct testing. It must be driven from a real, JS-executing
browser, same constraint as the Colosseum monitor. Once past the challenge,
the calendar renders each day as a checkbox input carrying a `data-date`
attribute and a `disabled` attribute when that day isn't bookable, so day
status is read straight from the DOM -- no network interception needed.

Each "next"/"previous" click triggers the site's own `get-calendar-by-month`
XHR, which re-renders the day checkboxes -- confirmed by live testing to
intermittently leave the DOM with zero checkboxes for a brief window (the
old month's checkboxes already removed, the new month's not yet inserted).
Neither a fixed sleep nor waiting on that XHR's network response proved
reliable across repeated live runs (the response event intermittently never
fired as observed by Playwright, for reasons not pinned down), so
navigate_to_month instead polls the visible month header itself after each
click until it actually shows the expected month -- confirmed reliable
across many repeated live runs.
"""

_MONTH_NAMES = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]


def read_current_month(page):
    """Return (year, month) currently displayed in the calendar header."""
    month_name = page.query_selector(".d-month").inner_text().strip().lower()
    year = int(page.query_selector(".d-year").inner_text().strip())
    return year, _MONTH_NAMES.index(month_name) + 1


def navigate_to_month(page, target_year, target_month):
    """Click the calendar's prev/next arrow until the target month is displayed."""
    current_year, current_month = read_current_month(page)
    delta = (target_year * 12 + target_month) - (current_year * 12 + current_month)
    selector = "#d-next" if delta > 0 else "#d-previous"
    step = 1 if delta > 0 else -1
    for _ in range(abs(delta)):
        expected_total = current_year * 12 + current_month + step
        # force=True: various transient elements can sit on top of this
        # button depending on timing -- same defensive click style already
        # proven necessary for the Colosseum monitor's calendar navigation.
        page.click(selector, force=True)
        for _ in range(20):
            page.wait_for_timeout(250)
            try:
                year, month = read_current_month(page)
            except AttributeError:
                continue  # header briefly absent mid-re-render
            if year * 12 + month == expected_total:
                current_year, current_month = year, month
                break
        else:
            raise TimeoutError(f"Calendar did not advance past {current_year}-{current_month:02d}")


def read_month_days(page):
    """Read every day checkbox in the currently-displayed calendar month.

    Returns {date_str ("YYYY-MM-DD"): status ("available" | "unavailable")}.
    """
    days = {}
    for checkbox in page.query_selector_all("#calendarContainer input[data-date]"):
        date_str = checkbox.get_attribute("data-date")[:10]
        is_disabled = checkbox.get_attribute("disabled") is not None
        days[date_str] = "unavailable" if is_disabled else "available"
    return days
