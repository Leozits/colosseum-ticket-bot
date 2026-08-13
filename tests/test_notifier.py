import pytest
from unittest.mock import patch, Mock
from colosseum_monitor.notifier import (
    format_availability_message,
    format_failure_message,
    send_whatsapp_message,
)


def test_format_availability_message_lists_each_opened_date():
    message = format_availability_message(["2026-10-24"], "https://example.com/ticket")
    assert "2026-10-24" in message
    assert "https://example.com/ticket" in message


def test_format_failure_message_includes_count_and_error():
    message = format_failure_message(3, "timeout")
    assert "3 vezes" in message
    assert "timeout" in message


@patch("colosseum_monitor.notifier.requests.get")
def test_send_whatsapp_message_posts_expected_params(mock_get):
    mock_get.return_value = Mock(status_code=200, text="Message queued. You will receive it in a few seconds.")

    send_whatsapp_message("5511985600509", "8502714", "hello")

    mock_get.assert_called_once_with(
        "https://api.callmebot.com/whatsapp.php",
        params={"phone": "5511985600509", "text": "hello", "apikey": "8502714"},
        timeout=15,
    )


@patch("colosseum_monitor.notifier.requests.get")
def test_send_whatsapp_message_raises_on_http_error(mock_get):
    mock_response = Mock()
    mock_response.raise_for_status.side_effect = Exception("500 error")
    mock_get.return_value = mock_response

    with pytest.raises(Exception):
        send_whatsapp_message("5511985600509", "8502714", "hello")


@patch("colosseum_monitor.notifier.requests.get")
def test_send_whatsapp_message_raises_when_not_confirmed(mock_get):
    mock_get.return_value = Mock(status_code=200, raise_for_status=Mock(), text="Invalid apikey.")

    with pytest.raises(RuntimeError):
        send_whatsapp_message("5511985600509", "8502714", "hello")
