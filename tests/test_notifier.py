import pytest
from unittest.mock import patch, Mock
from colosseum_monitor.notifier import (
    format_availability_message,
    format_failure_message,
    send_discord_message,
)


def test_format_availability_message_lists_each_opened_date_with_capacity():
    message = format_availability_message(
        ["2026-10-24"], {"2026-10-23": 0, "2026-10-24": 5}, "https://example.com/ticket"
    )
    assert "2026-10-24: 5 vagas" in message
    assert "https://example.com/ticket" in message
    assert "2026-10-23" not in message


def test_format_failure_message_includes_count_and_error():
    message = format_failure_message(3, "timeout")
    assert "3 vezes" in message
    assert "timeout" in message


@patch("colosseum_monitor.notifier.requests.post")
def test_send_discord_message_posts_content_as_json(mock_post):
    mock_post.return_value = Mock(status_code=204, raise_for_status=Mock())
    send_discord_message("https://discord.example/webhook", "hello")
    mock_post.assert_called_once_with(
        "https://discord.example/webhook", json={"content": "hello"}, timeout=10
    )


@patch("colosseum_monitor.notifier.requests.post")
def test_send_discord_message_raises_on_http_error(mock_post):
    mock_response = Mock()
    mock_response.raise_for_status.side_effect = Exception("500 error")
    mock_post.return_value = mock_response
    with pytest.raises(Exception):
        send_discord_message("https://discord.example/webhook", "hello")
