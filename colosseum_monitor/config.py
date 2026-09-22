"""Configuration constants for the Colosseum ticket availability monitor."""

TICKET_URL = "https://ticketing.colosseo.it/eventi/full-experience-sotterranei-e-arena/"

CALENDAR_YEAR = 2026
CALENDAR_MONTH = 10

TARGET_DATES = ["2026-10-22", "2026-10-23", "2026-10-24", "2026-10-25", "2026-10-27"]

MONITOR_END_DATE = "2026-10-27"

STATE_PATH = "state.json"
LOG_PATH = "log.txt"

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
