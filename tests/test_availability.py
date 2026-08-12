import pytest
from colosseum_monitor.availability import (
    parse_calendar_title,
    classify_day_status,
    find_status_changes,
    find_newly_available,
)


def test_parse_calendar_title_settembre():
    assert parse_calendar_title("Settembre 2026") == (2026, 9)


def test_parse_calendar_title_with_nbsp():
    assert parse_calendar_title("Ottobre 2026") == (2026, 10)


def test_parse_calendar_title_raises_on_unknown_month():
    with pytest.raises(ValueError):
        parse_calendar_title("Blorpuary 2026")


def test_parse_calendar_title_raises_on_missing_year():
    with pytest.raises(ValueError):
        parse_calendar_title("Settembre")


def test_classify_day_status_soldout():
    assert classify_day_status(" ui-datepicker-unselectable ui-state-disabled soldout_day", False) == "soldout"


def test_classify_day_status_closing():
    assert classify_day_status(" ui-datepicker-unselectable ui-state-disabled closing_day", False) == "closing"


def test_classify_day_status_available_when_linked_and_no_special_class():
    assert classify_day_status("", True) == "available"


def test_classify_day_status_unknown_when_unlinked_and_no_special_class():
    assert classify_day_status("ui-datepicker-today", False) == "unknown"


def test_find_status_changes_detects_transition():
    previous = {"2026-09-12": "closing"}
    current = {"2026-09-12": "soldout"}
    assert find_status_changes(previous, current) == [{"date": "2026-09-12", "from": "closing", "to": "soldout"}]


def test_find_status_changes_ignores_unchanged_dates():
    previous = {"2026-09-12": "soldout"}
    current = {"2026-09-12": "soldout"}
    assert find_status_changes(previous, current) == []


def test_find_status_changes_treats_new_date_as_change_from_none():
    previous = {}
    current = {"2026-09-13": "closing"}
    assert find_status_changes(previous, current) == [{"date": "2026-09-13", "from": None, "to": "closing"}]


def test_find_newly_available_detects_transition_to_available():
    previous = {"2026-10-23": "closing"}
    current = {"2026-10-23": "available"}
    assert find_newly_available(previous, current) == ["2026-10-23"]


def test_find_newly_available_ignores_non_available_transitions():
    previous = {"2026-09-12": "closing"}
    current = {"2026-09-12": "soldout"}
    assert find_newly_available(previous, current) == []


def test_find_newly_available_ignores_already_available_dates():
    previous = {"2026-10-23": "available"}
    current = {"2026-10-23": "available"}
    assert find_newly_available(previous, current) == []
