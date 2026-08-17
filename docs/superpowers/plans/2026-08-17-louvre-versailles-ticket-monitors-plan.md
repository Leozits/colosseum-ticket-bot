# Louvre + Versailles Ticket Monitors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing Colosseum ticket-availability monitor to two more official ticket sites — the Musée du Louvre and the Château de Versailles — for the user's Paris trip window (14–19 October 2026), reusing proven notification/state/logging logic via a new shared `monitor_common` package.

**Architecture:** Extract the Colosseum monitor's site-agnostic logic (state persistence, logging, day-status diffing, WhatsApp/email sending, and the run-once orchestration skeleton) into `monitor_common/`. Build two new sibling packages, `louvre_monitor/` and `versailles_monitor/`, each with its own `config.py`, `calendar_client.py` (the only truly site-specific piece — how day statuses are actually fetched), `messages.py`, and a thin `run.py` that wires everything into `monitor_common.engine.check_once()`. `colosseum_monitor` is refactored to use the same shared engine, with no behavior change.

**Tech Stack:** Python, `patchright` (Louvre — same Cloudflare-challenge-clearing browser automation as Colosseum), `httpx` (Versailles — plain HTTP, no browser needed), `pytest`.

## Global Constraints

- Target dates for both new monitors: 2026-10-14 through 2026-10-19 (all 6 days).
- `MONITOR_END_DATE` for both new monitors: `2026-10-19` (matches the last target date, same pattern as the Colosseum monitor).
- v1 scope is day-level availability only — no per-time-slot detail for Louvre or Versailles (`slots` is always `{}` for these two sites).
- Every new/moved module keeps the existing project's plain-function style (no classes) and existing docstring conventions.
- Notification wording for the two new monitors follows the Colosseum monitor's Portuguese tone (`"O calendário do X abriu para essas datas!"` / `"O monitor do X falhou N vezes seguidas."`).
- Nothing in this plan touches `colosseum_monitor`'s target dates, ticket URL, or notification behavior — only where its shared logic physically lives.

---

## Confirmed technical findings (from live testing, not assumption)

- **Louvre** (`ticket.louvre.fr`) is behind Cloudflare bot management: a bare `curl` to either the ticket page or its calendar endpoint returns `403` with a `Cf-Mitigated: challenge` header and a "Just a moment..." interstitial. It requires a real, JS-executing browser — same constraint as the Colosseum site, same `patchright` non-headless fix.
- Once past the challenge, Louvre's calendar renders each day as `<input type="checkbox" data-date="2026-10-14T03:00:00.000Z" disabled>` inside `#calendarContainer` — `disabled` present means unavailable. The currently-displayed month is shown in `<span class="d-month">` (full English month name) and `<span class="d-year">`; `#d-next` / `#d-previous` are the navigation buttons, and clicking `#d-next` advances the calendar (confirmed live: August → September → October, with real day data returned for each).
- **Versailles** (`ticket.chateauversailles.fr`) has no bot-blocking on its calendar endpoint — confirmed by a direct, cookie-less `curl POST https://ticket.chateauversailles.fr/en/api/calendar` with body `month=10&year=2026`, which returned a real `200` with `{"#markup": "<html fragment>"}`. Each day in that HTML is `<div id="agenda--calendar--date-2026-10-14" class="agenda--calendar-slot open ...">` (or `closed`/`disabled`). No browser needed at all.
- **Live result as of 2026-08-17**: Louvre shows all of October 2026 as unavailable (not yet open for booking). **Versailles shows 2026-10-14 through 2026-10-18 as `open` already** (`2026-10-19` is `closed`) — see the callout at the end of this plan.

---

## Part A — Extract the shared `monitor_common` library

### Task 1: Extract `state.py` and `logger.py` into `monitor_common`

**Files:**
- Create: `monitor_common/__init__.py`
- Create: `monitor_common/state.py`
- Create: `monitor_common/logger.py`
- Create: `tests/test_monitor_common_state.py`
- Create: `tests/test_monitor_common_logger.py`
- Modify: `colosseum_monitor/run.py:9-18` (import lines only)
- Delete: `colosseum_monitor/state.py`, `colosseum_monitor/logger.py`, `tests/test_state.py`, `tests/test_logger.py`

**Interfaces:**
- Produces: `monitor_common.state.load_state(path) -> dict`, `monitor_common.state.save_state(path, state) -> None`, `monitor_common.state.DEFAULT_STATE`
- Produces: `monitor_common.logger.format_log_line(timestamp, day_statuses) -> str`, `format_change_log_line(timestamp, changes) -> str`, `format_error_log_line(timestamp, error_message) -> str`, `format_slots_log_line(timestamp, slots_by_date) -> str`, `append_log(path, line) -> None`

- [ ] **Step 1: Write the failing tests for `monitor_common.state`**

Create `tests/test_monitor_common_state.py`:

```python
import json
from monitor_common.state import load_state, save_state, DEFAULT_STATE


def test_default_state_shape():
    assert DEFAULT_STATE == {"day_statuses": {}, "available_slots": {}, "consecutive_failures": 0}


def test_load_state_returns_default_when_file_missing(tmp_path):
    path = str(tmp_path / "state.json")
    assert load_state(path) == DEFAULT_STATE


def test_save_then_load_roundtrips(tmp_path):
    path = str(tmp_path / "state.json")
    state = {
        "day_statuses": {"2026-09-12": "soldout"},
        "available_slots": {},
        "consecutive_failures": 1,
    }
    save_state(path, state)
    assert load_state(path) == state


def test_save_state_writes_valid_json(tmp_path):
    path = str(tmp_path / "state.json")
    save_state(path, {"day_statuses": {}, "available_slots": {}, "consecutive_failures": 0})
    with open(path) as f:
        json.load(f)  # does not raise
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_monitor_common_state.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'monitor_common'`

- [ ] **Step 3: Create the `monitor_common` package and `state.py`**

Create `monitor_common/__init__.py` (empty file).

Create `monitor_common/state.py`:

```python
"""Load/save monitor state (last known day statuses + consecutive failure count) as JSON."""

import json
import os

DEFAULT_STATE = {"day_statuses": {}, "available_slots": {}, "consecutive_failures": 0}


def load_state(path):
    if not os.path.exists(path):
        return dict(DEFAULT_STATE)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(path, state):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)
```

- [ ] **Step 4: Run it to verify it passes**

Run: `pytest tests/test_monitor_common_state.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Write the failing tests for `monitor_common.logger`**

Create `tests/test_monitor_common_logger.py`:

```python
from monitor_common.logger import (
    format_log_line,
    format_change_log_line,
    format_error_log_line,
    format_slots_log_line,
    append_log,
)


def test_format_log_line_includes_timestamp_and_sorted_dates():
    line = format_log_line("2026-08-12T10:00:00+00:00", {"2026-09-13": "closing", "2026-09-12": "soldout"})
    assert line == "2026-08-12T10:00:00+00:00 OK 2026-09-12=soldout 2026-09-13=closing"


def test_format_change_log_line_lists_each_transition():
    changes = [
        {"date": "2026-09-12", "from": "closing", "to": "soldout"},
        {"date": "2026-09-13", "from": "closing", "to": "available"},
    ]
    line = format_change_log_line("2026-08-12T10:00:00+00:00", changes)
    assert line == "2026-08-12T10:00:00+00:00 CHANGE 2026-09-12:closing->soldout 2026-09-13:closing->available"


def test_format_error_log_line_includes_message():
    line = format_error_log_line("2026-08-12T10:00:00+00:00", "boom")
    assert line == "2026-08-12T10:00:00+00:00 ERROR boom"


