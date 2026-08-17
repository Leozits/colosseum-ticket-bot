from versailles_monitor.messages import format_availability_message


def test_format_availability_message_lists_each_date():
    message = format_availability_message(["2026-10-14", "2026-10-18"], "https://example.com")
    assert "- 2026-10-14" in message
    assert "- 2026-10-18" in message
    assert "https://example.com" in message
