"""Computes when a daytime pause (triggered once nothing's available) should lift."""

from datetime import timedelta, timezone
from zoneinfo import ZoneInfo

from colosseum_monitor import config


def next_resume_time(now_utc):
    """Return the next occurrence of config.PAUSE_RESUME_HOUR_LOCAL in
    config.PAUSE_TIMEZONE, as a UTC datetime strictly after now_utc.
    """
    local_tz = ZoneInfo(config.PAUSE_TIMEZONE)
    local_now = now_utc.astimezone(local_tz)
    resume_local = local_now.replace(
        hour=config.PAUSE_RESUME_HOUR_LOCAL, minute=0, second=0, microsecond=0
    )
    if resume_local <= local_now:
        resume_local += timedelta(days=1)
    return resume_local.astimezone(timezone.utc)
