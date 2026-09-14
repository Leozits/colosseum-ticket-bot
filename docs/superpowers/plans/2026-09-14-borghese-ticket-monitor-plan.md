# Galleria Borghese Ticket Monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a fourth ticket-availability monitor, for the Galleria Borghese (Rome), reusing the existing `monitor_common` engine unchanged and following the Louvre monitor's package shape.

**Architecture:** New sibling package `borghese_monitor/` — `config.py`, `calendar_client.py` (patchright-driven DOM reading, site-specific), `messages.py`, and a thin `run.py` wiring into `monitor_common.engine.check_once()`. The site's 3-tier availability signal (alta/moderata/ridotta) is collapsed to the existing binary `"available"`/`"unavailable"` vocabulary so nothing in `monitor_common` needs to change. Notification is email-only (no WhatsApp attempt) since CallMeBot's free-tier quota is currently exhausted.

**Tech Stack:** Python, `patchright` (the site is behind Akamai Bot Manager — same non-headless browser-automation technique already proven against Cloudflare/Octofence in this repo), `pytest`.

## Global Constraints

- Target dates: 2026-10-22, 2026-10-23, 2026-10-24, 2026-10-25, 2026-10-27 (2026-10-26 excluded — already booked for the Vatican).
- `MONITOR_END_DATE`: `2026-10-27`.
- Ticket type: standard/full-price entry ticket.
- Notification: email only. Do not call `send_whatsapp_message` from this monitor.
- The 3-tier availability signal (`data-availability-indicator` values / "Disponibilità alta/moderata/ridotta") is collapsed to `"available"`/`"unavailable"` — do not attempt to preserve the finer grain.
- Recommended Scheduled Task cadence: 30 minutes (materially gentler than the other monitors' 5 minutes, given Akamai's tougher protection and the pattern-observation goal).

---

## Confirmed technical findings (from live testing, not assumption)