def test_format_slots_log_line_lists_available_times_per_date():
    slots_by_date = {
        "2026-09-16": {"13:15": "available", "13:30": "available", "14:00": "closed"},
        "2026-09-17": {"09:00": "closed"},
    }
    line = format_slots_log_line("2026-08-13T10:00:00+00:00", slots_by_date)
    assert line == "2026-08-13T10:00:00+00:00 SLOTS 2026-09-16:[13:15,13:30] 2026-09-17:[]"


def test_append_log_appends_without_truncating(tmp_path):
    path = str(tmp_path / "log.txt")
    append_log(path, "line one")
    append_log(path, "line two")
    with open(path) as f:
        assert f.read() == "line one\nline two\n"
```

- [ ] **Step 6: Run it to verify it fails**

Run: `pytest tests/test_monitor_common_logger.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'monitor_common.logger'`

- [ ] **Step 7: Create `monitor_common/logger.py`**

```python
"""Append-only log of each monitor run, for auditability."""


def format_log_line(timestamp, day_statuses):
    parts = " ".join(f"{date}={status}" for date, status in sorted(day_statuses.items()))
    return f"{timestamp} OK {parts}"


def format_change_log_line(timestamp, changes):
    parts = " ".join(f"{c['date']}:{c['from']}->{c['to']}" for c in changes)
    return f"{timestamp} CHANGE {parts}"


def format_error_log_line(timestamp, error_message):
    return f"{timestamp} ERROR {error_message}"


def format_slots_log_line(timestamp, slots_by_date):
    parts = []
    for date, slots in sorted(slots_by_date.items()):
        available_times = sorted(t for t, status in slots.items() if status == "available")
        parts.append(f"{date}:[{','.join(available_times)}]")
    return f"{timestamp} SLOTS {' '.join(parts)}"


def append_log(path, line):
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
```

- [ ] **Step 8: Run it to verify it passes**

Run: `pytest tests/test_monitor_common_logger.py -v`
Expected: PASS (5 tests)

- [ ] **Step 9: Delete the old Colosseum-specific copies and their tests**

Delete these 4 files: `colosseum_monitor/state.py`, `colosseum_monitor/logger.py`, `tests/test_state.py`, `tests/test_logger.py`.

- [ ] **Step 10: Update `colosseum_monitor/run.py`'s imports**

In `colosseum_monitor/run.py`, replace:

```python
from colosseum_monitor.state import load_state, save_state
from colosseum_monitor.logger import (
    format_log_line,
    format_change_log_line,
    format_slots_log_line,
    format_error_log_line,
    append_log,
)
```

with:

```python
from monitor_common.state import load_state, save_state
from monitor_common.logger import (
    format_log_line,
    format_change_log_line,
    format_slots_log_line,
    format_error_log_line,
    append_log,
)
```

- [ ] **Step 11: Run the full test suite to confirm nothing broke**

Run: `pytest tests/ -v`
Expected: PASS, no failures, no collection errors (the deleted `test_state.py`/`test_logger.py` are simply gone; `test_run.py` and everything else still passes since `colosseum_monitor/run.py`'s behavior is unchanged, just its import source)

- [ ] **Step 12: Commit**

```bash
git add monitor_common tests/test_monitor_common_state.py tests/test_monitor_common_logger.py colosseum_monitor/run.py
git rm colosseum_monitor/state.py colosseum_monitor/logger.py tests/test_state.py tests/test_logger.py
git commit -m "Extract state and logger modules into shared monitor_common package"
```

---

### Task 2: Extract day-status diffing into `monitor_common/diff.py`

**Files:**
- Create: `monitor_common/diff.py`
- Create: `tests/test_monitor_common_diff.py`
- Modify: `colosseum_monitor/availability.py` (remove `find_status_changes`/`find_newly_available`)
- Modify: `tests/test_availability.py` (remove their tests)
- Modify: `colosseum_monitor/run.py:10` (import line only)

**Interfaces:**
- Produces: `monitor_common.diff.find_status_changes(previous, current) -> list[dict]`, `monitor_common.diff.find_newly_available(previous, current) -> list[str]`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_monitor_common_diff.py`:

```python
from monitor_common.diff import find_status_changes, find_newly_available


def test_find_status_changes_detects_transition():
    previous = {"2026-09-12": "closing"}
    current = {"2026-09-12": "soldout"}
    assert find_status_changes(previous, current) == [{"date": "2026-09-12", "from": "closing", "to": "soldout"}]


def test_find_status_changes_ignores_unchanged_dates():
    previous = {"2026-09-12": "soldout"}
    current = {"2026-09-12": "soldout"}
    assert find_status_changes(previous, current) == []


def test_find_status_changes_treats_new_date_as_change_from_none():
    previous = {}
    current = {"2026-09-13": "closing"}
    assert find_status_changes(previous, current) == [{"date": "2026-09-13", "from": None, "to": "closing"}]


def test_find_newly_available_detects_transition_to_available():
    previous = {"2026-10-23": "closing"}
    current = {"2026-10-23": "available"}
    assert find_newly_available(previous, current) == ["2026-10-23"]


def test_find_newly_available_ignores_non_available_transitions():
    previous = {"2026-09-12": "closing"}
    current = {"2026-09-12": "soldout"}
    assert find_newly_available(previous, current) == []


def test_find_newly_available_ignores_already_available_dates():
    previous = {"2026-10-23": "available"}
    current = {"2026-10-23": "available"}
    assert find_newly_available(previous, current) == []
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_monitor_common_diff.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'monitor_common.diff'`

- [ ] **Step 3: Create `monitor_common/diff.py`**

```python
"""Pure functions for diffing day-status snapshots between runs, shared by every ticket monitor."""


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
```

- [ ] **Step 4: Run it to verify it passes**

Run: `pytest tests/test_monitor_common_diff.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Remove the moved functions and their tests from Colosseum's copies**

In `colosseum_monitor/availability.py`, delete the `find_status_changes` and `find_newly_available` function definitions (keep `parse_calendar_title`, `classify_day_status`, `classify_slot_status`, and the module docstring/`_ITALIAN_MONTHS` dict as-is).

In `tests/test_availability.py`, remove the `find_status_changes`/`find_newly_available` import names and their 6 test functions (`test_find_status_changes_detects_transition`, `test_find_status_changes_ignores_unchanged_dates`, `test_find_status_changes_treats_new_date_as_change_from_none`, `test_find_newly_available_detects_transition_to_available`, `test_find_newly_available_ignores_non_available_transitions`, `test_find_newly_available_ignores_already_available_dates`). The remaining import line becomes:

```python
from colosseum_monitor.availability import (
    parse_calendar_title,
    classify_day_status,
    classify_slot_status,
)
```

- [ ] **Step 6: Update `colosseum_monitor/run.py`'s import**

Replace:

```python
from colosseum_monitor.availability import find_status_changes, find_newly_available
```

with:

```python
from monitor_common.diff import find_status_changes, find_newly_available
```

- [ ] **Step 7: Run the full test suite**

Run: `pytest tests/ -v`
Expected: PASS, no failures

- [ ] **Step 8: Commit**

```bash
git add monitor_common/diff.py tests/test_monitor_common_diff.py colosseum_monitor/availability.py tests/test_availability.py colosseum_monitor/run.py
git commit -m "Extract day-status diffing into monitor_common.diff"
```

---

### Task 3: Extract notification senders into `monitor_common/notifier.py`

**Files:**
- Create: `monitor_common/notifier.py`
- Create: `tests/test_monitor_common_notifier.py`
- Modify: `colosseum_monitor/notifier.py` (remove `send_whatsapp_message`/`send_email_message` and their now-unused imports)
- Modify: `tests/test_notifier.py` (remove their tests)
- Modify: `colosseum_monitor/run.py` (import line + nothing else — `_real_send_message` already calls these by name)

**Interfaces:**
- Produces: `monitor_common.notifier.send_whatsapp_message(phone, api_key, text) -> None`, `monitor_common.notifier.send_email_message(smtp_host, smtp_port, username, password, to_address, subject, body) -> None`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_monitor_common_notifier.py`:

