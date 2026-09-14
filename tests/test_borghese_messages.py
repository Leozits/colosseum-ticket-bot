from borghese_monitor.messages import format_availability_message


def test_format_availability_message_lists_each_date():
    message = format_availability_message(["2026-10-22", "2026-10-27"], "https://example.com")
    assert "- 2026-10-22" in message
    assert "- 2026-10-27" in message
    assert "https://example.com" in message