- `tosc.it` (TicketOne, the platform Galleria Borghese sells through) is behind **Akamai Bot Manager**: a bare `curl` request gets no HTTP response at all — the TCP connection is reset immediately after the request is sent (`Recv failure: Connection was reset`) — and the resolved IP (`23.201.217.233`) is in Akamai's address space. This is behavioral/fingerprinting protection, tougher than the Cloudflare/Octofence WAFs the other three monitors deal with.
- The calendar's month header is `<span class="btn-today text-center">Settembre 2026</span>` (Italian month name + year, single text node).
- Month navigation: `<button aria-label="Vai al mese precedente">` / `<button aria-label="Vai al mese prossimo">` inside a `.btn-group.cal-month-switch` container. Confirmed live: clicking "Vai al mese prossimo" advances the header from "Settembre 2026" to "Ottobre 2026".
- Each day is a `<div class="cal-month-day">` containing a `<span class="day-number" data-cal-date="YYYY-MM-DD">` whose `class` carries `cal-event-status-available` or `cal-event-status-unavailable`. Days with no event on sale yet (outside the current sale window, or the Galleria's closed Mondays) have **no** `data-cal-date` attribute at all on their `.day-number` span.
- Inside an available day's same `.cal-month-day`, each bookable time slot is a `<span class="event-time-pill" data-availability-indicator="N">HH:MM</span>`. Confirmed live: `data-availability-indicator="0"` is a placeholder for "nothing open" — its displayed time text is a dummy `"00:00"`, not a real time, and it carries `aria-hidden="true"`. Any other indicator value (1/2/3, corresponding to "Disponibilità ridotta/moderata/alta") is a real bookable time slot with a real `HH:MM` text.
- As of 2026-09-14, the site's own sale window ends 2026-10-18 — days 2026-10-19 through 2026-10-31 (which includes every target date) have no `data-cal-date` attribute yet, i.e. no event on sale. This is expected and matches the pattern already seen with the Colosseum and Louvre monitors before their target windows opened.

---

### Task 1: Borghese config + calendar client

**Files:**
- Create: `borghese_monitor/__init__.py`
- Create: `borghese_monitor/config.py`
- Create: `borghese_monitor/calendar_client.py`
- Create: `tests/test_borghese_calendar_client.py`

**Interfaces:**
- Produces: `borghese_monitor.config.{TICKET_URL, CALENDAR_YEAR, CALENDAR_MONTH, TARGET_DATES, MONITOR_END_DATE, STATE_PATH, LOG_PATH, SMTP_HOST, SMTP_PORT}`
- Produces: `borghese_monitor.calendar_client.read_current_month(page) -> (year: int, month: int)`, `navigate_to_month(page, target_year, target_month) -> None`, `read_month_days(page) -> {"statuses": dict[str, str], "slots": dict[str, dict[str, str]]}`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_borghese_calendar_client.py`:

```python
import pytest
from borghese_monitor.calendar_client import read_current_month, navigate_to_month, read_month_days

_MONTH_NAMES = [
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
]


class FakeElement:
    def __init__(self, text="", attrs=None):
        self._text = text
        self._attrs = attrs or {}

    def inner_text(self):
        return self._text

    def get_attribute(self, name):
        return self._attrs.get(name)


class FakeCell:
    def __init__(self, day_span=None, pills=None):
        self._day_span = day_span
        self._pills = pills or []

    def query_selector(self, selector):
        if selector == ".day-number[data-cal-date]":
            return self._day_span
        return None

    def query_selector_all(self, selector):
        if selector == ".event-time-pill":
            return self._pills
        return []


class FakeDaysPage:
    def __init__(self, cells):
        self._cells = cells

    def query_selector_all(self, selector):
        if selector == ".cal-month-day":
            return self._cells
        return []


class FakeMonthPage:
    def __init__(self, month_name, year):
        self.year = year
        self.month = _MONTH_NAMES.index(month_name.lower()) + 1
        self.click_log = []
        self.wait_calls = 0

    def query_selector(self, selector):
        if selector == ".btn-today.text-center":
            return FakeElement(text=f"{_MONTH_NAMES[self.month - 1].capitalize()} {self.year}")
        return None

    def click(self, selector, force=False):
        self.click_log.append(selector)
        step = 1 if selector == 'button[aria-label="Vai al mese prossimo"]' else -1
        total = self.year * 12 + self.month + step
        self.year, month_zero_based = divmod(total - 1, 12)
        self.month = month_zero_based + 1

    def wait_for_timeout(self, ms):
        self.wait_calls += 1


class StuckFakeMonthPage(FakeMonthPage):
    def click(self, selector, force=False):
        self.click_log.append(selector)  # month never actually advances


def test_read_current_month_parses_italian_month_name_and_year():
    page = FakeMonthPage("Settembre", 2026)
    assert read_current_month(page) == (2026, 9)


def test_navigate_to_month_clicks_next_for_future_month():
    page = FakeMonthPage("Settembre", 2026)
    navigate_to_month(page, 2026, 10)
    assert page.click_log == ['button[aria-label="Vai al mese prossimo"]']


def test_navigate_to_month_clicks_previous_for_past_month():
    page = FakeMonthPage("Ottobre", 2026)
    navigate_to_month(page, 2026, 9)
    assert page.click_log == ['button[aria-label="Vai al mese precedente"]']


def test_navigate_to_month_does_nothing_when_already_on_target():
    page = FakeMonthPage("Ottobre", 2026)
    navigate_to_month(page, 2026, 10)
    assert page.click_log == []


def test_navigate_to_month_raises_if_calendar_never_advances():
    page = StuckFakeMonthPage("Settembre", 2026)
    with pytest.raises(TimeoutError):
        navigate_to_month(page, 2026, 10)


def test_read_month_days_maps_available_class_and_lists_real_slots():
    cell = FakeCell(
        day_span=FakeElement(attrs={"data-cal-date": "2026-10-23", "class": "day-number cal-event-status-available"}),
        pills=[
            FakeElement(text="19:00", attrs={"data-availability-indicator": "2"}),
            FakeElement(text="00:00", attrs={"data-availability-indicator": "0"}),
        ],
    )
    page = FakeDaysPage([cell])
    assert read_month_days(page) == {
        "statuses": {"2026-10-23": "available"},
        "slots": {"2026-10-23": {"19:00": "available"}},
    }


def test_read_month_days_maps_missing_status_class_to_unavailable():
    cell = FakeCell(day_span=FakeElement(attrs={"data-cal-date": "2026-10-25", "class": "day-number"}))
    page = FakeDaysPage([cell])
    assert read_month_days(page) == {"statuses": {"2026-10-25": "unavailable"}, "slots": {}}


def test_read_month_days_skips_cells_without_a_day_number():
    page = FakeDaysPage([FakeCell(day_span=None)])
    assert read_month_days(page) == {"statuses": {}, "slots": {}}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_borghese_calendar_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'borghese_monitor'`

- [ ] **Step 3: Create `borghese_monitor/__init__.py`** (empty file)

- [ ] **Step 4: Create `borghese_monitor/config.py`**

```python
"""Configuration constants for the Galleria Borghese ticket availability monitor."""

import os

_PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))