```python
import pytest
from unittest.mock import patch, Mock, MagicMock
from monitor_common.notifier import send_whatsapp_message, send_email_message


@patch("monitor_common.notifier.requests.get")
def test_send_whatsapp_message_posts_expected_params(mock_get):
    mock_get.return_value = Mock(status_code=200, text="Message queued. You will receive it in a few seconds.")

    send_whatsapp_message("5511985600509", "8502714", "hello")

    mock_get.assert_called_once_with(
        "https://api.callmebot.com/whatsapp.php",
        params={"phone": "5511985600509", "text": "hello", "apikey": "8502714"},
        timeout=15,
    )


@patch("monitor_common.notifier.requests.get")
def test_send_whatsapp_message_raises_on_http_error(mock_get):
    mock_response = Mock()
    mock_response.raise_for_status.side_effect = Exception("500 error")
    mock_get.return_value = mock_response

    with pytest.raises(Exception):
        send_whatsapp_message("5511985600509", "8502714", "hello")


@patch("monitor_common.notifier.requests.get")
def test_send_whatsapp_message_raises_when_not_confirmed(mock_get):
    mock_get.return_value = Mock(status_code=200, raise_for_status=Mock(), text="Invalid apikey.")

    with pytest.raises(RuntimeError):
        send_whatsapp_message("5511985600509", "8502714", "hello")


@patch("monitor_common.notifier.smtplib.SMTP")
def test_send_email_message_logs_in_and_sends(mock_smtp_class):
    mock_server = MagicMock()
    mock_smtp_class.return_value.__enter__.return_value = mock_server

    send_email_message(
        smtp_host="smtp.gmail.com",
        smtp_port=587,
        username="me@gmail.com",
        password="app-password",
        to_address="me@gmail.com",
        subject="Subject",
        body="Body text",
    )

    mock_smtp_class.assert_called_once_with("smtp.gmail.com", 587, timeout=15)
    mock_server.starttls.assert_called_once()
    mock_server.login.assert_called_once_with("me@gmail.com", "app-password")
    mock_server.send_message.assert_called_once()
    sent_message = mock_server.send_message.call_args[0][0]
    assert sent_message["Subject"] == "Subject"
    assert sent_message["From"] == "me@gmail.com"
    assert sent_message["To"] == "me@gmail.com"
    assert sent_message.get_content().strip() == "Body text"


@patch("monitor_common.notifier.smtplib.SMTP")
def test_send_email_message_raises_on_login_failure(mock_smtp_class):
    mock_server = MagicMock()
    mock_server.login.side_effect = Exception("auth failed")
    mock_smtp_class.return_value.__enter__.return_value = mock_server

    with pytest.raises(Exception):
        send_email_message(
            smtp_host="smtp.gmail.com",
            smtp_port=587,
            username="me@gmail.com",
            password="wrong",
            to_address="me@gmail.com",
            subject="Subject",
            body="Body",
        )
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_monitor_common_notifier.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'monitor_common.notifier'`

- [ ] **Step 3: Create `monitor_common/notifier.py`**

```python
"""Generic senders for WhatsApp (CallMeBot) and email, shared by every ticket monitor.

CallMeBot's free tier confirms "Message queued" even on messages that never
actually get delivered, so email is kept as a backup channel rather than a
straight replacement.
"""

import smtplib
from email.message import EmailMessage

import requests

CALLMEBOT_URL = "https://api.callmebot.com/whatsapp.php"


def send_whatsapp_message(phone, api_key, text):
    response = requests.get(
        CALLMEBOT_URL,
        params={"phone": phone, "text": text, "apikey": api_key},
        timeout=15,
    )
    response.raise_for_status()
    if "Message queued" not in response.text:
        raise RuntimeError(f"CallMeBot did not confirm the message: {response.text!r}")


def send_email_message(smtp_host, smtp_port, username, password, to_address, subject, body):
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = username
    message["To"] = to_address
    message.set_content(body)

    with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
        server.starttls()
        server.login(username, password)
        server.send_message(message)
```

- [ ] **Step 4: Run it to verify it passes**

Run: `pytest tests/test_monitor_common_notifier.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Trim `colosseum_monitor/notifier.py` down to message wording only**

Replace the full contents of `colosseum_monitor/notifier.py` with:

```python
"""Colosseum-specific WhatsApp/email message wording.

Sending itself (WhatsApp via CallMeBot, email via SMTP) lives in
monitor_common.notifier, shared by every ticket monitor in this repo.
"""


def format_availability_message(dates, slots_by_date, ticket_url):
    lines = []
    for date in dates:
        available_times = sorted(
            t for t, status in slots_by_date.get(date, {}).items() if status == "available"
        )
        if available_times:
            lines.append(f"- {date}: {', '.join(available_times)}")
        else:
            lines.append(f"- {date}")
    return "O calendário do Coliseu abriu para essas datas!\n" + "\n".join(lines) + f"\n{ticket_url}"


def format_failure_message(consecutive_failures, error_message):
    return (
        f"O monitor do Coliseu falhou {consecutive_failures} vezes seguidas.\n"
        f"Último erro: {error_message}"
    )
```

- [ ] **Step 6: Trim `tests/test_notifier.py` down to the message-wording tests only**

Replace the full contents of `tests/test_notifier.py` with:

```python
from colosseum_monitor.notifier import format_availability_message, format_failure_message


def test_format_availability_message_lists_each_opened_date_with_times():
    message = format_availability_message(
        ["2026-10-24"],
        {"2026-10-24": {"13:15": "available", "14:00": "closed"}},
        "https://example.com/ticket",
    )
    assert "2026-10-24: 13:15" in message
    assert "14:00" not in message
    assert "https://example.com/ticket" in message


def test_format_availability_message_omits_times_when_none_known():
    message = format_availability_message(["2026-10-24"], {}, "https://example.com/ticket")
    assert "- 2026-10-24" in message
    assert ":" not in message.split("\n")[1]


def test_format_failure_message_includes_count_and_error():
    message = format_failure_message(3, "timeout")
    assert "3 vezes" in message
    assert "timeout" in message
```

- [ ] **Step 7: Update `colosseum_monitor/run.py`'s import**

Replace:

```python
from colosseum_monitor.notifier import (
    format_availability_message,
    format_failure_message,
    send_whatsapp_message,
    send_email_message,
)
```

with:

```python
from colosseum_monitor.notifier import format_availability_message, format_failure_message
from monitor_common.notifier import send_whatsapp_message, send_email_message
```

- [ ] **Step 8: Run the full test suite**

Run: `pytest tests/ -v`
Expected: PASS, no failures

- [ ] **Step 9: Commit**

```bash
git add monitor_common/notifier.py tests/test_monitor_common_notifier.py colosseum_monitor/notifier.py tests/test_notifier.py colosseum_monitor/run.py
git commit -m "Extract WhatsApp/email senders into monitor_common.notifier"
```

---

### Task 4: Build the shared engine and rewire `colosseum_monitor/run.py`

**Files:**
- Create: `monitor_common/engine.py`
- Create: `tests/test_monitor_common_engine.py`
- Modify: `colosseum_monitor/run.py` (replace the `check_once` body with a thin wrapper)

**Interfaces:**
- Consumes: `monitor_common.state.load_state/save_state`, `monitor_common.logger.*`, `monitor_common.diff.find_status_changes/find_newly_available` (all from Tasks 1–2)
- Produces: `monitor_common.engine.check_once(config, format_availability_message, format_failure_message, fetch_days, send_message, now=None) -> int`
  - `config`: object/module with `STATE_PATH`, `LOG_PATH`, `MONITOR_END_DATE`, `CONSECUTIVE_FAILURES_ALERT_THRESHOLD` attributes
  - `format_availability_message`: `callable(newly_available_dates: list[str], slots_by_date: dict) -> str`
  - `format_failure_message`: `callable(consecutive_failures: int, error_message: str) -> str`
  - `fetch_days`: `callable() -> {"statuses": dict[str, str], "slots": dict[str, dict[str, str]]}`
  - `send_message`: `callable(str) -> None`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_monitor_common_engine.py`:

```python
import json
import os
from types import SimpleNamespace

from monitor_common.engine import check_once


def _config(tmp_path, **overrides):
    defaults = dict(
        STATE_PATH=str(tmp_path / "state.json"),
        LOG_PATH=str(tmp_path / "log.txt"),
        MONITOR_END_DATE="2099-01-01",
        CONSECUTIVE_FAILURES_ALERT_THRESHOLD=3,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _result(statuses, slots=None):
    return {"statuses": statuses, "slots": slots or {}}


def _format_availability_message(dates, slots):
    return "AVAILABLE:" + ",".join(dates)


def _format_failure_message(consecutive_failures, error_message):
    return f"FAILED:{consecutive_failures}:{error_message}"


def test_check_once_logs_and_does_not_notify_when_nothing_changed(tmp_path):
    config = _config(tmp_path)
    days = {"2026-09-12": "soldout", "2026-09-13": "closing"}
    with open(config.STATE_PATH, "w") as f:
        json.dump({"day_statuses": days, "available_slots": {}, "consecutive_failures": 0}, f)

    sent = []
    result = check_once(
        config, _format_availability_message, _format_failure_message,
        fetch_days=lambda: _result(days), send_message=lambda msg: sent.append(msg),
    )

    assert result == 0
    assert sent == []
    with open(config.STATE_PATH) as f:
        assert json.load(f)["day_statuses"] == days


def test_check_once_notifies_when_a_date_becomes_available(tmp_path):
    config = _config(tmp_path)
    with open(config.STATE_PATH, "w") as f:
        json.dump({"day_statuses": {"2026-09-13": "closing"}, "available_slots": {}, "consecutive_failures": 0}, f)

    sent = []
    result = check_once(
        config, _format_availability_message, _format_failure_message,
        fetch_days=lambda: _result({"2026-09-13": "available"}),
        send_message=lambda msg: sent.append(msg),
    )

    assert result == 0
    assert sent == ["AVAILABLE:2026-09-13"]


def test_check_once_still_saves_state_when_notification_fails(tmp_path):
    config = _config(tmp_path)
    with open(config.STATE_PATH, "w") as f:
        json.dump({"day_statuses": {"2026-09-13": "closing"}, "available_slots": {}, "consecutive_failures": 0}, f)

    def broken_send(msg):
        raise ConnectionError("smtp unreachable")

    result = check_once(
        config, _format_availability_message, _format_failure_message,
        fetch_days=lambda: _result({"2026-09-13": "available"}), send_message=broken_send,
    )

    assert result == 0
    with open(config.STATE_PATH) as f:
        assert json.load(f)["day_statuses"] == {"2026-09-13": "available"}
    with open(config.LOG_PATH) as f:
        assert "notification failed" in f.read()


def test_check_once_skips_entirely_after_monitor_end_date(tmp_path):
    config = _config(tmp_path, MONITOR_END_DATE="2000-01-01")

    calls = []
    result = check_once(
        config, _format_availability_message, _format_failure_message,
        fetch_days=lambda: calls.append(1), send_message=lambda m: None,
    )

    assert result == 0
    assert calls == []
    assert not os.path.exists(config.STATE_PATH)


def test_check_once_logs_error_and_counts_failures_without_crashing(tmp_path):
    config = _config(tmp_path)

    def boom():
        raise RuntimeError("site unreachable")

    sent = []
    result = check_once(
        config, _format_availability_message, _format_failure_message,
        fetch_days=boom, send_message=lambda msg: sent.append(msg),
    )

    assert result == 1
    assert sent == []
    with open(config.STATE_PATH) as f:
        assert json.load(f)["consecutive_failures"] == 1


def test_check_once_alerts_after_threshold_consecutive_failures(tmp_path):
    config = _config(tmp_path)
    with open(config.STATE_PATH, "w") as f:
        json.dump({"day_statuses": {}, "available_slots": {}, "consecutive_failures": 2}, f)

    def boom():
        raise RuntimeError("site unreachable")

    sent = []
    result = check_once(
        config, _format_availability_message, _format_failure_message,
        fetch_days=boom, send_message=lambda msg: sent.append(msg),
    )

    assert result == 1
    assert sent == ["FAILED:3:site unreachable"]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_monitor_common_engine.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'monitor_common.engine'`

- [ ] **Step 3: Create `monitor_common/engine.py`**

```python
"""Generic run-once engine shared by every ticket monitor: load state, fetch,
diff, log, notify, save state -- with a consecutive-failure alert threshold.
"""

from datetime import date, datetime, timezone

from monitor_common.state import load_state, save_state
from monitor_common.logger import (
    format_log_line,
    format_change_log_line,
    format_slots_log_line,
    format_error_log_line,
    append_log,
)
from monitor_common.diff import find_status_changes, find_newly_available


def _notify_safely(config, send_message, content, timestamp):
    # A notification failure (e.g. the mail server being unreachable) must never
    # crash the run before save_state() -- that would leave state.json stuck on
    # the old snapshot forever, so the same "change" gets re-detected and
    # re-alerted (and re-fails) on every subsequent run indefinitely.
    try:
        send_message(content)
    except Exception as exc:
        append_log(config.LOG_PATH, format_error_log_line(timestamp, f"notification failed: {exc}"))


def check_once(config, format_availability_message, format_failure_message, fetch_days, send_message, now=None):
    """Run one availability check for a single site. Dependencies are injectable for testing.

    config: object/module with STATE_PATH, LOG_PATH, MONITOR_END_DATE,
            CONSECUTIVE_FAILURES_ALERT_THRESHOLD attributes.
    format_availability_message: callable(newly_available_dates, slots_by_date) -> str
    format_failure_message: callable(consecutive_failures, error_message) -> str
    fetch_days: callable() -> {"statuses": dict[date_str, status],
                                "slots": dict[date_str, dict[time_str, status]]}
    send_message: callable(str) -> None
    now: callable() -> datetime (timezone-aware, UTC)
    """
    now = now or (lambda: datetime.now(timezone.utc))

    if date.today() > date.fromisoformat(config.MONITOR_END_DATE):
        print(f"Monitoring window ended on {config.MONITOR_END_DATE}, skipping check.")
        return 0

    previous = load_state(config.STATE_PATH)
    timestamp = now().isoformat()

    try:
        result = fetch_days()
    except Exception as exc:
        consecutive_failures = previous["consecutive_failures"] + 1
        append_log(config.LOG_PATH, format_error_log_line(timestamp, str(exc)))
        if consecutive_failures >= config.CONSECUTIVE_FAILURES_ALERT_THRESHOLD:
            _notify_safely(config, send_message, format_failure_message(consecutive_failures, str(exc)), timestamp)
        save_state(
            config.STATE_PATH,
            {
                "day_statuses": previous["day_statuses"],
                "available_slots": previous.get("available_slots", {}),
                "consecutive_failures": consecutive_failures,
            },
        )
        return 1

    current = result["statuses"]
    current_slots = result["slots"]

    append_log(config.LOG_PATH, format_log_line(timestamp, current))
    if current_slots:
        append_log(config.LOG_PATH, format_slots_log_line(timestamp, current_slots))

    changes = find_status_changes(previous["day_statuses"], current)
    if changes:
        append_log(config.LOG_PATH, format_change_log_line(timestamp, changes))

    newly_available = find_newly_available(previous["day_statuses"], current)
    if newly_available:
        message = format_availability_message(newly_available, current_slots)
        _notify_safely(config, send_message, message, timestamp)

    save_state(
        config.STATE_PATH,
        {"day_statuses": current, "available_slots": current_slots, "consecutive_failures": 0},
    )
    return 0
```

