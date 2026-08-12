# Colosseum Ticket Availability Monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a GitHub-Actions-hosted bot that checks the official Colosseum ticketing site every 15 minutes for openings on Oct 23/24/25, 2026 (Full Experience - Sotterranei e Arena ticket) and posts a Discord message the moment one opens.

**Architecture:** A small Python package (`colosseum_monitor`) with pure, independently-tested modules for parsing/diffing availability, state persistence, logging, and Discord notification, plus one integration module that drives a headless Playwright browser to call the site's internal calendar API (required because the endpoint is behind a WAF that blocks non-browser requests). A thin orchestrator (`run.py`) wires these together behind a dependency-injectable `check_once()` function so the orchestration logic itself is unit-testable without a real browser. A GitHub Actions workflow runs it on a cron schedule and commits the updated state/log back to the repo.

**Tech Stack:** Python 3.10+, Playwright (sync API, Chromium), `requests`, `pytest`, GitHub Actions.

## Global Constraints

- Ticket page: `https://ticketing.colosseo.it/eventi/full-experience-sotterranei-e-arena/`
- Ticket's internal `page` id (used in the AJAX call): `225`
- Calendar AJAX endpoint: `POST https://ticketing.colosseo.it/mtajax/calendars_month`, form body `{action: "midaabc_calendars_month", page, year, month}`, JSON response `{success: bool, data: [{startDateTime: str, capacity: int, ...}, ...]}`
- This endpoint 403s (Octofence WAF block page) when called without a real browser session — it must always be invoked via `page.evaluate` on an already-navigated Playwright page, never via a plain HTTP client
- Target year/month: 2026 / 10 (October)
- Target dates: `2026-10-23`, `2026-10-24`, `2026-10-25`
- Monitoring window ends: `2026-10-25` (script no-ops after this date)
- Notification channel: Discord webhook, URL supplied via env var `DISCORD_WEBHOOK_URL` (GitHub Actions secret of the same name)
- Consecutive-failure alert threshold: 3 (only alert on repeated failures, but log every failure)
- Project root: `C:\Users\leonardosiqueira\colosseum-ticket-bot` (already `git init`'d; design doc already committed at `docs/superpowers/specs/2026-08-12-colosseum-ticket-monitor-design.md`)
- All commands below assume the working directory is the project root and are written for Git Bash (the repo will also be used from Windows)

---

## File Structure

```
colosseum-ticket-bot/
├── colosseum_monitor/
│   ├── __init__.py
│   ├── config.py           # constants (Task 1)
│   ├── availability.py      # parse/diff pure functions (Task 2)
│   ├── state.py              # load/save state.json (Task 3)
│   ├── logger.py             # append-only log.txt (Task 4)
│   ├── notifier.py           # Discord webhook messages (Task 5)
│   ├── calendar_client.py    # Playwright-driven AJAX call (Task 6)
│   └── run.py                 # orchestration entry point (Task 7)
├── tests/
│   ├── test_config.py
│   ├── test_availability.py
│   ├── test_state.py
│   ├── test_logger.py
│   ├── test_notifier.py
│   ├── test_calendar_client.py
│   └── test_run.py
├── .github/workflows/check.yml   # cron schedule (Task 8)
├── requirements.txt
├── requirements-dev.txt
├── .gitignore
├── README.md
├── state.json    # committed baseline, then updated by CI (Task 9)
└── log.txt       # committed baseline, then appended by CI (Task 9)
```

---

### Task 1: Project scaffolding + config module

**Files:**
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `.gitignore`
- Create: `colosseum_monitor/__init__.py`
- Create: `colosseum_monitor/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nothing
- Produces: module `colosseum_monitor.config` with constants `TICKET_URL: str`, `TICKET_PAGE_ID: int`, `TARGET_YEAR: int`, `TARGET_MONTH: int`, `TARGET_DATES: list[str]`, `MONITOR_END_DATE: str`, `STATE_PATH: str`, `LOG_PATH: str`, `CONSECUTIVE_FAILURES_ALERT_THRESHOLD: int` — every later task imports these by name.

- [ ] **Step 1: Create the non-Python project files**

`requirements.txt`:
```
playwright==1.47.0
requests==2.32.3
```

`requirements-dev.txt`:
```
-r requirements.txt
pytest==8.3.3
```

`.gitignore`:
```
__pycache__/
*.pyc
.venv/
venv/
```

- [ ] **Step 2: Create the package `__init__.py`**

`colosseum_monitor/__init__.py`:
```python
```
(empty file — just marks the directory as a package)

- [ ] **Step 3: Write the failing test for config**

`tests/test_config.py`:
```python
from colosseum_monitor import config


def test_target_dates_fall_within_target_year_and_month():
    prefix = f"{config.TARGET_YEAR}-{config.TARGET_MONTH:02d}"
    for date_str in config.TARGET_DATES:
        assert date_str.startswith(prefix)


def test_target_dates_are_the_three_expected_days():
    assert config.TARGET_DATES == ["2026-10-23", "2026-10-24", "2026-10-25"]


def test_monitor_end_date_covers_all_target_dates():
    assert config.MONITOR_END_DATE >= max(config.TARGET_DATES)


def test_ticket_page_id_matches_confirmed_value():
    assert config.TICKET_PAGE_ID == 225
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'colosseum_monitor.config'` (or similar import error)

- [ ] **Step 5: Write the implementation**

`colosseum_monitor/config.py`:
```python
"""Configuration constants for the Colosseum ticket availability monitor."""

TICKET_URL = "https://ticketing.colosseo.it/eventi/full-experience-sotterranei-e-arena/"
TICKET_PAGE_ID = 225

TARGET_YEAR = 2026
TARGET_MONTH = 10
TARGET_DATES = ["2026-10-23", "2026-10-24", "2026-10-25"]

MONITOR_END_DATE = "2026-10-25"

STATE_PATH = "state.json"
LOG_PATH = "log.txt"

CONSECUTIVE_FAILURES_ALERT_THRESHOLD = 3
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `python -m pytest tests/test_config.py -v`
Expected: `4 passed`

- [ ] **Step 7: Commit**

```bash
git add requirements.txt requirements-dev.txt .gitignore colosseum_monitor/__init__.py colosseum_monitor/config.py tests/test_config.py
git commit -m "Add project scaffolding and config constants"
```

---

### Task 2: Availability parsing/diffing (pure functions)

**Files:**
- Create: `colosseum_monitor/availability.py`
- Test: `tests/test_availability.py`

**Interfaces:**
- Consumes: nothing (pure functions, no dependency on other project modules)
- Produces: `parse_slots(response_json: dict) -> list[dict]`, `capacity_by_date(slots: list[dict], target_dates: list[str]) -> dict[str, int]`, `find_newly_available(previous: dict[str, int], current: dict[str, int]) -> list[str]` — `run.py` (Task 7) calls all three.

- [ ] **Step 1: Write the failing tests**

`tests/test_availability.py`:
```python
import pytest
from colosseum_monitor.availability import parse_slots, capacity_by_date, find_newly_available


def test_parse_slots_returns_data_list_on_success():
    response = {"success": True, "data": [{"startDateTime": "2026-10-23T06:45:00Z", "capacity": 5}]}
    assert parse_slots(response) == response["data"]


def test_parse_slots_raises_on_missing_success_flag():
    with pytest.raises(ValueError):
        parse_slots({"data": []})


def test_parse_slots_raises_on_non_dict_response():
    with pytest.raises(ValueError):
        parse_slots(["not", "a", "dict"])


def test_capacity_by_date_sums_multiple_slots_same_day():
    slots = [
        {"startDateTime": "2026-10-23T06:45:00Z", "capacity": 5},
        {"startDateTime": "2026-10-23T07:00:00Z", "capacity": 3},
        {"startDateTime": "2026-10-24T06:45:00Z", "capacity": 0},
    ]
    result = capacity_by_date(slots, ["2026-10-23", "2026-10-24", "2026-10-25"])
    assert result == {"2026-10-23": 8, "2026-10-24": 0, "2026-10-25": 0}


def test_capacity_by_date_ignores_slots_outside_target_dates():
    slots = [{"startDateTime": "2026-09-01T06:45:00Z", "capacity": 100}]
    result = capacity_by_date(slots, ["2026-10-23"])
    assert result == {"2026-10-23": 0}


def test_find_newly_available_detects_transition_from_zero():
    previous = {"2026-10-23": 0, "2026-10-24": 0}
    current = {"2026-10-23": 0, "2026-10-24": 5}
    assert find_newly_available(previous, current) == ["2026-10-24"]


def test_find_newly_available_ignores_dates_still_at_zero():
    previous = {"2026-10-23": 0}
    current = {"2026-10-23": 0}
    assert find_newly_available(previous, current) == []


def test_find_newly_available_treats_unknown_previous_date_as_zero():
    previous = {}
    current = {"2026-10-23": 2}
    assert find_newly_available(previous, current) == ["2026-10-23"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_availability.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'colosseum_monitor.availability'`

- [ ] **Step 3: Write the implementation**

`colosseum_monitor/availability.py`:
```python
"""Pure functions for computing ticket availability from the site's calendar API response."""


def parse_slots(response_json):
    """Validate and extract the slot list from a calendars_month API response.

    Raises ValueError if the response doesn't have the expected shape.
    """
    if not isinstance(response_json, dict) or response_json.get("success") is not True:
        raise ValueError(f"Unexpected calendar response shape: {response_json!r}")
    data = response_json.get("data")
    if not isinstance(data, list):
        raise ValueError(f"Unexpected calendar response shape: {response_json!r}")
    return data


def capacity_by_date(slots, target_dates):
    """Sum remaining capacity per date, for the given list of target date strings (YYYY-MM-DD).

    Dates in target_dates with no matching slots are included with capacity 0.
    """
    totals = {date_str: 0 for date_str in target_dates}
    for slot in slots:
        slot_date = slot["startDateTime"][:10]
        if slot_date in totals:
            totals[slot_date] += slot["capacity"]
    return totals


def find_newly_available(previous, current):
    """Return the dates that went from 0 (or unknown) capacity to >0 capacity."""
    newly_available = []
    for date_str, capacity in current.items():
        if capacity > 0 and previous.get(date_str, 0) == 0:
            newly_available.append(date_str)
    return newly_available
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_availability.py -v`
Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add colosseum_monitor/availability.py tests/test_availability.py
git commit -m "Add availability parsing and diffing logic"
```

---

### Task 3: State persistence

**Files:**
- Create: `colosseum_monitor/state.py`
- Test: `tests/test_state.py`

**Interfaces:**
- Consumes: nothing
- Produces: `DEFAULT_STATE: dict` (`{"capacities": {}, "consecutive_failures": 0}`), `load_state(path: str) -> dict`, `save_state(path: str, state: dict) -> None` — `run.py` (Task 7) uses all three.

- [ ] **Step 1: Write the failing tests**

`tests/test_state.py`:
```python
import json
from colosseum_monitor.state import load_state, save_state, DEFAULT_STATE


def test_default_state_shape():
    assert DEFAULT_STATE == {"capacities": {}, "consecutive_failures": 0}


def test_load_state_returns_default_when_file_missing(tmp_path):
    path = str(tmp_path / "state.json")
    assert load_state(path) == DEFAULT_STATE


def test_save_then_load_roundtrips(tmp_path):
    path = str(tmp_path / "state.json")
    state = {"capacities": {"2026-10-23": 5}, "consecutive_failures": 1}
    save_state(path, state)
    assert load_state(path) == state


def test_save_state_writes_valid_json(tmp_path):
    path = str(tmp_path / "state.json")
    save_state(path, {"capacities": {}, "consecutive_failures": 0})
    with open(path) as f:
        json.load(f)  # does not raise
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_state.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'colosseum_monitor.state'`

- [ ] **Step 3: Write the implementation**

`colosseum_monitor/state.py`:
```python
"""Load/save monitor state (last known capacities + consecutive failure count) as JSON."""

import json
import os

DEFAULT_STATE = {"capacities": {}, "consecutive_failures": 0}


def load_state(path):
    if not os.path.exists(path):
        return dict(DEFAULT_STATE)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(path, state):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_state.py -v`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add colosseum_monitor/state.py tests/test_state.py
git commit -m "Add state persistence"
```

---

### Task 4: Append-only log

**Files:**
- Create: `colosseum_monitor/logger.py`
- Test: `tests/test_logger.py`

**Interfaces:**
- Consumes: nothing
- Produces: `format_log_line(timestamp: str, capacities: dict[str, int]) -> str`, `format_error_log_line(timestamp: str, error_message: str) -> str`, `append_log(path: str, line: str) -> None` — `run.py` (Task 7) uses all three.

- [ ] **Step 1: Write the failing tests**

`tests/test_logger.py`:
```python
from colosseum_monitor.logger import format_log_line, format_error_log_line, append_log


def test_format_log_line_includes_timestamp_and_sorted_dates():
    line = format_log_line("2026-08-12T10:00:00+00:00", {"2026-10-24": 0, "2026-10-23": 5})
    assert line == "2026-08-12T10:00:00+00:00 OK 2026-10-23=5 2026-10-24=0"


def test_format_error_log_line_includes_message():
    line = format_error_log_line("2026-08-12T10:00:00+00:00", "boom")
    assert line == "2026-08-12T10:00:00+00:00 ERROR boom"


def test_append_log_appends_without_truncating(tmp_path):
    path = str(tmp_path / "log.txt")
    append_log(path, "line one")
    append_log(path, "line two")
    with open(path) as f:
        assert f.read() == "line one\nline two\n"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_logger.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'colosseum_monitor.logger'`

- [ ] **Step 3: Write the implementation**

`colosseum_monitor/logger.py`:
```python
"""Append-only log of each monitor run, for auditability."""


def format_log_line(timestamp, capacities):
    parts = " ".join(f"{date}={capacity}" for date, capacity in sorted(capacities.items()))
    return f"{timestamp} OK {parts}"


def format_error_log_line(timestamp, error_message):
    return f"{timestamp} ERROR {error_message}"


def append_log(path, line):
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_logger.py -v`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add colosseum_monitor/logger.py tests/test_logger.py
git commit -m "Add append-only run log"
```

---

### Task 5: Discord notifier

**Files:**
- Create: `colosseum_monitor/notifier.py`
- Test: `tests/test_notifier.py`

**Interfaces:**
- Consumes: nothing
- Produces: `format_availability_message(dates: list[str], capacities: dict[str, int], ticket_url: str) -> str`, `format_failure_message(consecutive_failures: int, error_message: str) -> str`, `send_discord_message(webhook_url: str, content: str) -> None` — `run.py` (Task 7) uses all three.

- [ ] **Step 1: Write the failing tests**

`tests/test_notifier.py`:
```python
import pytest
from unittest.mock import patch, Mock
from colosseum_monitor.notifier import (
    format_availability_message,
    format_failure_message,
    send_discord_message,
)


def test_format_availability_message_lists_each_opened_date_with_capacity():
    message = format_availability_message(
        ["2026-10-24"], {"2026-10-23": 0, "2026-10-24": 5}, "https://example.com/ticket"
    )
    assert "2026-10-24: 5 vagas" in message
    assert "https://example.com/ticket" in message
    assert "2026-10-23" not in message


def test_format_failure_message_includes_count_and_error():
    message = format_failure_message(3, "timeout")
    assert "3 vezes" in message
    assert "timeout" in message


@patch("colosseum_monitor.notifier.requests.post")
def test_send_discord_message_posts_content_as_json(mock_post):
    mock_post.return_value = Mock(status_code=204, raise_for_status=Mock())
    send_discord_message("https://discord.example/webhook", "hello")
    mock_post.assert_called_once_with(
        "https://discord.example/webhook", json={"content": "hello"}, timeout=10
    )


@patch("colosseum_monitor.notifier.requests.post")
def test_send_discord_message_raises_on_http_error(mock_post):
    mock_response = Mock()
    mock_response.raise_for_status.side_effect = Exception("500 error")
    mock_post.return_value = mock_response
    with pytest.raises(Exception):
        send_discord_message("https://discord.example/webhook", "hello")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_notifier.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'colosseum_monitor.notifier'`

- [ ] **Step 3: Write the implementation**

`colosseum_monitor/notifier.py`:
```python
"""Send monitor notifications to a Discord channel via webhook."""

import requests


def format_availability_message(dates, capacities, ticket_url):
    lines = [f"- {date}: {capacities[date]} vagas" for date in dates]
    return "🎟️ Disponibilidade aberta no Coliseu!\n" + "\n".join(lines) + f"\n{ticket_url}"


def format_failure_message(consecutive_failures, error_message):
    return (
        f"⚠️ O monitor do Coliseu falhou {consecutive_failures} vezes seguidas.\n"
        f"Último erro: {error_message}"
    )


def send_discord_message(webhook_url, content):
    response = requests.post(webhook_url, json={"content": content}, timeout=10)
    response.raise_for_status()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_notifier.py -v`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add colosseum_monitor/notifier.py tests/test_notifier.py
git commit -m "Add Discord notifier"
```

---

### Task 6: Calendar API client (Playwright-driven)

**Files:**
- Create: `colosseum_monitor/calendar_client.py`
- Test: `tests/test_calendar_client.py`

**Interfaces:**
- Consumes: nothing
- Produces: `build_ajax_payload(page_id: int, year: int, month: int) -> dict`, `fetch_month_calendar(page, page_id: int, year: int, month: int) -> dict` (where `page` is a Playwright `Page` that has already navigated to the ticket URL) — `run.py` (Task 7) uses `fetch_month_calendar`.

Note: `fetch_month_calendar` drives a real browser page and cannot be meaningfully unit-tested with a mock (that would only test the mock). It is verified against the live site in Task 9's manual integration check. Only the pure `build_ajax_payload` helper gets a unit test here.

- [ ] **Step 1: Write the failing test**

`tests/test_calendar_client.py`:
```python
from colosseum_monitor.calendar_client import build_ajax_payload


def test_build_ajax_payload_has_expected_shape():
    payload = build_ajax_payload(225, 2026, 10)
    assert payload == {
        "action": "midaabc_calendars_month",
        "page": 225,
        "year": 2026,
        "month": 10,
    }
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_calendar_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'colosseum_monitor.calendar_client'`

- [ ] **Step 3: Write the implementation**

`colosseum_monitor/calendar_client.py`:
```python
"""Fetches calendar availability data from the ticketing site's internal AJAX endpoint.

The endpoint (/mtajax/calendars_month) sits behind an Octofence WAF that blocks
plain HTTP requests without a real browser session -- it must be called from
inside a Playwright page that has already loaded the ticket page, via
page.evaluate, so the request carries the page's real cookies/session.
"""


def build_ajax_payload(page_id, year, month):
    return {"action": "midaabc_calendars_month", "page": page_id, "year": year, "month": month}


_FETCH_SCRIPT = """
async ({pageId, year, month}) => {
    const body = new URLSearchParams({
        action: "midaabc_calendars_month",
        page: pageId,
        year: year,
        month: month,
    });
    const resp = await fetch("/mtajax/calendars_month", {
        method: "POST",
        headers: {"Content-Type": "application/x-www-form-urlencoded"},
        body: body,
    });
    return await resp.json();
}
"""


def fetch_month_calendar(page, page_id, year, month):
    """Fetch the calendar JSON for one month, using an already-navigated Playwright page."""
    return page.evaluate(_FETCH_SCRIPT, {"pageId": page_id, "year": year, "month": month})
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_calendar_client.py -v`
Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add colosseum_monitor/calendar_client.py tests/test_calendar_client.py
git commit -m "Add Playwright-driven calendar API client"
```

---

### Task 7: Orchestration entry point

**Files:**
- Create: `colosseum_monitor/run.py`
- Test: `tests/test_run.py`

**Interfaces:**
- Consumes: `config.{TICKET_URL, TICKET_PAGE_ID, TARGET_YEAR, TARGET_MONTH, TARGET_DATES, MONITOR_END_DATE, STATE_PATH, LOG_PATH, CONSECUTIVE_FAILURES_ALERT_THRESHOLD}` (Task 1); `availability.{parse_slots, capacity_by_date, find_newly_available}` (Task 2); `state.{load_state, save_state}` (Task 3); `logger.{format_log_line, format_error_log_line, append_log}` (Task 4); `notifier.{format_availability_message, format_failure_message, send_discord_message}` (Task 5); `calendar_client.fetch_month_calendar` (Task 6)
- Produces: `check_once(fetch_calendar=None, send_message=None, now=None) -> int` (0 on success/no-op, 1 on failure) — this is the function GitHub Actions invokes (Task 8) and the function Task 9's manual verification calls directly.

- [ ] **Step 1: Write the failing tests**

`tests/test_run.py`:
```python
import json
import os
from colosseum_monitor import config
from colosseum_monitor.run import check_once


def _canned_response(capacities_by_date):
    slots = [
        {"startDateTime": f"{date_str}T06:45:00Z", "capacity": capacity}
        for date_str, capacity in capacities_by_date.items()
    ]
    return {"success": True, "data": slots}


def test_check_once_logs_and_does_not_notify_when_still_sold_out(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(config, "LOG_PATH", str(tmp_path / "log.txt"))

    sent = []
    result = check_once(
        fetch_calendar=lambda: _canned_response({d: 0 for d in config.TARGET_DATES}),
        send_message=lambda msg: sent.append(msg),
    )

    assert result == 0
    assert sent == []
    with open(config.STATE_PATH) as f:
        state = json.load(f)
    assert state["capacities"] == {d: 0 for d in config.TARGET_DATES}


def test_check_once_notifies_when_a_date_opens_up(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(config, "LOG_PATH", str(tmp_path / "log.txt"))
    with open(config.STATE_PATH, "w") as f:
        json.dump({"capacities": {d: 0 for d in config.TARGET_DATES}, "consecutive_failures": 0}, f)

    sent = []
    opened = {d: 0 for d in config.TARGET_DATES}
    opened[config.TARGET_DATES[0]] = 4
    result = check_once(
        fetch_calendar=lambda: _canned_response(opened),
        send_message=lambda msg: sent.append(msg),
    )

    assert result == 0
    assert len(sent) == 1
    assert config.TARGET_DATES[0] in sent[0]


def test_check_once_skips_entirely_after_monitor_end_date(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(config, "LOG_PATH", str(tmp_path / "log.txt"))
    monkeypatch.setattr(config, "MONITOR_END_DATE", "2000-01-01")

    calls = []
    result = check_once(fetch_calendar=lambda: calls.append(1), send_message=lambda m: None)

    assert result == 0
    assert calls == []
    assert not os.path.exists(config.STATE_PATH)


def test_check_once_logs_error_and_counts_failures_without_crashing(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(config, "LOG_PATH", str(tmp_path / "log.txt"))

    def boom():
        raise RuntimeError("site unreachable")

    sent = []
    result = check_once(fetch_calendar=boom, send_message=lambda msg: sent.append(msg))

    assert result == 1
    assert sent == []
    with open(config.STATE_PATH) as f:
        state = json.load(f)
    assert state["consecutive_failures"] == 1


def test_check_once_alerts_after_threshold_consecutive_failures(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(config, "LOG_PATH", str(tmp_path / "log.txt"))
    with open(config.STATE_PATH, "w") as f:
        json.dump({"capacities": {}, "consecutive_failures": 2}, f)

    def boom():
        raise RuntimeError("site unreachable")

    sent = []
    result = check_once(fetch_calendar=boom, send_message=lambda msg: sent.append(msg))

    assert result == 1
    assert len(sent) == 1
    assert "3 vezes" in sent[0]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_run.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'colosseum_monitor.run'`

- [ ] **Step 3: Write the implementation**

`colosseum_monitor/run.py`:
```python
"""Entry point: check ticket availability once and notify on new openings."""

import os
import sys
from datetime import date, datetime, timezone

from playwright.sync_api import sync_playwright

from colosseum_monitor import config
from colosseum_monitor.availability import parse_slots, capacity_by_date, find_newly_available
from colosseum_monitor.state import load_state, save_state
from colosseum_monitor.logger import format_log_line, format_error_log_line, append_log
from colosseum_monitor.notifier import (
    format_availability_message,
    format_failure_message,
    send_discord_message,
)
from colosseum_monitor.calendar_client import fetch_month_calendar


def check_once(fetch_calendar=None, send_message=None, now=None):
    """Run one availability check. Dependencies are injectable for testing.

    fetch_calendar: callable() -> dict (the raw calendars_month response)
    send_message: callable(str) -> None
    now: callable() -> datetime (timezone-aware, UTC)
    """
    fetch_calendar = fetch_calendar or _real_fetch_calendar
    send_message = send_message or _real_send_message
    now = now or (lambda: datetime.now(timezone.utc))

    if date.today() > date.fromisoformat(config.MONITOR_END_DATE):
        print(f"Monitoring window ended on {config.MONITOR_END_DATE}, skipping check.")
        return 0

    previous = load_state(config.STATE_PATH)
    timestamp = now().isoformat()

    try:
        response = fetch_calendar()
        slots = parse_slots(response)
        current = capacity_by_date(slots, config.TARGET_DATES)
    except Exception as exc:
        consecutive_failures = previous["consecutive_failures"] + 1
        append_log(config.LOG_PATH, format_error_log_line(timestamp, str(exc)))
        if consecutive_failures >= config.CONSECUTIVE_FAILURES_ALERT_THRESHOLD:
            send_message(format_failure_message(consecutive_failures, str(exc)))
        save_state(
            config.STATE_PATH,
            {"capacities": previous["capacities"], "consecutive_failures": consecutive_failures},
        )
        return 1

    append_log(config.LOG_PATH, format_log_line(timestamp, current))

    newly_available = find_newly_available(previous["capacities"], current)
    if newly_available:
        send_message(format_availability_message(newly_available, current, config.TICKET_URL))

    save_state(config.STATE_PATH, {"capacities": current, "consecutive_failures": 0})
    return 0


def _real_fetch_calendar():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(config.TICKET_URL, wait_until="domcontentloaded")
            return fetch_month_calendar(page, config.TICKET_PAGE_ID, config.TARGET_YEAR, config.TARGET_MONTH)
        finally:
            browser.close()


def _real_send_message(content):
    webhook_url = os.environ["DISCORD_WEBHOOK_URL"]
    send_discord_message(webhook_url, content)


if __name__ == "__main__":
    sys.exit(check_once())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_run.py -v`
Expected: `5 passed`

- [ ] **Step 5: Run the full test suite to confirm nothing regressed**

Run: `python -m pytest tests/ -v`
Expected: `29 passed` (4 config + 8 availability + 4 state + 3 logger + 4 notifier + 1 calendar_client + 5 run)

- [ ] **Step 6: Commit**

```bash
git add colosseum_monitor/run.py tests/test_run.py
git commit -m "Add orchestration entry point wiring modules together"
```

---

### Task 8: GitHub Actions workflow

**Files:**
- Create: `.github/workflows/check.yml`
- Create: `README.md`

**Interfaces:**
- Consumes: `colosseum_monitor.run` module (invoked as `python -m colosseum_monitor.run`), env var `DISCORD_WEBHOOK_URL` (Task 5's `_real_send_message` reads it)
- Produces: nothing consumed by later tasks (Task 9 pushes this workflow live)

- [ ] **Step 1: Write the workflow file**

`.github/workflows/check.yml`:
```yaml
name: Check Colosseum ticket availability

on:
  schedule:
    - cron: "*/15 * * * *"
  workflow_dispatch: {}

permissions:
  contents: write

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          playwright install --with-deps chromium

      - name: Run availability check
        env:
          DISCORD_WEBHOOK_URL: ${{ secrets.DISCORD_WEBHOOK_URL }}
        run: python -m colosseum_monitor.run

      - name: Commit updated state and log
        run: |
          git config user.name "colosseum-ticket-bot"
          git config user.email "actions@users.noreply.github.com"
          git add state.json log.txt
          git diff --quiet --cached || git commit -m "Update availability state [skip ci]"
          git push
```

- [ ] **Step 2: Write the README**

`README.md`:
```markdown
# Colosseum ticket availability monitor

Checks the official Colosseum ticketing site every 15 minutes for openings on
Oct 23/24/25, 2026 for the "Full Experience - Sotterranei e Arena" ticket, and
posts to a Discord channel the moment one opens up. Runs entirely on GitHub
Actions — no computer of yours needs to stay on.

See `docs/superpowers/specs/2026-08-12-colosseum-ticket-monitor-design.md` for
the full design and `docs/superpowers/plans/2026-08-12-colosseum-ticket-monitor-plan.md`
for how it was built.

## One-time setup

1. **Create a Discord webhook** in a server/channel you control:
   Discord → server → channel settings (gear icon) → Integrations → Webhooks → New Webhook → copy the URL.

2. **Push this repo to GitHub** (public, so Actions minutes are free and unlimited):
   ```bash
   gh repo create colosseum-ticket-bot --public --source=. --push
   ```

3. **Add the webhook URL as a repo secret**:
   ```bash
   gh secret set DISCORD_WEBHOOK_URL --body "<paste your webhook URL>"
   ```

4. **The workflow starts running automatically** on its 15-minute schedule once
   pushed (GitHub Actions is on by default for a new repo). You can also
   trigger it manually from the repo's Actions tab ("Run workflow") to test it.

## Local development

```bash
python -m venv .venv
source .venv/Scripts/activate     # Git Bash; use .venv\Scripts\activate.bat for cmd.exe
pip install -r requirements-dev.txt
playwright install chromium
python -m pytest tests/ -v
```

## Running a check manually

```bash
DISCORD_WEBHOOK_URL="<webhook url>" python -m colosseum_monitor.run
```
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/check.yml README.md
git commit -m "Add GitHub Actions workflow and README"
```

---

### Task 9: Manual verification, baseline data, and going live

This task has no new source code — it runs the finished bot for real, establishes the committed baseline `state.json`/`log.txt` the workflow needs to always find on disk, and pushes everything to GitHub. Do these steps interactively (not from a fresh subagent with no terminal access to the live site).

**Files:**
- Create: `state.json` (baseline, generated by running the code — do not hand-write it)
- Create: `log.txt` (baseline, generated by running the code — do not hand-write it)

- [ ] **Step 1: Install Playwright's browser binary locally (one-time)**

Run: `playwright install chromium`
Expected: downloads Chromium; exits 0.

- [ ] **Step 2: Sanity-check parsing against a month already known to be sold out**

This confirms the parser doesn't produce false positives before trusting it. Run from the project root:

```bash
python -c "
from playwright.sync_api import sync_playwright
from colosseum_monitor import config
from colosseum_monitor.calendar_client import fetch_month_calendar
from colosseum_monitor.availability import parse_slots, capacity_by_date

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto(config.TICKET_URL, wait_until='domcontentloaded')
    response = fetch_month_calendar(page, config.TICKET_PAGE_ID, 2026, 9)  # September: known sold out
    browser.close()

slots = parse_slots(response)
print(capacity_by_date(slots, ['2026-09-23', '2026-09-24', '2026-09-25']))
"
```

Expected: prints a dict with all three dates mapped to `0` (e.g. `{'2026-09-23': 0, '2026-09-24': 0, '2026-09-25': 0}`). If any value is non-zero, stop and re-check the parsing logic before proceeding — the code is misreading the API.

- [ ] **Step 3: Generate the real October baseline**

```bash
python -m colosseum_monitor.run
```

Expected: exits 0, creates `state.json` and `log.txt` in the project root. Open `state.json` and confirm it has the shape `{"capacities": {"2026-10-23": <int>, "2026-10-24": <int>, "2026-10-25": <int>}, "consecutive_failures": 0}`. (No `DISCORD_WEBHOOK_URL` env var is needed for this run if all three capacities come back `0`, since no message is sent in that case — matching the "still sold out" report from the user. If a capacity is already non-zero, set `DISCORD_WEBHOOK_URL` first so the run can notify instead of crashing on the missing env var.)

- [ ] **Step 4: Verify Discord delivery end-to-end with a real webhook**

```bash
python -c "
import os
from colosseum_monitor.notifier import send_discord_message
send_discord_message(os.environ['DISCORD_WEBHOOK_URL'], '🔧 Teste do monitor do Coliseu — se você está vendo isso, a notificação funciona.')
"
```
(Set `DISCORD_WEBHOOK_URL` in the shell first: `export DISCORD_WEBHOOK_URL="<webhook url>"`)

Expected: the test message appears in the Discord channel within a few seconds.

- [ ] **Step 5: Commit the baseline state/log**

```bash
git add state.json log.txt
git commit -m "Add baseline availability state from initial real check"
```

- [ ] **Step 6: Create the GitHub repo and push**

```bash
gh repo create colosseum-ticket-bot --public --source=. --push
```
Expected: repo created on GitHub, all commits pushed, prints the repo URL.

- [ ] **Step 7: Add the Discord webhook as a repo secret**

```bash
gh secret set DISCORD_WEBHOOK_URL --body "<paste your webhook URL>"
```
Expected: `✓ Set Actions secret DISCORD_WEBHOOK_URL for <owner>/colosseum-ticket-bot`

- [ ] **Step 8: Trigger the workflow manually and confirm it commits back to the repo**

```bash
gh workflow run check.yml
```
Wait ~30-60 seconds, then:
```bash
gh run list --workflow=check.yml --limit 1
```
Expected: the run shows status `completed` / conclusion `success`. Then:
```bash
git pull
git log --oneline -3
```
Expected: a new commit from `colosseum-ticket-bot` (the Actions bot identity) updating `log.txt` appears — this confirms the schedule/commit-back loop works end-to-end. From here it runs unattended every 15 minutes until 2026-10-25.