TICKET_URL = "https://www.tosc.it/artist/galleria-borghese/galleria-borghese-2253937/"

CALENDAR_YEAR = 2026
CALENDAR_MONTH = 10

TARGET_DATES = [
    "2026-10-22", "2026-10-23", "2026-10-24", "2026-10-25", "2026-10-27",
]

MONITOR_END_DATE = "2026-10-27"

STATE_PATH = os.path.join(_PACKAGE_DIR, "state.json")
LOG_PATH = os.path.join(_PACKAGE_DIR, "log.txt")

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
```

- [ ] **Step 5: Create `borghese_monitor/calendar_client.py`**

```python
"""Reads Galleria Borghese ticket-calendar day statuses via genuine browser interaction.

tosc.it (TicketOne) is protected by Akamai Bot Manager -- confirmed by
direct testing: a bare HTTP request gets no response at all (the TCP
connection is reset immediately), and the resolved IP is in Akamai's
address space. This is behavioral/fingerprinting protection, not a
one-time JS challenge, so there's no guaranteed workaround -- only
looking as close to a real, infrequent visit as possible (see the design
doc for the resulting much lower poll cadence used by the Scheduled Task).

Each day is a <div class="cal-month-day"> containing a
<span class="day-number" data-cal-date="YYYY-MM-DD"> whose class carries
"cal-event-status-available" or "cal-event-status-unavailable" -- days with
no event on sale yet have no data-cal-date attribute at all. An available
day's same .cal-month-day additionally contains one
<span class="event-time-pill" data-availability-indicator="N">HH:MM</span>
per bookable time slot; indicator "0" is a placeholder for "nothing open"
(its time text is a dummy "00:00", not real) and is skipped -- any other
indicator value means that specific time is bookable at some level (the
site's own alta/moderata/ridotta 3-tier signal, collapsed here to a plain
"available", per the design doc).
"""

_MONTH_NAMES = [
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
]


def read_current_month(page):
    """Return (year, month) currently displayed in the calendar header."""
    header = page.query_selector(".btn-today.text-center").inner_text().strip()
    month_name, year = header.rsplit(" ", 1)
    return int(year), _MONTH_NAMES.index(month_name.strip().lower()) + 1


def navigate_to_month(page, target_year, target_month):
    """Click the calendar's prev/next arrow until the target month is displayed."""
    current_year, current_month = read_current_month(page)
    delta = (target_year * 12 + target_month) - (current_year * 12 + current_month)
    selector = (
        'button[aria-label="Vai al mese prossimo"]' if delta > 0
        else 'button[aria-label="Vai al mese precedente"]'
    )
    step = 1 if delta > 0 else -1
    for _ in range(abs(delta)):
        expected_total = current_year * 12 + current_month + step
        # force=True: various transient elements can sit on top of this
        # button depending on timing -- same defensive click style already
        # proven necessary for the Colosseum and Louvre monitors' calendar
        # navigation.
        page.click(selector, force=True)
        # Polling the visible month header (rather than trusting a fixed
        # delay or a network response event) is what actually proved
        # reliable for the Louvre monitor's own month navigation -- applying
        # the same lesson here up front instead of re-discovering it live.
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
    """Read every day cell in the currently-displayed calendar month.

    Returns {"statuses": {date_str ("YYYY-MM-DD"): "available" | "unavailable"},
              "slots": {date_str: {time_str ("HH:MM"): "available"}}} --
    "slots" only has an entry for a date when at least one real bookable
    time was found for it.
    """
    statuses = {}
    slots = {}
    for cell in page.query_selector_all(".cal-month-day"):
        day_span = cell.query_selector(".day-number[data-cal-date]")
        if day_span is None:
            continue
        date_str = day_span.get_attribute("data-cal-date")
        css_class = day_span.get_attribute("class") or ""
        statuses[date_str] = "available" if "cal-event-status-available" in css_class else "unavailable"

        day_slots = {}
        for pill in cell.query_selector_all(".event-time-pill"):
            indicator = pill.get_attribute("data-availability-indicator")
            if indicator in (None, "0"):
                continue
            time_text = pill.inner_text().strip()
            day_slots[time_text] = "available"
        if day_slots:
            slots[date_str] = day_slots

    return {"statuses": statuses, "slots": slots}
