"""Configuration constants for the Colosseum ticket availability monitor."""

TICKET_URL = "https://ticketing.colosseo.it/eventi/full-experience-sotterranei-e-arena/"

TARGET_DATES = ["2026-10-23", "2026-10-24", "2026-10-25"]

MONITOR_END_DATE = "2026-10-25"

STATE_PATH = "state.json"
LOG_PATH = "log.txt"

CONSECUTIVE_FAILURES_ALERT_THRESHOLD = 3

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

# Once a check finds nothing available, checks pause until this local hour/timezone,
# then resume every 15 min again until the next "nothing available" result.
PAUSE_RESUME_HOUR_LOCAL = 22
PAUSE_TIMEZONE = "America/Sao_Paulo"
