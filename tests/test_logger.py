from colosseum_monitor.logger import format_log_line, format_error_log_line, append_log


def test_format_log_line_includes_timestamp_and_sorted_dates():
    line = format_log_line("2026-08-12T10:00:00+00:00", {"2026-10-24": 0, "2026-10-23": 5})
    assert line == "2026-08-12T10:00:00+00:00 OK 2026-10-23=5 2026-10-24=0"


def test_format_error_log_line_includes_message():
    line = format_error_log_line("2026-08-12T10:00:00+00:00", "boom")
    assert line == "2026-08-12T10:00:00+00:00 ERROR boom"


def test_append_log_appends_without_truncating(tmp_path):
    path = str(tmp_path / "log.txt")
    append_log(path, "line one")
    append_log(path, "line two")
    with open(path) as f:
        assert f.read() == "line one\nline two\n"