```

- [ ] **Step 6: Run it to verify it passes**

Run: `pytest tests/test_borghese_calendar_client.py -v`
Expected: PASS (8 tests)

- [ ] **Step 7: Commit**

```bash
git add borghese_monitor/__init__.py borghese_monitor/config.py borghese_monitor/calendar_client.py tests/test_borghese_calendar_client.py
git commit -m "Add Galleria Borghese monitor config and calendar client

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: Borghese messages + run.py wiring (email-only)

**Files:**
- Create: `borghese_monitor/messages.py`
- Create: `borghese_monitor/run.py`
- Create: `tests/test_borghese_messages.py`
- Create: `tests/test_borghese_run.py`

**Interfaces:**
- Consumes: `borghese_monitor.config` (Task 1), `borghese_monitor.calendar_client.navigate_to_month/read_month_days` (Task 1), `monitor_common.engine.check_once` (existing), `monitor_common.notifier.send_email_message` (existing)
- Produces: `borghese_monitor.run.check_once(fetch_days=None, send_message=None, now=None) -> int`

- [ ] **Step 1: Write the failing tests for messages**

Create `tests/test_borghese_messages.py`:

```python
from borghese_monitor.messages import format_availability_message


def test_format_availability_message_lists_each_date():
    message = format_availability_message(["2026-10-22", "2026-10-27"], "https://example.com")
    assert "- 2026-10-22" in message
    assert "- 2026-10-27" in message
    assert "https://example.com" in message
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_borghese_messages.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'borghese_monitor.messages'`

- [ ] **Step 3: Create `borghese_monitor/messages.py`**

```python
"""Site-specific email message wording for the Galleria Borghese monitor."""


def format_availability_message(dates, ticket_url):
    lines = [f"- {date}" for date in dates]
    return "O calendário da Galleria Borghese abriu para essas datas!\n" + "\n".join(lines) + f"\n{ticket_url}"
```

- [ ] **Step 4: Run it to verify it passes**

Run: `pytest tests/test_borghese_messages.py -v`
Expected: PASS (1 test)

- [ ] **Step 5: Write the failing tests for `run.py` wiring**

Create `tests/test_borghese_run.py`:

```python
import json
from borghese_monitor import config
from borghese_monitor.run import check_once


def _result(statuses):
    return {"statuses": statuses, "slots": {}}


def test_check_once_notifies_with_borghese_wording_when_a_date_becomes_available(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(config, "LOG_PATH", str(tmp_path / "log.txt"))
    with open(config.STATE_PATH, "w") as f:
        json.dump({"day_statuses": {"2026-10-22": "unavailable"}, "available_slots": {}, "consecutive_failures": 0}, f)

    sent = []
    result = check_once(
        fetch_days=lambda: _result({"2026-10-22": "available"}),
        send_message=lambda msg: sent.append(msg),
    )

    assert result == 0
    assert len(sent) == 1
    assert "Borghese" in sent[0]
    assert "2026-10-22" in sent[0]
    assert config.TICKET_URL in sent[0]


def test_check_once_does_not_notify_when_nothing_changed(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(config, "LOG_PATH", str(tmp_path / "log.txt"))
    days = {"2026-10-22": "unavailable"}
    with open(config.STATE_PATH, "w") as f:
        json.dump({"day_statuses": days, "available_slots": {}, "consecutive_failures": 0}, f)

    sent = []
    result = check_once(fetch_days=lambda: _result(days), send_message=lambda msg: sent.append(msg))

    assert result == 0
    assert sent == []


def test_check_once_skips_entirely_after_monitor_end_date(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(config, "LOG_PATH", str(tmp_path / "log.txt"))
    monkeypatch.setattr(config, "MONITOR_END_DATE", "2000-01-01")

    calls = []
    result = check_once(fetch_days=lambda: calls.append(1), send_message=lambda m: None)

    assert result == 0
    assert calls == []
```

