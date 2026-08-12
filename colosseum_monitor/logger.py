"""Append-only log of each monitor run, for auditability."""


def format_log_line(timestamp, capacities):
    parts = " ".join(f"{date}={capacity}" for date, capacity in sorted(capacities.items()))
    return f"{timestamp} OK {parts}"


def format_error_log_line(timestamp, error_message):
    return f"{timestamp} ERROR {error_message}"


def append_log(path, line):
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
