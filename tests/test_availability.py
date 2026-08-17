import pytest
from colosseum_monitor.availability import (
    parse_calendar_title,
    classify_day_status,
    classify_slot_status,
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


def test_classify_slot_status_closed_when_disabled():
    assert classify_slot_status(True) == "closed"


def test_classify_slot_status_available_when_not_disabled():
    assert classify_slot_status(False) == "available"
