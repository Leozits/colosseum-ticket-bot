"""Entry point: check the Versailles ticket calendar once and notify on new openings."""

import os
import sys

from versailles_monitor import config
from versailles_monitor.messages import format_availability_message, format_failure_message
from versailles_monitor.calendar_client import fetch_month_html, parse_month_days
from monitor_common.engine import check_once as _engine_check_once
from monitor_common.notifier import send_whatsapp_message, send_email_message


def check_once(fetch_days=None, send_message=None, now=None):
    return _engine_check_once(
        config,
        format_availability_message=lambda dates, slots: format_availability_message(dates, config.TICKET_URL),
        format_failure_message=format_failure_message,
        fetch_days=fetch_days or _real_fetch_days,
        send_message=send_message or _real_send_message,
        now=now,
    )


def _real_fetch_days():
    html = fetch_month_html(config.CALENDAR_YEAR, config.CALENDAR_MONTH)
    all_days = parse_month_days(html)
    statuses = {date: status for date, status in all_days.items() if date in config.TARGET_DATES}
    return {"statuses": statuses, "slots": {}}


def _real_send_message(content):
    errors = []

    try:
        send_whatsapp_message(
            phone=os.environ["WHATSAPP_PHONE"],
            api_key=os.environ["CALLMEBOT_API_KEY"],
            text=content,
        )
    except Exception as exc:
        errors.append(f"WhatsApp: {exc}")

    try:
        send_email_message(
            smtp_host=config.SMTP_HOST,
            smtp_port=config.SMTP_PORT,
            username=os.environ["GMAIL_ADDRESS"],
            password=os.environ["GMAIL_APP_PASSWORD"],
            to_address=os.environ.get("NOTIFY_TO_EMAIL") or os.environ["GMAIL_ADDRESS"],
            subject="Monitor Versalhes",
            body=content,
        )
    except Exception as exc:
        errors.append(f"Email: {exc}")

    if errors:
        raise RuntimeError("; ".join(errors))


if __name__ == "__main__":
    sys.exit(check_once())
