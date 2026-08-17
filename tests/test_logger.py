from colosseum_monitor.logger import (
    format_log_line,
    format_change_log_line,
    format_error_log_line,
    format_slots_log_line,
    append_log,
)


def test_format_log_line_includes_timestamp_and_sorted_dates():
    line = format_log_line("2026-08-12T10:00:00+00:00", {"2026-09-13": "closing", "2026-09-12": "soldout"})
    assert line == "2026-08-12T10:00:00+00:00 OK 2026-09-12=soldout 2026-09-13=closing"


def test_format_change_log_line_lists_each_transition():
    changes = [
        {"date": "2026-09-12", "from": "closing", "to": "soldout"},
        {"date": "2026-09-13", "from": "closing", "to": "available"},
    ]
    line = format_change_log_line("2026-08-12T10:00:00+00:00", changes)
    assert line == "2026-08-12T10:00:00+00:00 CHANGE 2026-09-12:closing->soldout 2026-09-13:closing->available"


def test_format_error_log_line_includes_message():
    line = format_error_log_line("2026-08-12T10:00:00+00:00", "boom")
    assert line == "2026-08-12T10:00:00+00:00 ERROR boom"


def test_format_slots_log_line_lists_available_times_per_date():
    slots_by_date = {
        "2026-09-16": {"13:15": "available", "13:30": "available", "14:00": "closed"},
        "2026-09-17": {"09:00": "closed"},
    }
    line = format_slots_log_line("2026-08-13T10:00:00+00:00", slots_by_date)
    assert line == "2026-08-13T10:00:00+00:00 SLOTS 2026-09-16:[13:15,13:30] 2026-09-17:[]"


def test_append_log_appends_without_truncating(tmp_path):
    path = str(tmp_path / "log.txt")
    append_log(path, "line one")
    append_log(path, "line two")
    with open(path) as f:
        assert f.read() == "line one\nline two\n"
