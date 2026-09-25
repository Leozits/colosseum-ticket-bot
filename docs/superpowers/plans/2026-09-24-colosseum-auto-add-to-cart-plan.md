# Colosseum Auto-Add-to-Cart Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When the Colosseum monitor finds a target date/time newly available, automatically add it to the cart (earliest date, earliest time first) and hold a second, on-screen browser open until the user finishes checkout themselves or the cart empties on its own.

**Architecture:** New `colosseum_monitor/cart.py` holds every cart-specific action (set participant count, select a time slot, add to cart, detect an empty cart, wait for it to empty). `colosseum_monitor/run.py`'s `_real_fetch_days` gains a second, on-screen browser session that only opens when a genuinely new target slot is found; a small notification-suppression flag stops the normal "it's available" email firing redundantly after the cart-specific one already went out.

**Tech Stack:** Python, `patchright` (same technique already used for the routine check), `pytest`.

## Global Constraints

- Stops at "add to cart" — never touches checkout or payment, never attempts to defeat the Cloudflare Turnstile challenge beyond what a normal browser session already does.
- Colosseum-only — not generalized to the other three monitors.
- Picks the single earliest (date, then time) newly-available pair per run — never tries to grab more than one.
- `AUTO_ADD_TO_CART` config flag must exist so this can be turned off without a code change.
- The cart's hold time is never hardcoded or guessed — the monitor watches the cart's own empty/non-empty state instead.

---

## Confirmed technical findings (from live testing, not assumption)

