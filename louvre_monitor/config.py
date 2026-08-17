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