- [ ] **Step 4: Run it to verify it passes**

Run: `pytest tests/test_monitor_common_engine.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Rewrite `colosseum_monitor/run.py` to delegate to the shared engine**

Replace the full contents of `colosseum_monitor/run.py` with:

```python
"""Entry point: check ticket calendar day statuses once and notify on new openings."""

import os
import sys

from patchright.sync_api import sync_playwright

from colosseum_monitor import config
from colosseum_monitor.notifier import format_availability_message, format_failure_message
from colosseum_monitor.calendar_client import (
    advance_to_max_month,
    read_visible_month_days,
    click_day,
    read_time_slots,
)
from monitor_common.engine import check_once as _engine_check_once
from monitor_common.notifier import send_whatsapp_message, send_email_message


def check_once(fetch_days=None, send_message=None, now=None):
    return _engine_check_once(
        config,
        format_availability_message=lambda dates, slots: format_availability_message(dates, slots, config.TICKET_URL),
        format_failure_message=format_failure_message,
        fetch_days=fetch_days or _real_fetch_days,
        send_message=send_message or _real_send_message,
        now=now,
    )


def _real_fetch_days():
    # headless=False: the WAF blocks headless Chromium outright, confirmed by testing.
    # window-position off-screen: keeps the required real browser window from
    # popping up in front of the user every 15 minutes.
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--window-position=-32000,-32000", "--window-size=1280,800"],
        )
        try:
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
            advance_to_max_month(page)
            statuses = read_visible_month_days(page)

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

            return {"statuses": statuses, "slots": slots}
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

(Note: `_real_fetch_days` and `_real_send_message` are unchanged from before — only `check_once` itself changed, from containing the full run-once logic to delegating it to `monitor_common.engine.check_once`.)

- [ ] **Step 6: Run the full test suite**

Run: `pytest tests/ -v`
Expected: PASS, no failures — `tests/test_run.py` (unchanged) still passes because `colosseum_monitor.run.check_once`'s public signature (`fetch_days`, `send_message`, `now` keyword args) and observable behavior are identical, just now implemented via the shared engine.

- [ ] **Step 7: Commit**

```bash
git add monitor_common/engine.py tests/test_monitor_common_engine.py colosseum_monitor/run.py
git commit -m "Extract run-once engine into monitor_common; Colosseum monitor now uses it"
```

---

## Part B — Louvre monitor

### Task 5: Louvre config + calendar client

**Files:**
- Create: `louvre_monitor/__init__.py`
- Create: `louvre_monitor/config.py`
- Create: `louvre_monitor/calendar_client.py`
- Create: `tests/test_louvre_calendar_client.py`

**Interfaces:**
- Produces: `louvre_monitor.config.{TICKET_URL, CALENDAR_YEAR, CALENDAR_MONTH, TARGET_DATES, MONITOR_END_DATE, STATE_PATH, LOG_PATH, CONSECUTIVE_FAILURES_ALERT_THRESHOLD, SMTP_HOST, SMTP_PORT}`
- Produces: `louvre_monitor.calendar_client.read_current_month(page) -> (year: int, month: int)`, `navigate_to_month(page, target_year, target_month) -> None`, `read_month_days(page) -> dict[str, str]`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_louvre_calendar_client.py`:

```python
from louvre_monitor.calendar_client import read_current_month, navigate_to_month, read_month_days


class FakeElement:
    def __init__(self, text="", attrs=None):
        self._text = text
        self._attrs = attrs or {}

    def inner_text(self):
        return self._text

    def get_attribute(self, name):
        return self._attrs.get(name)


class FakePage:
    def __init__(self, month_name, year, day_elements=None):
        self._month_name = month_name
        self._year = year
        self._day_elements = day_elements or []
        self.click_log = []
        self.wait_calls = 0

    def query_selector(self, selector):
        if selector == ".d-month":
            return FakeElement(text=self._month_name)
        if selector == ".d-year":
            return FakeElement(text=str(self._year))
        return None

    def query_selector_all(self, selector):
        if selector == "#calendarContainer input[data-date]":
            return self._day_elements
        return []

    def click(self, selector, force=False):
        self.click_log.append(selector)

    def wait_for_timeout(self, ms):
        self.wait_calls += 1


def test_read_current_month_parses_month_name_and_year():
    page = FakePage("August", 2026)
    assert read_current_month(page) == (2026, 8)


def test_navigate_to_month_clicks_next_for_future_month():
    page = FakePage("August", 2026)
    navigate_to_month(page, 2026, 10)
    assert page.click_log == ["#d-next", "#d-next"]


def test_navigate_to_month_clicks_previous_for_past_month():
    page = FakePage("October", 2026)
    navigate_to_month(page, 2026, 8)
    assert page.click_log == ["#d-previous", "#d-previous"]


def test_navigate_to_month_does_nothing_when_already_on_target():
    page = FakePage("October", 2026)
    navigate_to_month(page, 2026, 10)
    assert page.click_log == []


def test_read_month_days_maps_disabled_attribute_to_unavailable():
    page = FakePage("October", 2026, day_elements=[
        FakeElement(attrs={"data-date": "2026-10-14T03:00:00.000Z"}),
        FakeElement(attrs={"data-date": "2026-10-15T03:00:00.000Z", "disabled": ""}),
    ])
    assert read_month_days(page) == {
        "2026-10-14": "available",
        "2026-10-15": "unavailable",
    }
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_louvre_calendar_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'louvre_monitor'`

- [ ] **Step 3: Create `louvre_monitor/__init__.py`** (empty file)

- [ ] **Step 4: Create `louvre_monitor/config.py`**

```python
"""Configuration constants for the Louvre ticket availability monitor."""

import os

_PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))

TICKET_URL = "https://ticket.louvre.fr/en/billetterie/3313"

CALENDAR_YEAR = 2026
CALENDAR_MONTH = 10

TARGET_DATES = [
    "2026-10-14", "2026-10-15", "2026-10-16",
    "2026-10-17", "2026-10-18", "2026-10-19",
]

MONITOR_END_DATE = "2026-10-19"

STATE_PATH = os.path.join(_PACKAGE_DIR, "state.json")
LOG_PATH = os.path.join(_PACKAGE_DIR, "log.txt")

