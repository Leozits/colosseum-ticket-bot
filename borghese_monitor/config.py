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
