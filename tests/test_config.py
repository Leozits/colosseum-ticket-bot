from colosseum_monitor import config


def test_target_dates_cover_the_trip_window_excluding_the_vatican_day():
    assert config.TARGET_DATES == ["2026-10-22", "2026-10-23", "2026-10-24", "2026-10-25", "2026-10-27"]
    assert "2026-10-26" not in config.TARGET_DATES  # already booked for the Vatican


def test_monitor_end_date_covers_all_target_dates():
    assert config.MONITOR_END_DATE >= max(config.TARGET_DATES)
