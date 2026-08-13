from datetime import datetime, timezone
from colosseum_monitor.schedule_window import next_resume_time


def test_next_resume_time_same_day_when_before_22h_brt():
    now_utc = datetime(2026, 8, 13, 14, 0, 0, tzinfo=timezone.utc)  # 11:00 BRT
    assert next_resume_time(now_utc) == datetime(2026, 8, 14, 1, 0, 0, tzinfo=timezone.utc)


def test_next_resume_time_next_day_when_already_past_22h_brt():
    now_utc = datetime(2026, 8, 14, 2, 0, 0, tzinfo=timezone.utc)  # 23:00 BRT
    assert next_resume_time(now_utc) == datetime(2026, 8, 15, 1, 0, 0, tzinfo=timezone.utc)


def test_next_resume_time_bumps_to_next_day_exactly_at_resume_hour():
    now_utc = datetime(2026, 8, 14, 1, 0, 0, tzinfo=timezone.utc)  # exactly 22:00 BRT
    assert next_resume_time(now_utc) == datetime(2026, 8, 15, 1, 0, 0, tzinfo=timezone.utc)


def test_next_resume_time_returns_utc_timezone():
    now_utc = datetime(2026, 8, 13, 14, 0, 0, tzinfo=timezone.utc)
    assert next_resume_time(now_utc).tzinfo == timezone.utc