CONSECUTIVE_FAILURES_ALERT_THRESHOLD = 3

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
```

- [ ] **Step 5: Create `louvre_monitor/calendar_client.py`**

```python
"""Reads Louvre ticket-calendar day statuses via genuine browser interaction.

The site is behind Cloudflare bot management: a bare HTTP request gets a 403
with a `Cf-Mitigated: challenge` header and a "Just a moment..." interstitial
-- confirmed by direct testing. It must be driven from a real, JS-executing
browser, same constraint as the Colosseum monitor. Once past the challenge,
the calendar renders each day as a checkbox input carrying a `data-date`
attribute and a `disabled` attribute when that day isn't bookable, so day
status is read straight from the DOM -- no network interception needed.
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
    for _ in range(abs(delta)):
        # force=True: various transient elements can sit on top of this
        # button depending on timing -- same defensive click style already
        # proven necessary for the Colosseum monitor's calendar navigation.
        page.click(selector, force=True)
        page.wait_for_timeout(2000)


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
```

- [ ] **Step 6: Run it to verify it passes**

Run: `pytest tests/test_louvre_calendar_client.py -v`
Expected: PASS (5 tests)

- [ ] **Step 7: Commit**

```bash
git add louvre_monitor/__init__.py louvre_monitor/config.py louvre_monitor/calendar_client.py tests/test_louvre_calendar_client.py
git commit -m "Add Louvre monitor config and calendar client"
```

---

### Task 6: Louvre messages + run.py wiring

**Files:**
- Create: `louvre_monitor/messages.py`
- Create: `louvre_monitor/run.py`
- Create: `tests/test_louvre_messages.py`
- Create: `tests/test_louvre_run.py`

**Interfaces:**
- Consumes: `louvre_monitor.config` (Task 5), `louvre_monitor.calendar_client.navigate_to_month/read_month_days` (Task 5), `monitor_common.engine.check_once` (Task 4), `monitor_common.notifier.send_whatsapp_message/send_email_message` (Task 3)
- Produces: `louvre_monitor.run.check_once(fetch_days=None, send_message=None, now=None) -> int`

- [ ] **Step 1: Write the failing tests for messages**

Create `tests/test_louvre_messages.py`:

```python
from louvre_monitor.messages import format_availability_message, format_failure_message


def test_format_availability_message_lists_each_date():
    message = format_availability_message(["2026-10-14", "2026-10-15"], "https://example.com")
    assert "- 2026-10-14" in message
    assert "- 2026-10-15" in message
    assert "https://example.com" in message


def test_format_failure_message_includes_count_and_error():
    message = format_failure_message(3, "timeout")
    assert "3 vezes" in message
    assert "timeout" in message
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_louvre_messages.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'louvre_monitor.messages'`

- [ ] **Step 3: Create `louvre_monitor/messages.py`**

```python
"""Site-specific WhatsApp/email message wording for the Louvre monitor."""


def format_availability_message(dates, ticket_url):
    lines = [f"- {date}" for date in dates]
    return "O calendário do Louvre abriu para essas datas!\n" + "\n".join(lines) + f"\n{ticket_url}"


def format_failure_message(consecutive_failures, error_message):
    return (
        f"O monitor do Louvre falhou {consecutive_failures} vezes seguidas.\n"
        f"Último erro: {error_message}"
    )
```

- [ ] **Step 4: Run it to verify it passes**

Run: `pytest tests/test_louvre_messages.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Write the failing tests for `run.py` wiring**

Create `tests/test_louvre_run.py`:

```python
import json
from louvre_monitor import config
from louvre_monitor.run import check_once


def _result(statuses):
    return {"statuses": statuses, "slots": {}}


def test_check_once_notifies_with_louvre_wording_when_a_date_becomes_available(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(config, "LOG_PATH", str(tmp_path / "log.txt"))
    with open(config.STATE_PATH, "w") as f:
        json.dump({"day_statuses": {"2026-10-14": "unavailable"}, "available_slots": {}, "consecutive_failures": 0}, f)

    sent = []
    result = check_once(
        fetch_days=lambda: _result({"2026-10-14": "available"}),
        send_message=lambda msg: sent.append(msg),
    )

    assert result == 0
    assert len(sent) == 1
    assert "Louvre" in sent[0]
    assert "2026-10-14" in sent[0]
    assert config.TICKET_URL in sent[0]


def test_check_once_does_not_notify_when_nothing_changed(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(config, "LOG_PATH", str(tmp_path / "log.txt"))
    days = {"2026-10-14": "unavailable"}
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

Run: `pytest tests/test_louvre_run.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'louvre_monitor.run'`

- [ ] **Step 7: Create `louvre_monitor/run.py`**

```python
"""Entry point: check the Louvre ticket calendar once and notify on new openings."""

import os
import sys

from patchright.sync_api import sync_playwright

from louvre_monitor import config
from louvre_monitor.messages import format_availability_message, format_failure_message
from louvre_monitor.calendar_client import navigate_to_month, read_month_days
from monitor_common.engine import check_once as _engine_check_once
from monitor_common.notifier import send_whatsapp_message, send_email_message


def check_once(fetch_days=None, send_message=None, now=None):
    return _engine_check_once(
        config,
        format_availability_message=lambda dates, slots: format_availability_message(dates, config.TICKET_URL),
        format_failure_message=format_failure_message,
        fetch_days=fetch_days or _real_fetch_days,
        send_message=send_message or _real_send_message,
        now=now,
    )


def _real_fetch_days():
    # headless=False: non-headless is the proven-safe choice already
    # validated for the Colosseum monitor's own Cloudflare/WAF interaction;
    # not yet confirmed whether Louvre's Cloudflare challenge specifically
    # requires it, but there is no reason to risk finding out the hard way.
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--window-position=-32000,-32000", "--window-size=1280,800"],
        )
        try:
            page = browser.new_page()
            page.goto(config.TICKET_URL, wait_until="domcontentloaded")
            # The Cloudflare "Just a moment..." interstitial resolves on its
            # own once its JS challenge passes; wait for the real calendar
            # rather than guessing a fixed delay.
            page.wait_for_selector(".d-month", timeout=30000)
            decline_cookies_button = page.query_selector(".orejime-Notice-declineButton")
            if decline_cookies_button:
                decline_cookies_button.click(force=True)
            navigate_to_month(page, config.CALENDAR_YEAR, config.CALENDAR_MONTH)
            all_days = read_month_days(page)
            statuses = {date: status for date, status in all_days.items() if date in config.TARGET_DATES}
            return {"statuses": statuses, "slots": {}}
        finally:
            browser.close()


def _real_send_message(content):
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
            subject="Monitor Louvre",
            body=content,
        )
    except Exception as exc:
        errors.append(f"Email: {exc}")

    if errors:
        raise RuntimeError("; ".join(errors))


if __name__ == "__main__":
    sys.exit(check_once())
```

- [ ] **Step 8: Run it to verify it passes**

Run: `pytest tests/test_louvre_run.py -v`
Expected: PASS (3 tests)

- [ ] **Step 9: Run the full test suite**

Run: `pytest tests/ -v`
Expected: PASS, no failures

- [ ] **Step 10: Commit**

```bash
git add louvre_monitor/messages.py louvre_monitor/run.py tests/test_louvre_messages.py tests/test_louvre_run.py
git commit -m "Add Louvre monitor messages and run entry point"
```

---

### Task 7: Louvre live smoke test + Windows Scheduled Task + README

**Files:**
- Modify: `README.md` (add a Louvre section)

- [ ] **Step 1: Run one real check against the live site**

Run (with real credentials — same ones already configured for the Colosseum monitor):

```bash
WHATSAPP_PHONE="<your number>" CALLMEBOT_API_KEY="<api key>" GMAIL_ADDRESS="<your gmail>" GMAIL_APP_PASSWORD="<app password>" python -m louvre_monitor.run
```

Expected: a non-headless Chromium window opens off-screen briefly, the command exits 0, and `louvre_monitor/log.txt` now contains one `OK` line listing all 6 target dates. As of 2026-08-17 all of October is unavailable on the official Louvre site, so no notification should fire on this baseline run — but if the site has opened up by the time this runs for real, a real WhatsApp+email notification WILL fire, which is correct behavior, not a bug.

- [ ] **Step 2: Inspect the resulting state**

Run: `cat louvre_monitor/state.json` (or open it in an editor)
Expected: valid JSON with a `day_statuses` key containing exactly the 6 target dates, and `consecutive_failures: 0`.

- [ ] **Step 3: Register the Windows Scheduled Task**

```powershell
$action = New-ScheduledTaskAction -Execute "<path to>\pythonw.exe" -Argument "-m louvre_monitor.run" -WorkingDirectory "<path to>\colosseum-ticket-bot"
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 200)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName "LouvreTicketMonitor" -Action $action -Trigger $trigger -Settings $settings -Description "Checks Louvre ticket calendar every 5 min while this PC is on; notifies by WhatsApp and email."
```

- [ ] **Step 4: Add a Louvre section to `README.md`**

After the existing "GitHub Actions (disabled)" section at the end of `README.md`, add:

```markdown
## Louvre monitor

Same idea as the Colosseum monitor above, watching
`https://ticket.louvre.fr/en/billetterie/3313` for dates 14–19 October 2026
(the user's Paris trip window) instead. Shares the same WhatsApp/email
credentials and setup — no new one-time setup needed beyond what's above.

The Louvre site is behind Cloudflare bot management rather than Octofence,
but the fix is identical: patchright, non-headless, off-screen window. Its
calendar exposes each day as a checkbox with a `disabled` attribute rather
than day-cell CSS classes, but the underlying "drive it like a real user"
approach carries over unchanged.

Register its own Scheduled Task (independent of the Colosseum one, same
5-minute cadence):

```powershell
$action = New-ScheduledTaskAction -Execute "<path to>\pythonw.exe" -Argument "-m louvre_monitor.run" -WorkingDirectory "<path to>\colosseum-ticket-bot"
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 200)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName "LouvreTicketMonitor" -Action $action -Trigger $trigger -Settings $settings -Description "Checks Louvre ticket calendar every 5 min while this PC is on; notifies by WhatsApp and email."
```

State and logs live in `louvre_monitor/state.json` and `louvre_monitor/log.txt`
(kept separate from the Colosseum monitor's files at the repo root).
```

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "Document the Louvre monitor's setup"
```

(`louvre_monitor/state.json` and `louvre_monitor/log.txt` from Step 1 are real run output, not source — commit them separately later along with the repo's existing convention of periodically checking in the Colosseum monitor's own state/log files, not as part of this task.)

---

## Part C — Versailles monitor

### Task 8: Versailles config + calendar client

**Files:**
- Create: `versailles_monitor/__init__.py`
- Create: `versailles_monitor/config.py`
- Create: `versailles_monitor/calendar_client.py`
- Create: `tests/test_versailles_calendar_client.py`
- Modify: `requirements.txt` (add `httpx`)

**Interfaces:**
- Produces: `versailles_monitor.config.{CALENDAR_URL, TICKET_URL, CALENDAR_YEAR, CALENDAR_MONTH, TARGET_DATES, MONITOR_END_DATE, STATE_PATH, LOG_PATH, CONSECUTIVE_FAILURES_ALERT_THRESHOLD, SMTP_HOST, SMTP_PORT}`
- Produces: `versailles_monitor.calendar_client.fetch_month_html(year, month) -> str`, `parse_month_days(html) -> dict[str, str]`

- [ ] **Step 1: Add `httpx` to `requirements.txt`**

Replace the contents of `requirements.txt` with:

```
patchright==1.61.2
requests==2.32.3
httpx==0.27.2
```

Run: `pip install -r requirements.txt`
Expected: `httpx` installs successfully alongside the existing dependencies.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_versailles_calendar_client.py`:

```python
from unittest.mock import patch, Mock
from versailles_monitor.calendar_client import fetch_month_html, parse_month_days


def test_parse_month_days_maps_open_to_available_and_others_to_unavailable():
    html = (
        '<div id="agenda--calendar--date-2026-10-14" class="agenda--calendar-slot open theme--jardins_musicaux">'
        '<span>14</span></div>'
        '<div id="agenda--calendar--date-2026-10-19" class="agenda--calendar-slot closed">'
        '<span>19</span></div>'
        '<div id="agenda--calendar--date-2026-09-01" class="agenda--calendar-slot disabled">'
        '<span>01</span></div>'
    )
    assert parse_month_days(html) == {
        "2026-10-14": "available",
        "2026-10-19": "unavailable",
        "2026-09-01": "unavailable",
    }


def test_parse_month_days_returns_empty_dict_for_no_matches():
    assert parse_month_days("<div>nothing here</div>") == {}


@patch("versailles_monitor.calendar_client.httpx.post")
def test_fetch_month_html_posts_month_and_year_and_returns_markup(mock_post):
    mock_post.return_value = Mock(status_code=200, json=lambda: {"#markup": "<div>ok</div>"})

    result = fetch_month_html(2026, 10)

    mock_post.assert_called_once_with(
        "https://ticket.chateauversailles.fr/en/api/calendar",
        data={"month": 10, "year": 2026},
        timeout=15,
    )
    assert result == "<div>ok</div>"


@patch("versailles_monitor.calendar_client.httpx.post")
def test_fetch_month_html_raises_on_http_error(mock_post):
    mock_response = Mock()
    mock_response.raise_for_status.side_effect = Exception("500 error")
    mock_post.return_value = mock_response

    import pytest
    with pytest.raises(Exception):
        fetch_month_html(2026, 10)
```

- [ ] **Step 3: Run it to verify it fails**

Run: `pytest tests/test_versailles_calendar_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'versailles_monitor'`

- [ ] **Step 4: Create `versailles_monitor/__init__.py`** (empty file)

- [ ] **Step 5: Create `versailles_monitor/config.py`**

```python
"""Configuration constants for the Palace of Versailles ticket availability monitor."""

import os

_PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))

TICKET_URL = "https://ticket.chateauversailles.fr/en"

CALENDAR_YEAR = 2026
CALENDAR_MONTH = 10

TARGET_DATES = [
    "2026-10-14", "2026-10-15", "2026-10-16",
    "2026-10-17", "2026-10-18", "2026-10-19",
]

MONITOR_END_DATE = "2026-10-19"

STATE_PATH = os.path.join(_PACKAGE_DIR, "state.json")
LOG_PATH = os.path.join(_PACKAGE_DIR, "log.txt")

CONSECUTIVE_FAILURES_ALERT_THRESHOLD = 3

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
```

- [ ] **Step 6: Create `versailles_monitor/calendar_client.py`**

```python
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
```

- [ ] **Step 7: Run it to verify it passes**

Run: `pytest tests/test_versailles_calendar_client.py -v`
Expected: PASS (4 tests)

- [ ] **Step 8: Commit**

```bash
git add requirements.txt versailles_monitor/__init__.py versailles_monitor/config.py versailles_monitor/calendar_client.py tests/test_versailles_calendar_client.py
git commit -m "Add Versailles monitor config and calendar client"
```

---

### Task 9: Versailles messages + run.py wiring

**Files:**
- Create: `versailles_monitor/messages.py`
- Create: `versailles_monitor/run.py`
- Create: `tests/test_versailles_messages.py`
- Create: `tests/test_versailles_run.py`

**Interfaces:**
- Consumes: `versailles_monitor.config` (Task 8), `versailles_monitor.calendar_client.fetch_month_html/parse_month_days` (Task 8), `monitor_common.engine.check_once` (Task 4), `monitor_common.notifier.send_whatsapp_message/send_email_message` (Task 3)
- Produces: `versailles_monitor.run.check_once(fetch_days=None, send_message=None, now=None) -> int`

- [ ] **Step 1: Write the failing tests for messages**

Create `tests/test_versailles_messages.py`:

```python
from versailles_monitor.messages import format_availability_message, format_failure_message


def test_format_availability_message_lists_each_date():
    message = format_availability_message(["2026-10-14", "2026-10-18"], "https://example.com")
    assert "- 2026-10-14" in message
    assert "- 2026-10-18" in message
    assert "https://example.com" in message


def test_format_failure_message_includes_count_and_error():
    message = format_failure_message(3, "timeout")
    assert "3 vezes" in message
    assert "timeout" in message
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_versailles_messages.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'versailles_monitor.messages'`

- [ ] **Step 3: Create `versailles_monitor/messages.py`**

```python
"""Site-specific WhatsApp/email message wording for the Versailles monitor."""


def format_availability_message(dates, ticket_url):
    lines = [f"- {date}" for date in dates]
    return "O calendário de Versalhes abriu para essas datas!\n" + "\n".join(lines) + f"\n{ticket_url}"


def format_failure_message(consecutive_failures, error_message):
    return (
        f"O monitor de Versalhes falhou {consecutive_failures} vezes seguidas.\n"
        f"Último erro: {error_message}"
    )
```

- [ ] **Step 4: Run it to verify it passes**

Run: `pytest tests/test_versailles_messages.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Write the failing tests for `run.py` wiring**

Create `tests/test_versailles_run.py`:

```python
import json
from versailles_monitor import config
from versailles_monitor.run import check_once


def _result(statuses):
    return {"statuses": statuses, "slots": {}}


def test_check_once_notifies_with_versailles_wording_when_a_date_becomes_available(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(config, "LOG_PATH", str(tmp_path / "log.txt"))
    with open(config.STATE_PATH, "w") as f:
        json.dump({"day_statuses": {"2026-10-14": "unavailable"}, "available_slots": {}, "consecutive_failures": 0}, f)

    sent = []
    result = check_once(
        fetch_days=lambda: _result({"2026-10-14": "available"}),
        send_message=lambda msg: sent.append(msg),
    )

    assert result == 0
    assert len(sent) == 1
    assert "Versalhes" in sent[0]
    assert "2026-10-14" in sent[0]
    assert config.TICKET_URL in sent[0]


def test_check_once_does_not_notify_when_nothing_changed(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(config, "LOG_PATH", str(tmp_path / "log.txt"))
    days = {"2026-10-14": "unavailable"}
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

Run: `pytest tests/test_versailles_run.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'versailles_monitor.run'`

- [ ] **Step 7: Create `versailles_monitor/run.py`**

```python
"""Entry point: check the Versailles ticket calendar once and notify on new openings."""

import os
import sys

from versailles_monitor import config
from versailles_monitor.messages import format_availability_message, format_failure_message
from versailles_monitor.calendar_client import fetch_month_html, parse_month_days
from monitor_common.engine import check_once as _engine_check_once
from monitor_common.notifier import send_whatsapp_message, send_email_message


def check_once(fetch_days=None, send_message=None, now=None):
    return _engine_check_once(
        config,
        format_availability_message=lambda dates, slots: format_availability_message(dates, config.TICKET_URL),
        format_failure_message=format_failure_message,
        fetch_days=fetch_days or _real_fetch_days,
        send_message=send_message or _real_send_message,
        now=now,
    )


def _real_fetch_days():
    html = fetch_month_html(config.CALENDAR_YEAR, config.CALENDAR_MONTH)
    all_days = parse_month_days(html)
    statuses = {date: status for date, status in all_days.items() if date in config.TARGET_DATES}
    return {"statuses": statuses, "slots": {}}


def _real_send_message(content):
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
            subject="Monitor Versalhes",
            body=content,
        )
    except Exception as exc:
        errors.append(f"Email: {exc}")

    if errors:
        raise RuntimeError("; ".join(errors))


if __name__ == "__main__":
    sys.exit(check_once())
```

- [ ] **Step 8: Run it to verify it passes**

Run: `pytest tests/test_versailles_run.py -v`
Expected: PASS (3 tests)

- [ ] **Step 9: Run the full test suite**

Run: `pytest tests/ -v`
Expected: PASS, no failures

- [ ] **Step 10: Commit**

```bash
git add versailles_monitor/messages.py versailles_monitor/run.py tests/test_versailles_messages.py tests/test_versailles_run.py
git commit -m "Add Versailles monitor messages and run entry point"
```

---

### Task 10: Versailles live smoke test + Windows Scheduled Task + README

**Files:**
- Modify: `README.md` (add a Versailles section)

- [ ] **Step 1: Run one real check against the live site**

Run:

```bash
WHATSAPP_PHONE="<your number>" CALLMEBOT_API_KEY="<api key>" GMAIL_ADDRESS="<your gmail>" GMAIL_APP_PASSWORD="<app password>" python -m versailles_monitor.run
```

Expected: exits 0 in well under a second (plain HTTP call, no browser) and `versailles_monitor/log.txt` now contains one `OK` line listing all 6 target dates.

**Important:** as of 2026-08-17, the live Versailles calendar already shows 2026-10-14 through 2026-10-18 as `open` (only 2026-10-19 is `closed`). Since this is the very first run, there's no prior `state.json`, so every one of those already-open dates will be treated as "newly available" and **a real WhatsApp + email notification will fire immediately** — this is correct, expected behavior (the monitor doing exactly its job on a baseline that happens to already be good news), not a test failure. If the site's real status has changed by the time this step actually runs, the notification contents will differ accordingly — check `versailles_monitor/log.txt`'s `OK` line to see the real live status either way.

- [ ] **Step 2: Inspect the resulting state**

Run: `cat versailles_monitor/state.json` (or open it in an editor)
Expected: valid JSON with a `day_statuses` key containing exactly the 6 target dates, and `consecutive_failures: 0`.

- [ ] **Step 3: Register the Windows Scheduled Task**

```powershell
$action = New-ScheduledTaskAction -Execute "<path to>\pythonw.exe" -Argument "-m versailles_monitor.run" -WorkingDirectory "<path to>\colosseum-ticket-bot"
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 200)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName "VersaillesTicketMonitor" -Action $action -Trigger $trigger -Settings $settings -Description "Checks Versailles ticket calendar every 5 min; notifies by WhatsApp and email."
```

(No `--window-size`/off-screen concerns here — this monitor never opens a browser window at all.)

- [ ] **Step 4: Add a Versailles section to `README.md`**

After the Louvre section added in Task 7, add:

```markdown
## Versailles monitor

Same idea again, watching `https://ticket.chateauversailles.fr` (Passport
ticket: château + gardens + Trianon Estate) for dates 14–19 October 2026.
Shares the same WhatsApp/email credentials and setup — no new one-time setup
needed.

Unlike the other two monitors, Versailles's calendar endpoint has **no
bot-blocking at all** — confirmed by a direct, cookie-less request returning
real data. This monitor makes a plain HTTP call and never opens a browser,
so it's much lighter and faster than the Colosseum/Louvre ones.

Register its own Scheduled Task (independent of the other two, same 5-minute
cadence):

```powershell
$action = New-ScheduledTaskAction -Execute "<path to>\pythonw.exe" -Argument "-m versailles_monitor.run" -WorkingDirectory "<path to>\colosseum-ticket-bot"
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 200)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName "VersaillesTicketMonitor" -Action $action -Trigger $trigger -Settings $settings -Description "Checks Versailles ticket calendar every 5 min; notifies by WhatsApp and email."
```

State and logs live in `versailles_monitor/state.json` and
`versailles_monitor/log.txt`.

**Note on what "open" means:** the calendar endpoint's `open` class reflects
whether the château accepts visitors that day at all, not necessarily
confirmed remaining quota for the Passport ticket specifically (that would
only be knowable further into the booking flow, which this monitor does not
drive). Day-level only, same scope as the other two monitors — see the
design doc for details.
```

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "Document the Versailles monitor's setup"
```

---

## Self-review notes

- **Spec coverage**: every section of the design doc (shared library scope, per-site fetch mechanism, day-level-only v1 scope, error handling via the shared engine, testing plan items 1–5, non-goals) maps to a task above. The design's testing-plan item 4 (hand-edit state to simulate a prior state and confirm notification wording) is covered by `tests/test_louvre_run.py`/`tests/test_versailles_run.py`'s "notifies with correct wording" tests rather than a separate manual step, since it's just as easily automated.
- **Type/signature consistency checked**: `monitor_common.engine.check_once`'s `format_availability_message` parameter is always called as `(dates, slots)` — both Louvre's and Versailles's `run.py` wrap their 2-arg `messages.format_availability_message(dates, ticket_url)` in a lambda matching that shape, exactly like Colosseum's 3-arg version does.
- **No placeholders**: every step above has complete, runnable code — nothing deferred to "later."
