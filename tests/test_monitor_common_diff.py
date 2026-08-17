from monitor_common.diff import find_status_changes, find_newly_available


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
