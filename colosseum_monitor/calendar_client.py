"""Reads real ticket-calendar day statuses from the ticketing site via genuine browser interaction.

The site's WAF blocks network requests triggered by injected script (e.g. page.evaluate
calling fetch()), even from an already-loaded, otherwise-legitimate page session --
confirmed by testing. Real user-driven interaction (mouse clicks dispatched through the
browser's own input stack) is NOT blocked, since the resulting request is fired by the
page's own already-loaded jQuery, not by anything we inject. So this module never calls
page.evaluate for network requests -- it only clicks real elements and reads back the
resulting DOM state.
"""

from colosseum_monitor.availability import parse_calendar_title, classify_day_status, classify_slot_status


def read_current_month(page):
    """Return (year, month) currently displayed in the calendar header."""
    title_element = page.query_selector(".ui-datepicker-title")
    if title_element is None:
        raise ValueError("Calendar title not found on page")
    return parse_calendar_title(title_element.inner_text())


def _read_current_month_tolerantly(page):
    """Retry read_current_month briefly -- confirmed by testing (on the
    Borghese monitor) that a calendar header can be transiently absent or
    malformed right after a fresh page load, not just mid-navigation.
    """
    for _ in range(20):
        try:
            return read_current_month(page)
        except (AttributeError, ValueError):
            page.wait_for_timeout(250)
    return read_current_month(page)  # let the real exception surface


def navigate_to_month(page, target_year, target_month):
    """Click the calendar's next/prev arrow until the target month is displayed.

    If the site's own booking horizon doesn't reach the target month yet
    (the "next" arrow becomes disabled first), stops early and leaves the
    calendar on whichever month it did reach -- read_visible_month_days will
    then simply not find any of the target dates, the same "not on sale yet"
    signal already used by the Louvre and Borghese monitors. This replaces
    the previous "click next until disabled" approach, which silently lost
    track of the target dates once the site's own horizon extended past them
    (confirmed happening in production: the site jumped straight from
    October to December in one batch release, and the old code just kept
    following whatever the furthest month was instead of watching October).
    """
    current_year, current_month = _read_current_month_tolerantly(page)
    delta = (target_year * 12 + target_month) - (current_year * 12 + current_month)
    if delta == 0:
        return
    selector = ".ui-datepicker-next" if delta > 0 else ".ui-datepicker-prev"
    step = 1 if delta > 0 else -1
    for _ in range(abs(delta)):
        button = page.query_selector(selector)
        if button is None:
            return
        css_class = button.get_attribute("class") or ""
        if "ui-state-disabled" in css_class:
            return
        expected_total = current_year * 12 + current_month + step
        # force=True: various transient elements (loading overlay, sticky
        # header, cookie banner) can sit on top of this button depending on
        # timing -- same defensive click style already proven necessary.
        button.click(force=True)
        for _ in range(20):
            page.wait_for_timeout(250)
            try:
                year, month = read_current_month(page)
            except (AttributeError, ValueError):
                continue  # header briefly absent or malformed mid-re-render
            if year * 12 + month == expected_total:
                current_year, current_month = year, month
                break
        else:
            raise TimeoutError(f"Calendar did not advance past {current_year}-{current_month:02d}")


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


def click_day(page, day_number):
    """Click the cell for a given day-of-month (int) in the currently-visible month.

    Returns True if a clickable (i.e. available) cell was found and clicked.
    """
    for cell in page.query_selector_all(".ui-datepicker-calendar td"):
        link = cell.query_selector("a")
        if link and link.inner_text().strip() == str(day_number):
            link.click(force=True)
            return True
    return False


def read_time_slots(page):
    """Read the time-slot picker for whichever day was just clicked via click_day().

    Returns {time_str ("HH:MM"): status ("closed" | "available")}.
    """
    slots = {}
    for label in page.query_selector_all(".abc-slotpicker label"):
        input_element = label.query_selector("input[name='slot']")
        if input_element is None:
            continue
        time_text = label.inner_text()[:5]
        is_disabled = input_element.get_attribute("disabled") is not None
        slots[time_text] = classify_slot_status(is_disabled)
    return slots
