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
