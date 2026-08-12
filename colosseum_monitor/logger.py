"""Append-only log of each monitor run, for auditability."""


def format_log_line(timestamp, day_statuses):
    parts = " ".join(f"{date}={status}" for date, status in sorted(day_statuses.items()))
    return f"{timestamp} OK {parts}"


def format_change_log_line(timestamp, changes):
    parts = " ".join(f"{c['date']}:{c['from']}->{c['to']}" for c in changes)
    return f"{timestamp} CHANGE {parts}"


def format_error_log_line(timestamp, error_message):
    return f"{timestamp} ERROR {error_message}"


def append_log(path, line):
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
