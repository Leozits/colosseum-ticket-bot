"""Reads real ticket-calendar day statuses from the ticketing site via genuine browser interaction.

The site's WAF blocks network requests triggered by injected script (e.g. page.evaluate
calling fetch()), even from an already-loaded, otherwise-legitimate page session --
confirmed by testing. Real user-driven interaction (mouse clicks dispatched through the
browser's own input stack) is NOT blocked, since the resulting request is fired by the
page's own already-loaded jQuery, not by anything we inject. So this module never calls
page.evaluate for network requests -- it only clicks real elements and reads back the
resulting DOM state.
"""

from colosseum_monitor.availability import parse_calendar_title, classify_day_status


def advance_to_max_month(page):
    """Click the calendar's "next month" arrow until the site's booking horizon is reached."""
    while True:
        button = page.query_selector(".ui-datepicker-next")
        if not button:
            break
        css_class = button.get_attribute("class") or ""
        if "ui-state-disabled" in css_class:
            break
        # Various transient elements (loading overlay, sticky header, cookie
        # banner) can sit on top of this button depending on timing; force=True
        # dispatches the click at its location regardless -- still a real
        # browser input event, just skipping Playwright's own "is anything
        # covering this?" pre-click check.
        button.click(force=True)
        page.wait_for_timeout(2500)


def read_visible_month_days(page):
    """Read every day cell in the currently-displayed calendar month.

    Returns {date_str ("YYYY-MM-DD"): status ("soldout" | "closing" | "available" | "unknown")}.
    """
    title_element = page.query_selector(".ui-datepicker-title")
    if not title_element:
        raise ValueError("Calendar title not found on page")
    year, month = parse_calendar_title(title_element.inner_text())

    days = {}
    for cell in page.query_selector_all(".ui-datepicker-calendar td"):
        link = cell.query_selector("a")
        span = cell.query_selector("span")
        text_element = link or span
        if text_element is None:
            continue
        day_text = text_element.inner_text().strip()
        if not day_text.isdigit():
            continue
        css_class = cell.get_attribute("class") or ""
        status = classify_day_status(css_class, link is not None)
        date_str = f"{year:04d}-{month:02d}-{int(day_text):02d}"
        days[date_str] = status
    return days
