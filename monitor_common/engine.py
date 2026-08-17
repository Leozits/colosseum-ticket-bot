"""Generic run-once engine shared by every ticket monitor: load state, fetch,
diff, log, notify, save state.

Failures are logged and counted (consecutive_failures in state.json) but
never trigger a notification -- the user only wants to hear about actual
ticket availability, not the monitor's own health. A run that fails
repeatedly for hours just accumulates silent ERROR log lines instead.
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


def check_once(config, format_availability_message, fetch_days, send_message, now=None):
    """Run one availability check for a single site. Dependencies are injectable for testing.

    config: object/module with STATE_PATH, LOG_PATH, MONITOR_END_DATE attributes.
    format_availability_message: callable(newly_available_dates, slots_by_date) -> str
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
