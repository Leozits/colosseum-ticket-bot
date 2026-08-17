"""Entry point: check ticket calendar day statuses once and notify on new openings."""

import os
import sys

from patchright.sync_api import sync_playwright

from colosseum_monitor import config
from colosseum_monitor.notifier import format_availability_message, format_failure_message
from colosseum_monitor.calendar_client import (
    advance_to_max_month,
    read_visible_month_days,
    click_day,
    read_time_slots,
)
from monitor_common.engine import check_once as _engine_check_once
from monitor_common.notifier import send_whatsapp_message, send_email_message


def check_once(fetch_days=None, send_message=None, now=None):
    return _engine_check_once(
        config,
        format_availability_message=lambda dates, slots: format_availability_message(dates, slots, config.TICKET_URL),
        format_failure_message=format_failure_message,
        fetch_days=fetch_days or _real_fetch_days,
        send_message=send_message or _real_send_message,
        now=now,
    )


def _real_fetch_days():
    # headless=False: the WAF blocks headless Chromium outright, confirmed by testing.
    # window-position off-screen: keeps the required real browser window from
    # popping up in front of the user every 15 minutes.
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--window-position=-32000,-32000", "--window-size=1280,800"],
        )
        try:
            page = browser.new_page()
            page.goto(config.TICKET_URL, wait_until="domcontentloaded")
            # Site shows a "Waiting" holding page before settling into the real
            # one; wait for the actual calendar rather than guessing a fixed
            # delay, which was intermittently too short and logged spurious
            # "Calendar title not found" failures.
            page.wait_for_selector(".ui-datepicker-title", timeout=30000)
            # Fresh (non-persistent) browser session -> the cookie consent banner
            # is present every run and otherwise intercepts clicks on the
            # calendar's "next month" arrow.
            accept_cookies_button = page.query_selector("#cookie_action_close_header")
            if accept_cookies_button:
                accept_cookies_button.click(force=True)
            advance_to_max_month(page)
            statuses = read_visible_month_days(page)

            # Only "available" days are clickable at all (soldout/closing days
            # render as <span>, not <a>) -- so this only ever runs for the
            # handful of dates actually worth knowing the exact times for.
            slots = {}
            for date_str, status in statuses.items():
                if status != "available":
                    continue
                day_number = int(date_str[-2:])
                if click_day(page, day_number):
                    page.wait_for_selector(".abc-slotpicker", timeout=15000)
                    slots[date_str] = read_time_slots(page)

            return {"statuses": statuses, "slots": slots}
        finally:
            browser.close()


def _real_send_message(content):
    # Both channels, independently -- CallMeBot's free tier sometimes confirms
    # "Message queued" for messages that never actually arrive, so email stays
    # as a backup rather than a straight replacement. Any failure (partial or
    # total) is reported so it still shows up in the log.
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
            subject="Monitor Coliseu",
            body=content,
        )
    except Exception as exc:
        errors.append(f"Email: {exc}")

    if errors:
        raise RuntimeError("; ".join(errors))


if __name__ == "__main__":
    sys.exit(check_once())
