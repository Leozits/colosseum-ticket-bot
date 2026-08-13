import pytest
from unittest.mock import patch, Mock, MagicMock
from colosseum_monitor.notifier import (
    format_availability_message,
    format_failure_message,
    send_whatsapp_message,
    send_email_message,
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


@patch("colosseum_monitor.notifier.smtplib.SMTP")
def test_send_email_message_logs_in_and_sends(mock_smtp_class):
    mock_server = MagicMock()
    mock_smtp_class.return_value.__enter__.return_value = mock_server

    send_email_message(
        smtp_host="smtp.gmail.com",
        smtp_port=587,
        username="me@gmail.com",
        password="app-password",
        to_address="me@gmail.com",
        subject="Subject",
        body="Body text",
    )

    mock_smtp_class.assert_called_once_with("smtp.gmail.com", 587, timeout=15)
    mock_server.starttls.assert_called_once()
    mock_server.login.assert_called_once_with("me@gmail.com", "app-password")
    mock_server.send_message.assert_called_once()
    sent_message = mock_server.send_message.call_args[0][0]
    assert sent_message["Subject"] == "Subject"
    assert sent_message["From"] == "me@gmail.com"
    assert sent_message["To"] == "me@gmail.com"
    assert sent_message.get_content().strip() == "Body text"


@patch("colosseum_monitor.notifier.smtplib.SMTP")
def test_send_email_message_raises_on_login_failure(mock_smtp_class):
    mock_server = MagicMock()
    mock_server.login.side_effect = Exception("auth failed")
    mock_smtp_class.return_value.__enter__.return_value = mock_server

    with pytest.raises(Exception):
        send_email_message(
            smtp_host="smtp.gmail.com",
            smtp_port=587,
            username="me@gmail.com",
            password="wrong",
            to_address="me@gmail.com",
            subject="Subject",
            body="Body",
        )