- Participant stepper: `.abc-participantspicker input[type='number']` (value starts empty) and `.abc-participantspicker button[data-dir="up"]` (the `+` button). A single click was observed live jumping the value by more than one increment — `set_participant_count` reads the value back after each click rather than blind-clicking a fixed number of times.
- Time-slot radios: `.abc-slotpicker label` each containing `input[name='slot']`; the label's `inner_text()[:5]` is the time (e.g. `"09:45"`), matching exactly how `colosseum_monitor/calendar_client.py:read_time_slots` already reads them. A disabled slot's input carries a `disabled` attribute.
- Add-to-cart button: a `<button>` whose exact text is `"Aggiungi"`. The real, observed failure mode is `POST /mtajax/addtocart` returning `403` (a Cloudflare Turnstile failure, confirmed from the user's own browser console) — the button itself stays present and clickable either way, so success must be read from whether the cart actually gained an item, not from the click succeeding.
- Empty-cart signal: `#btn-showcart` (the "Procedi" checkout button) is `display: none` while the cart is empty and becomes visible once it has an item — confirmed live on 2026-09-24 with an empty cart. `is_cart_empty` checks this element's visibility.

---

### Task 1: Colosseum cart module

**Files:**
- Create: `colosseum_monitor/cart.py`
- Create: `tests/test_colosseum_cart.py`

**Interfaces:**
- Produces: `colosseum_monitor.cart.pick_earliest_newly_available(previous_statuses, current_statuses, current_slots) -> tuple[str, str] | None`
- Produces: `colosseum_monitor.cart.set_participant_count(page, count) -> None`
- Produces: `colosseum_monitor.cart.select_time_slot(page, time_str) -> bool`
- Produces: `colosseum_monitor.cart.add_to_cart(page) -> bool`
- Produces: `colosseum_monitor.cart.is_cart_empty(page) -> bool`
- Produces: `colosseum_monitor.cart.wait_for_cart_to_empty(page, poll_interval_seconds, max_wait_seconds) -> bool` (`True` if it emptied on its own, `False` if `max_wait_seconds` was reached first)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_colosseum_cart.py`:

```python
from colosseum_monitor.cart import (
    pick_earliest_newly_available,
    set_participant_count,
    select_time_slot,
    add_to_cart,
    is_cart_empty,
    wait_for_cart_to_empty,
)


# --- pick_earliest_newly_available -----------------------------------------

def test_pick_earliest_newly_available_prefers_the_earliest_date():
    previous = {"2026-10-22": "closing", "2026-10-23": "closing"}
    current = {"2026-10-22": "available", "2026-10-23": "available"}
    slots = {"2026-10-22": {"09:00": "available"}, "2026-10-23": {"08:45": "available"}}
    assert pick_earliest_newly_available(previous, current, slots) == ("2026-10-22", "09:00")


def test_pick_earliest_newly_available_picks_earliest_time_within_a_date():
    previous = {"2026-10-22": "closing"}
    current = {"2026-10-22": "available"}
    slots = {"2026-10-22": {"12:00": "available", "09:00": "available"}}
    assert pick_earliest_newly_available(previous, current, slots) == ("2026-10-22", "09:00")


def test_pick_earliest_newly_available_ignores_dates_already_available_before():
    previous = {"2026-10-22": "available"}
    current = {"2026-10-22": "available"}
    slots = {"2026-10-22": {"09:00": "available"}}
    assert pick_earliest_newly_available(previous, current, slots) is None


def test_pick_earliest_newly_available_skips_a_date_with_no_recorded_slot():
    previous = {"2026-10-22": "closing", "2026-10-23": "closing"}
    current = {"2026-10-22": "available", "2026-10-23": "available"}
    slots = {"2026-10-23": {"08:45": "available"}}  # 2026-10-22 has no slots entry
    assert pick_earliest_newly_available(previous, current, slots) == ("2026-10-23", "08:45")


def test_pick_earliest_newly_available_returns_none_when_nothing_qualifies():
    previous = {"2026-10-22": "closing"}
    current = {"2026-10-22": "closing"}
    slots = {}
    assert pick_earliest_newly_available(previous, current, slots) is None


# --- set_participant_count --------------------------------------------------

class FakeParticipantsPage:
    def __init__(self, start_value="", increment=1):
        self.value = start_value
        self.increment = increment
        self.click_count = 0
        self.wait_calls = 0

    def query_selector(self, selector):
        if selector == ".abc-participantspicker input[type='number']":
            return _FakeInput(self)
        if selector == '.abc-participantspicker button[data-dir="up"]':
            return _FakePlusButton(self)
        return None

    def wait_for_timeout(self, ms):
        self.wait_calls += 1


class _FakeInput:
    def __init__(self, page):
        self._page = page

    def get_attribute(self, name):
        return self._page.value if name == "value" else None


class _FakePlusButton:
    def __init__(self, page):
        self._page = page

    def click(self, force=False):
        self._page.click_count += 1
        current = int(self._page.value) if self._page.value.isdigit() else 0
        self._page.value = str(current + self._page.increment)


def test_set_participant_count_clicks_until_target_reached():
    page = FakeParticipantsPage(start_value="", increment=1)
    set_participant_count(page, 2)
    assert page.value == "2"
    assert page.click_count == 2


def test_set_participant_count_stops_early_if_a_click_overshoots_the_target():
    # Confirmed live: a single click was observed jumping the value by more
    # than one increment -- this must not cause an extra, unwanted click.
    page = FakeParticipantsPage(start_value="", increment=2)
    set_participant_count(page, 1)
    assert page.value == "2"
    assert page.click_count == 1


# --- select_time_slot --------------------------------------------------------

class FakeElement:
    def __init__(self, text="", attrs=None, visible=True, on_click=None):
        self._text = text
        self._attrs = dict(attrs or {})
        self._visible = visible
        self.clicked = False
        self._on_click = on_click

    def inner_text(self):
        return self._text

    def get_attribute(self, name):
        return self._attrs.get(name)

    def is_visible(self):
        return self._visible

    def click(self, force=False):
        self.clicked = True
        if self._on_click:
            self._on_click()


class FakeLabel:
    def __init__(self, text, input_element):
        self._text = text
        self._input = input_element

    def inner_text(self):
        return self._text

    def query_selector(self, selector):
        if selector == "input[name='slot']":
            return self._input
        return None


class FakeSlotPage:
    def __init__(self, labels):
        self._labels = labels

    def query_selector_all(self, selector):
        if selector == ".abc-slotpicker label":
            return self._labels
        return []


def test_select_time_slot_clicks_the_matching_available_radio():
    target_input = FakeElement()
    other_input = FakeElement()
    page = FakeSlotPage([
        FakeLabel("09:00Vendita chiusa o sold out", other_input),
        FakeLabel("09:45Disponibilità: 4", target_input),
    ])
    assert select_time_slot(page, "09:45") is True
    assert target_input.clicked is True
    assert other_input.clicked is False


def test_select_time_slot_returns_false_when_the_matching_time_is_disabled():
    disabled_input = FakeElement(attrs={"disabled": ""})
    page = FakeSlotPage([FakeLabel("09:45Vendita chiusa o sold out", disabled_input)])
    assert select_time_slot(page, "09:45") is False
    assert disabled_input.clicked is False


def test_select_time_slot_returns_false_when_time_not_found():
    page = FakeSlotPage([FakeLabel("09:45Disponibilità: 4", FakeElement())])
    assert select_time_slot(page, "10:30") is False


# --- add_to_cart / is_cart_empty ---------------------------------------------

class FakeCartPage:
    def __init__(self, buttons, showcart_visible):
        self._buttons = buttons
        self._showcart_visible = showcart_visible

    def query_selector_all(self, selector):
        if selector == "button":
            return self._buttons
        return []

    def query_selector(self, selector):
        if selector == "#btn-showcart":
            return FakeElement(visible=self._showcart_visible)
        return None

    def wait_for_timeout(self, ms):
        pass


def test_add_to_cart_returns_true_when_cart_becomes_non_empty():
    page = FakeCartPage(buttons=[], showcart_visible=False)
    add_button = FakeElement(text="Aggiungi", on_click=lambda: setattr(page, "_showcart_visible", True))
    page._buttons = [FakeElement(text="Altro"), add_button]

    assert add_to_cart(page) is True
    assert add_button.clicked is True


def test_add_to_cart_returns_false_when_cart_stays_empty():
    # Mirrors the real observed failure: the button is clickable, the click
    # goes through, but the site's own 403 (Turnstile) means nothing was
    # actually added.
    add_button = FakeElement(text="Aggiungi")
    page = FakeCartPage(buttons=[add_button], showcart_visible=False)
    assert add_to_cart(page) is False


def test_add_to_cart_returns_false_when_button_not_found():
    page = FakeCartPage(buttons=[FakeElement(text="Outro")], showcart_visible=False)
    assert add_to_cart(page) is False


def test_is_cart_empty_reflects_showcart_visibility():
    assert is_cart_empty(FakeCartPage(buttons=[], showcart_visible=False)) is True
    assert is_cart_empty(FakeCartPage(buttons=[], showcart_visible=True)) is False


# --- wait_for_cart_to_empty ---------------------------------------------------

class FakeCartWaitPage:
    def __init__(self, empty_after_n_reloads):
        self.reload_count = 0
        self._empty_after = empty_after_n_reloads
        self.wait_calls = []

    def wait_for_timeout(self, ms):
        self.wait_calls.append(ms)

    def reload(self, wait_until=None):
        self.reload_count += 1

    def wait_for_selector(self, selector, timeout=None):
        pass

    def query_selector(self, selector):
        if selector == "#btn-showcart":
            return FakeElement(visible=self.reload_count < self._empty_after)
        return None


def test_wait_for_cart_to_empty_polls_until_showcart_disappears():
    page = FakeCartWaitPage(empty_after_n_reloads=3)
    result = wait_for_cart_to_empty(page, poll_interval_seconds=5, max_wait_seconds=3600)
    assert result is True
    assert page.reload_count == 3
    assert page.wait_calls == [5000, 5000, 5000]


def test_wait_for_cart_to_empty_gives_up_after_max_wait():
    page = FakeCartWaitPage(empty_after_n_reloads=999)
    result = wait_for_cart_to_empty(page, poll_interval_seconds=10, max_wait_seconds=25)
    assert result is False
    assert page.reload_count == 3
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_colosseum_cart.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'colosseum_monitor.cart'`

- [ ] **Step 3: Create `colosseum_monitor/cart.py`**

```python
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
```

- [ ] **Step 4: Run it to verify it passes**

Run: `pytest tests/test_colosseum_cart.py -v`
Expected: PASS (14 tests)

- [ ] **Step 5: Commit**

```bash
git add colosseum_monitor/cart.py tests/test_colosseum_cart.py
git commit -m "$(cat <<'COMMIT'
Add Colosseum cart module: pick-earliest, set-participants, select-slot, add-to-cart, wait-for-empty

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
COMMIT
)"
```

---

### Task 2: Cart-ready notification + config

**Files:**
- Modify: `colosseum_monitor/notifier.py`
- Modify: `colosseum_monitor/config.py`
- Modify: `tests/test_notifier.py`

**Interfaces:**
- Produces: `colosseum_monitor.notifier.format_cart_ready_message(date, time, ticket_url) -> str`
- Produces: `colosseum_monitor.config.{AUTO_ADD_TO_CART, AUTO_ADD_TO_CART_PARTICIPANTS, CART_POLL_INTERVAL_SECONDS, CART_MAX_WAIT_MINUTES}`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_notifier.py` (append to the existing file, don't remove the current tests):

```python
from colosseum_monitor.notifier import format_cart_ready_message


def test_format_cart_ready_message_includes_date_time_and_url():
    message = format_cart_ready_message("2026-10-22", "09:45", "https://example.com/ticket")
    assert "2026-10-22" in message
    assert "09:45" in message
    assert "https://example.com/ticket" in message
```

(This adds a new import line at the top alongside the existing
`from colosseum_monitor.notifier import format_availability_message`, and
one new test function at the end of the file.)

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_notifier.py -v`
Expected: FAIL with `ImportError: cannot import name 'format_cart_ready_message'`

- [ ] **Step 3: Add `format_cart_ready_message` to `colosseum_monitor/notifier.py`**

Append to the end of `colosseum_monitor/notifier.py`:

```python


def format_cart_ready_message(date, time, ticket_url):
    return (
        f"🎫 AÇÃO NECESSÁRIA: ingresso do Coliseu para {date} às {time} já está no carrinho!\n"
        f"Uma janela do navegador está aberta no seu computador esperando você finalizar a compra.\n"
        f"Ela fecha sozinha quando o carrinho esvaziar (você finalizando, ou expirando).\n"
        f"{ticket_url}"
    )
```

- [ ] **Step 4: Run it to verify it passes**

Run: `pytest tests/test_notifier.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Add the new config constants**

In `colosseum_monitor/config.py`, after the existing `SMTP_PORT = 587` line, add:

```python

AUTO_ADD_TO_CART = True
AUTO_ADD_TO_CART_PARTICIPANTS = 2
CART_POLL_INTERVAL_SECONDS = 30
CART_MAX_WAIT_MINUTES = 60
```

- [ ] **Step 6: Run the full test suite**

Run: `pytest tests/ -v`
Expected: PASS, no failures

- [ ] **Step 7: Commit**

```bash
git add colosseum_monitor/notifier.py colosseum_monitor/config.py tests/test_notifier.py
git commit -m "$(cat <<'COMMIT'
Add cart-ready notification wording and auto-add-to-cart config

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
COMMIT
)"
```

---

### Task 3: Wire the cart flow into `run.py`

**Files:**
- Modify: `colosseum_monitor/run.py` (full rewrite of the file's contents below)
- Modify: `README.md`

**Interfaces:**
- Consumes: everything produced in Task 1 (`colosseum_monitor.cart.*`) and Task 2 (`format_cart_ready_message`, the four new config constants)
- Consumes: `monitor_common.state.load_state`, `monitor_common.logger.append_log` (both already used elsewhere in this repo)
- Produces: `colosseum_monitor.run.check_once(fetch_days=None, send_message=None, now=None) -> int` — same public signature as today, unchanged

No new automated tests in this task — the pieces being wired together
(real `sync_playwright` browser orchestration and the notification-
suppression wrapper) aren't practically unit-testable without mocking
Playwright itself, matching how `_real_fetch_days`/`_real_send_message`
have never been unit tested for any of the four monitors in this repo
already; the existing `tests/test_run.py` (which injects fakes for both
`fetch_days` and `send_message`, bypassing this wiring entirely) continues
to pass unchanged and is the regression check for this task.

- [ ] **Step 1: Replace the full contents of `colosseum_monitor/run.py`**

```python
"""Entry point: check ticket calendar day statuses once and notify on new openings."""

import os
import sys
from datetime import datetime, timezone

from patchright.sync_api import sync_playwright

from colosseum_monitor import config
from colosseum_monitor.notifier import format_availability_message, format_cart_ready_message
from colosseum_monitor.calendar_client import (
    navigate_to_month,
    read_visible_month_days,
    click_day,
    read_time_slots,
)
from colosseum_monitor.cart import (
    pick_earliest_newly_available,
    set_participant_count,
    select_time_slot,
    add_to_cart,
    wait_for_cart_to_empty,
)
from monitor_common.engine import check_once as _engine_check_once
from monitor_common.notifier import send_whatsapp_message, send_email_message
from monitor_common.state import load_state
from monitor_common.logger import append_log


def check_once(fetch_days=None, send_message=None, now=None):
    # cart_notified is shared between this run's fetch_days and
    # send_message: if the cart flow below already sent its own urgent
    # "finish checkout now" email, the generic "it's available" email that
    # the shared engine would otherwise send for the same date must not
    # also go out once fetch_days finally returns (possibly much later,
    # after the whole cart hold-and-wait finished).
    cart_notified = {"sent": False}

    def _default_fetch_days():
        return _real_fetch_days(cart_notified)

    def _default_send_message(content):
        if cart_notified["sent"]:
            return
        _real_send_message(content)

    return _engine_check_once(
        config,
        format_availability_message=lambda dates, slots: format_availability_message(dates, slots, config.TICKET_URL),
        fetch_days=fetch_days or _default_fetch_days,
        send_message=send_message or _default_send_message,
        now=now,
    )


def _open_ticket_page(browser):
    page = browser.new_page()
    page.goto(config.TICKET_URL, wait_until="domcontentloaded")
    # Site shows a "Waiting" holding page before settling into the real
    # one; wait for the actual calendar rather than guessing a fixed
    # delay, which was intermittently too short and logged spurious
    # "Calendar title not found" failures.
    page.wait_for_selector(".ui-datepicker-title", timeout=30000)
    # Fresh (non-persistent) browser session -> the cookie consent banner
    # is present every run and otherwise intercepts clicks on the
    # calendar's "next month" arrow.
    accept_cookies_button = page.query_selector("#cookie_action_close_header")
    if accept_cookies_button:
        accept_cookies_button.click(force=True)
    navigate_to_month(page, config.CALENDAR_YEAR, config.CALENDAR_MONTH)
    return page


def _log_cart(message):
    append_log(config.LOG_PATH, f"{datetime.now(timezone.utc).isoformat()} CART {message}")


def _real_fetch_days(cart_notified):
    # headless=False: the WAF blocks headless Chromium outright, confirmed by testing.
    # window-position off-screen: keeps the required real browser window from
    # popping up in front of the user every 5 minutes.
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--window-position=-32000,-32000", "--window-size=1280,800"],
        )
        try:
            page = _open_ticket_page(browser)
            all_days = read_visible_month_days(page)
            statuses = {date: status for date, status in all_days.items() if date in config.TARGET_DATES}

            # Only "available" days are clickable at all (soldout/closing days
            # render as <span>, not <a>) -- so this only ever runs for the
            # handful of dates actually worth knowing the exact times for.
            slots = {}
            for date_str, status in statuses.items():
                if status != "available":
                    continue
                day_number = int(date_str[-2:])
                if click_day(page, day_number):
                    page.wait_for_selector(".abc-slotpicker", timeout=15000)
                    slots[date_str] = read_time_slots(page)
        finally:
            browser.close()

    if config.AUTO_ADD_TO_CART:
        previous = load_state(config.STATE_PATH)
        pick = pick_earliest_newly_available(previous["day_statuses"], statuses, slots)
        if pick:
            try:
                _attempt_cart_hold(pick[0], pick[1], cart_notified)
            except Exception as exc:
                _log_cart(f"unexpected error during cart hold for {pick[0]} {pick[1]}: {exc}")

    return {"statuses": statuses, "slots": slots}


def _attempt_cart_hold(date_str, time_str, cart_notified):
    day_number = int(date_str[-2:])
    with sync_playwright() as p:
        # On-screen (not off-screen like the routine check above) and
        # deliberately a second, separate browser rather than repositioning
        # the one above -- see the design doc for why.
        browser = p.chromium.launch(
            headless=False,
            args=["--window-position=100,100", "--window-size=1280,900"],
        )
        try:
            page = _open_ticket_page(browser)

            # Re-verify: the gap since the check above is real, and slots
            # move fast enough that this is not a formality.
            if not click_day(page, day_number):
                _log_cart(f"{date_str} no longer clickable on re-check, skipping cart hold")
                return
            page.wait_for_selector(".abc-slotpicker", timeout=15000)
            current_slots = read_time_slots(page)
            if current_slots.get(time_str) != "available":
                _log_cart(f"{date_str} {time_str} no longer available on re-check, skipping cart hold")
                return

            set_participant_count(page, config.AUTO_ADD_TO_CART_PARTICIPANTS)
            if not select_time_slot(page, time_str):
                _log_cart(f"could not select {date_str} {time_str}, skipping cart hold")
                return
            if not add_to_cart(page):
                _log_cart(f"add-to-cart failed for {date_str} {time_str} (Turnstile, or the slot closed)")
                return

            _log_cart(f"added {date_str} {time_str} to cart, notifying and holding the browser open")
            _real_send_message(format_cart_ready_message(date_str, time_str, config.TICKET_URL))
            cart_notified["sent"] = True

            emptied = wait_for_cart_to_empty(page, config.CART_POLL_INTERVAL_SECONDS, config.CART_MAX_WAIT_MINUTES * 60)
            if emptied:
                _log_cart(f"cart is empty again for {date_str} {time_str}, resuming normal monitoring")
            else:
                _log_cart(
                    f"gave up waiting for the cart to empty for {date_str} {time_str} "
                    f"after {config.CART_MAX_WAIT_MINUTES} min, resuming normal monitoring anyway"
                )
        finally:
            browser.close()


def _real_send_message(content):
    # Both channels, independently -- CallMeBot's free tier sometimes confirms
    # "Message queued" for messages that never actually arrive, so email stays
    # as a backup rather than a straight replacement. Any failure (partial or
    # total) is reported so it still shows up in the log.
    errors = []

    try:
        send_whatsapp_message(
            phone=os.environ["WHATSAPP_PHONE"],
            api_key=os.environ["CALLMEBOT_API_KEY"],
            text=content,
        )
    except Exception as exc:
        errors.append(f"WhatsApp: {exc}")

    try:
        send_email_message(
            smtp_host=config.SMTP_HOST,
            smtp_port=config.SMTP_PORT,
            username=os.environ["GMAIL_ADDRESS"],
            password=os.environ["GMAIL_APP_PASSWORD"],
            to_address=os.environ.get("NOTIFY_TO_EMAIL") or os.environ["GMAIL_ADDRESS"],
            subject="Monitor Coliseu",
            body=content,
        )
    except Exception as exc:
        errors.append(f"Email: {exc}")

    if errors:
        raise RuntimeError("; ".join(errors))


if __name__ == "__main__":
    sys.exit(check_once())
```

- [ ] **Step 2: Run the full test suite**

Run: `pytest tests/ -v`
Expected: PASS, no failures — `tests/test_run.py` in particular still passes
unchanged, since it always passes its own `fetch_days`/`send_message`
fakes and never touches `_default_fetch_days`/`_default_send_message`.

- [ ] **Step 3: Commit**

```bash
git add colosseum_monitor/run.py
git commit -m "$(cat <<'COMMIT'
Wire auto-add-to-cart into the Colosseum monitor's run loop

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
COMMIT
)"
```

- [ ] **Step 4: Live verification note (read before the next real opening)**

This feature's happy path (a real add-to-cart succeeding, a real cart
later emptying) cannot be rehearsed without a genuine target slot opening
-- the design doc already covers this. The very next time `log.txt` shows
a `CART` line, check it against these expectations before trusting the
feature:

- `CART added <date> <time> to cart, notifying and holding the browser open`
  should be followed shortly after by an actual email arriving, and a
  visible, on-screen (not off-screen) Chromium window on the machine
  running the Scheduled Task.
- If instead you see
  `CART add-to-cart failed for <date> <time> (Turnstile, or the slot closed)`,
  that's the documented, expected failure mode (Section "Confirmed
  technical findings" in the design doc) — the monitor should still have
  sent the normal "it's available, hurry" email as a fallback (check
  `log.txt` for the usual `ERROR notification failed` pattern if even that
  didn't arrive, e.g. CallMeBot's quota).
- If a `CART gave up waiting ... after 60 min` line ever appears, that
  means checkout was never finished and the site didn't auto-expire the
  cart within an hour either — worth a manual check on whether the ticket
  is actually still reserved.

- [ ] **Step 5: Document the feature in `README.md`**

In `README.md`, find the existing numbered list near the top (the one
describing what changed after the original build) — it currently ends at
item 5, "**It never alerts about its own failures, only about real ticket
availability.**" Add a new item 6 right after it:

```markdown
6. **It automatically adds a newly-available target slot to the cart and
   holds it open for you.** When one of the 5 target dates opens with a
   real bookable time, the monitor opens a second, on-screen browser
   window (separate from the regular off-screen one used for routine
   checks), re-verifies the slot is still open, sets 2 participants,
   selects the date/time, and clicks "Aggiungi" (add to cart). If that
   succeeds, it emails immediately and then just watches the cart — once
   it's empty again (you finished checkout, or it expired on its own), the
   browser closes and routine 5-minute monitoring resumes. It never goes
   past "add to cart": no payment info, no attempt to solve the site's own
   Cloudflare Turnstile challenge if that's what blocks the add-to-cart
   call (a real, observed failure mode — see `log.txt` for `CART
   add-to-cart failed ...` lines). Turn it off with
   `AUTO_ADD_TO_CART = False` in `colosseum_monitor/config.py` if it
   misbehaves; no other code change needed.
```

- [ ] **Step 6: Commit**

```bash
git add README.md
git commit -m "$(cat <<'COMMIT'
Document Colosseum monitor auto-add-to-cart in the README

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
COMMIT
)"
```

---

## Self-review notes

- **Spec coverage**: earliest-date-then-time selection, the second on-screen
  browser (not a repositioned one), re-verification before adding, the
  Turnstile-403 failure mode, the `is_cart_empty`-driven wait instead of a
  guessed duration, the `AUTO_ADD_TO_CART` off-switch, and the
  never-touch-checkout boundary are all covered by Tasks 1–3 above.
- **Type/signature consistency checked**: `pick_earliest_newly_available`
  returns exactly the `(date_str, time_str)` tuple shape that
  `_attempt_cart_hold(pick[0], pick[1], cart_notified)` unpacks;
  `wait_for_cart_to_empty`'s `bool` return is used by `_attempt_cart_hold`
  to pick the right log line; `format_cart_ready_message(date, time,
  ticket_url)`'s parameter order matches exactly how it's called in
  `_attempt_cart_hold`.
- **No placeholders**: the one true unknown from the design doc (the exact
  shape of a successful vs. failed `/mtajax/addtocart` response) is handled
  by never depending on that response directly — success is read from
  `is_cart_empty` instead, which is already confirmed live and doesn't
  require guessing at network response formats.
