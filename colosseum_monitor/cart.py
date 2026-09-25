"""Adds a specific date/time to the Colosseum ticket cart, and watches the
cart until it empties again (checkout completed, or the site's own expiry
auto-drop). Stops at "add to cart" -- never touches checkout or payment.
"""


def pick_earliest_newly_available(previous_statuses, current_statuses, current_slots):
    """Pick the earliest target date (and its earliest bookable time) that
    just became available.

    Returns (date_str, time_str), or None if nothing qualifies. A date only
    qualifies if it wasn't already "available" in previous_statuses and has
    at least one recorded available time in current_slots.
    """
    for date_str in sorted(current_statuses):
        if current_statuses[date_str] != "available":
            continue
        if previous_statuses.get(date_str) == "available":
            continue
        times = sorted(
            t for t, status in current_slots.get(date_str, {}).items() if status == "available"
        )
        if times:
            return date_str, times[0]
    return None


def set_participant_count(page, count):
    """Set the participant stepper to an exact count.

    A single "+" click was observed live to sometimes jump the value by
    more than one, so this reads the field back after each click and stops
    as soon as it reaches (or passes) the target, rather than blind-clicking
    a fixed number of times.
    """
    input_element = page.query_selector(".abc-participantspicker input[type='number']")
    plus_button = page.query_selector('.abc-participantspicker button[data-dir="up"]')
    for _ in range(count + 2):  # +2 safety margin for the observed over-jump
        current = input_element.get_attribute("value") or ""
        if current.isdigit() and int(current) >= count:
            return
        plus_button.click(force=True)
        page.wait_for_timeout(300)


def select_time_slot(page, time_str):
    """Select the radio for a specific bookable time in the currently-open slot picker.

    Returns True if a matching, non-disabled radio was found and clicked.
    """
    for label in page.query_selector_all(".abc-slotpicker label"):
        input_element = label.query_selector("input[name='slot']")
        if input_element is None:
            continue
        if label.inner_text()[:5] != time_str:
            continue
        if input_element.get_attribute("disabled") is not None:
            return False
        input_element.click(force=True)
        return True
    return False


def add_to_cart(page):
    """Click "Aggiungi" and report whether the cart actually gained an item.

    Success/failure is read from the resulting cart state, not assumed from
    the click itself -- the real, observed failure mode is a 403 from the
    site's own Cloudflare Turnstile check on this exact action, which
    leaves the button clickable but the cart empty.
    """
    add_button = None
    for button in page.query_selector_all("button"):
        if button.inner_text().strip() == "Aggiungi":
            add_button = button
            break
    if add_button is None:
        return False
    add_button.click(force=True)
    page.wait_for_timeout(2000)
    return not is_cart_empty(page)


def is_cart_empty(page):
    """Return True if the cart currently has no items.

    Confirmed live: #btn-showcart (the "Procedi" checkout button) is
    display:none while the cart is empty, and becomes visible once it has
    at least one item.
    """
    button = page.query_selector("#btn-showcart")
    if button is None:
        return True
    return not button.is_visible()


def wait_for_cart_to_empty(page, poll_interval_seconds, max_wait_seconds):
    """Block until the cart is empty again -- checkout completed, or the
    site's own countdown auto-dropped it. Reloads the page for each check
    (a genuine navigation, not an injected-script fetch) to match this
    repo's established WAF-safe pattern.

    Returns True if the cart emptied on its own, False if max_wait_seconds
    was reached first -- this blocks the whole monitor while it runs, so it
    must not be able to hang forever if something unexpected happens.
    """
    elapsed = 0
    while elapsed < max_wait_seconds:
        page.wait_for_timeout(poll_interval_seconds * 1000)
        elapsed += poll_interval_seconds
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector(".ui-datepicker-title", timeout=30000)
        if is_cart_empty(page):
            return True
    return False