- [ ] **Step 6: Run it to verify it fails**

Run: `pytest tests/test_borghese_run.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'borghese_monitor.run'`

- [ ] **Step 7: Create `borghese_monitor/run.py`**

```python
"""Entry point: check the Galleria Borghese ticket calendar once and notify on new openings."""

import os
import sys

from patchright.sync_api import sync_playwright

from borghese_monitor import config
from borghese_monitor.messages import format_availability_message
from borghese_monitor.calendar_client import navigate_to_month, read_month_days
from monitor_common.engine import check_once as _engine_check_once
from monitor_common.notifier import send_email_message


def check_once(fetch_days=None, send_message=None, now=None):
    return _engine_check_once(
        config,
        format_availability_message=lambda dates, slots: format_availability_message(dates, config.TICKET_URL),
        fetch_days=fetch_days or _real_fetch_days,
        send_message=send_message or _real_send_message,
        now=now,
    )


def _real_fetch_days():
    # headless=False: non-headless is the proven-safe choice for every WAF
    # in this repo so far; Akamai's own bot management is tougher than the
    # others, so there is even less reason to risk headless here.
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--window-position=-32000,-32000", "--window-size=1280,800"],
        )
        try:
            page = browser.new_page()
            page.goto(config.TICKET_URL, wait_until="domcontentloaded")
            page.wait_for_selector(".btn-today.text-center", timeout=30000)
            navigate_to_month(page, config.CALENDAR_YEAR, config.CALENDAR_MONTH)
            result = read_month_days(page)
            statuses = {date: status for date, status in result["statuses"].items() if date in config.TARGET_DATES}
            slots = {date: s for date, s in result["slots"].items() if date in config.TARGET_DATES}
            return {"statuses": statuses, "slots": slots}
        finally:
            browser.close()


def _real_send_message(content):
    # Email only -- WhatsApp via CallMeBot has no free-tier quota left (see
    # the other monitors' history); attempting it here would just add
    # guaranteed-failing noise to the log for no benefit.
    send_email_message(
        smtp_host=config.SMTP_HOST,
        smtp_port=config.SMTP_PORT,
        username=os.environ["GMAIL_ADDRESS"],
        password=os.environ["GMAIL_APP_PASSWORD"],
        to_address=os.environ.get("NOTIFY_TO_EMAIL") or os.environ["GMAIL_ADDRESS"],
        subject="Monitor Galleria Borghese",
        body=content,
    )


if __name__ == "__main__":
    sys.exit(check_once())
```

- [ ] **Step 8: Run it to verify it passes**

Run: `pytest tests/test_borghese_run.py -v`
Expected: PASS (3 tests)

- [ ] **Step 9: Run the full test suite**

Run: `pytest tests/ -v`
Expected: PASS, no failures

- [ ] **Step 10: Commit**

```bash
git add borghese_monitor/messages.py borghese_monitor/run.py tests/test_borghese_messages.py tests/test_borghese_run.py
git commit -m "Add Galleria Borghese monitor messages and run entry point (email-only)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: Live smoke test + Windows Scheduled Task (30-min cadence) + README

**Files:**
- Modify: `README.md` (add a Galleria Borghese section)

- [ ] **Step 1: Run one real check against the live site**

Run (using the same credentials already configured for the other monitors — `GMAIL_ADDRESS`/`GMAIL_APP_PASSWORD` are the only ones this monitor needs, since it's email-only):

```bash
GMAIL_ADDRESS="<your gmail>" GMAIL_APP_PASSWORD="<app password>" python -m borghese_monitor.run
```

Expected: a non-headless Chromium window opens off-screen briefly, the command exits 0, and `borghese_monitor/log.txt` now contains one `OK` line listing all 5 target dates. As of 2026-09-14 the site's sale window doesn't yet reach any of them (all should show `unavailable`), so no notification should fire on this baseline run — but if the site has opened up by the time this runs for real, a real email notification WILL fire, which is correct behavior, not a bug.

If this fails, check the error in `borghese_monitor/log.txt` — Akamai may present differently than expected the first time a real (not manually-driven) patchright session hits it. Do not retry rapidly; a single retry after a few minutes is fine, but repeated rapid attempts risk the same kind of block the Louvre monitor hit.

- [ ] **Step 2: Inspect the resulting state**

Run: `cat borghese_monitor/state.json` (or open it in an editor)
Expected: valid JSON with a `day_statuses` key containing exactly the 5 target dates, and `consecutive_failures: 0`.

- [ ] **Step 3: Register the Windows Scheduled Task at a 30-minute cadence**

```powershell
$action = New-ScheduledTaskAction -Execute "<path to>\pythonw.exe" -Argument "-m borghese_monitor.run" -WorkingDirectory "<path to>\colosseum-ticket-bot"
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 30) -RepetitionDuration (New-TimeSpan -Days 200)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
Register-ScheduledTask -TaskName "BorgheseTicketMonitor" -Action $action -Trigger $trigger -Settings $settings -Description "Checks Galleria Borghese ticket calendar every 30 min; notifies by email only."
```

(30-minute cadence, not the other monitors' 5 minutes — deliberately gentler given Akamai's tougher protection and the pattern-observation goal; see the design doc.)

- [ ] **Step 4: Add a Galleria Borghese section to `README.md`**

After the Versailles section at the end of `README.md`, add:

```markdown
## Galleria Borghese monitor

