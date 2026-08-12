from colosseum_monitor import config


def test_target_dates_fall_within_target_year_and_month():
    prefix = f"{config.TARGET_YEAR}-{config.TARGET_MONTH:02d}"
    for date_str in config.TARGET_DATES:
        assert date_str.startswith(prefix)


def test_target_dates_are_the_three_expected_days():
    assert config.TARGET_DATES == ["2026-10-23", "2026-10-24", "2026-10-25"]


def test_monitor_end_date_covers_all_target_dates():
    assert config.MONITOR_END_DATE >= max(config.TARGET_DATES)


def test_ticket_page_id_matches_confirmed_value():
    assert config.TICKET_PAGE_ID == 225
