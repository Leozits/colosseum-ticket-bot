from colosseum_monitor import config


def test_target_dates_are_the_three_expected_days():
    assert config.TARGET_DATES == ["2026-10-23", "2026-10-24", "2026-10-25"]


def test_monitor_end_date_covers_all_target_dates():
    assert config.MONITOR_END_DATE >= max(config.TARGET_DATES)
