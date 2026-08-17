from colosseum_monitor.notifier import format_availability_message


def test_format_availability_message_lists_each_opened_date_with_times():
    message = format_availability_message(
        ["2026-10-24"],
        {"2026-10-24": {"13:15": "available", "14:00": "closed"}},
        "https://example.com/ticket",
    )
    assert "2026-10-24: 13:15" in message
    assert "14:00" not in message
    assert "https://example.com/ticket" in message


def test_format_availability_message_omits_times_when_none_known():
    message = format_availability_message(["2026-10-24"], {}, "https://example.com/ticket")
    assert "- 2026-10-24" in message
    assert ":" not in message.split("\n")[1]
