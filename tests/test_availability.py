import pytest
from colosseum_monitor.availability import parse_slots, capacity_by_date, find_newly_available


def test_parse_slots_returns_data_list_on_success():
    response = {"success": True, "data": [{"startDateTime": "2026-10-23T06:45:00Z", "capacity": 5}]}
    assert parse_slots(response) == response["data"]


def test_parse_slots_raises_on_missing_success_flag():
    with pytest.raises(ValueError):
        parse_slots({"data": []})


def test_parse_slots_raises_on_non_dict_response():
    with pytest.raises(ValueError):
        parse_slots(["not", "a", "dict"])


def test_capacity_by_date_sums_multiple_slots_same_day():
    slots = [
        {"startDateTime": "2026-10-23T06:45:00Z", "capacity": 5},
        {"startDateTime": "2026-10-23T07:00:00Z", "capacity": 3},
        {"startDateTime": "2026-10-24T06:45:00Z", "capacity": 0},
    ]
    result = capacity_by_date(slots, ["2026-10-23", "2026-10-24", "2026-10-25"])
    assert result == {"2026-10-23": 8, "2026-10-24": 0, "2026-10-25": 0}


def test_capacity_by_date_ignores_slots_outside_target_dates():
    slots = [{"startDateTime": "2026-09-01T06:45:00Z", "capacity": 100}]
    result = capacity_by_date(slots, ["2026-10-23"])
    assert result == {"2026-10-23": 0}


def test_find_newly_available_detects_transition_from_zero():
    previous = {"2026-10-23": 0, "2026-10-24": 0}
    current = {"2026-10-23": 0, "2026-10-24": 5}
    assert find_newly_available(previous, current) == ["2026-10-24"]


def test_find_newly_available_ignores_dates_still_at_zero():
    previous = {"2026-10-23": 0}
    current = {"2026-10-23": 0}
    assert find_newly_available(previous, current) == []


def test_find_newly_available_treats_unknown_previous_date_as_zero():
    previous = {}
    current = {"2026-10-23": 2}
    assert find_newly_available(previous, current) == ["2026-10-23"]