Watches `https://www.tosc.it/artist/galleria-borghese/galleria-borghese-2253937/`
(TicketOne's platform) for the standard entry ticket, dates 22, 23, 24, 25,
27 October 2026 (26 excluded — already booked for the Vatican).

This site is behind **Akamai Bot Manager**, confirmed tougher than the
other three WAFs in this repo — a bare HTTP request gets no response at
all (the TCP connection resets immediately). There's no guaranteed
workaround for Akamai's behavioral detection, only minimizing how bot-like
this looks: same non-headless patchright technique as the Colosseum and
Louvre monitors, but on a **30-minute cadence instead of 5 minutes**. The
goal here is explicitly understanding the availability pattern over time
(see the design doc), not catching a sub-5-minute window, so the gentler
cadence costs little.

Notifications are **email only** for this monitor (no WhatsApp attempt) —
CallMeBot's free-tier quota is exhausted; add `send_whatsapp_message` back
into `borghese_monitor/run.py`'s `_real_send_message` once that's resolved,
following the pattern in the other monitors.

The site's own 3-tier availability signal ("Disponibilità alta / moderata
/ ridotta") is collapsed to a plain available/unavailable in the state and
logs — see the design doc for why.

Register its own Scheduled Task (independent of the other monitors, 30-min
cadence):

```powershell
$action = New-ScheduledTaskAction -Execute "<path to>\pythonw.exe" -Argument "-m borghese_monitor.run" -WorkingDirectory "<path to>\colosseum-ticket-bot"
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 30) -RepetitionDuration (New-TimeSpan -Days 200)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
Register-ScheduledTask -TaskName "BorgheseTicketMonitor" -Action $action -Trigger $trigger -Settings $settings -Description "Checks Galleria Borghese ticket calendar every 30 min; notifies by email only."
```

State and logs live in `borghese_monitor/state.json` and
`borghese_monitor/log.txt`. If this monitor starts failing persistently
(matching the Louvre monitor's Cloudflare-block history), disable the
Scheduled Task and wait — do not guess a fixed cooldown and auto-reactivate
on a timer; that already proved unreliable once.
```

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "Document the Galleria Borghese monitor's setup

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

(`borghese_monitor/state.json` and `borghese_monitor/log.txt` from Step 1 are real run output, not source — leave them uncommitted, matching the other three monitors' convention.)

---

## Self-review notes

- **Spec coverage**: Akamai findings, DOM structure, 3-tier-to-binary collapse, email-only notification, 30-min cadence, target dates/end date, testing plan, and non-goals from the design doc all map to a task above.
- **Type/signature consistency checked**: `read_month_days(page)` returns exactly the `{"statuses": ..., "slots": ...}` shape `monitor_common.engine.check_once`'s `fetch_days` callable is documented to return; `borghese_monitor.run.check_once`'s wrapping of `format_availability_message` into a `(dates, slots) -> str` lambda matches the same pattern already used by `louvre_monitor.run` and `versailles_monitor.run`.
- **No placeholders**: the one open question from the design doc (month-navigation mechanism) was resolved by live testing before writing this plan, not deferred into a task step — every step above has complete, runnable code.
