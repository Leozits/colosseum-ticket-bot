"""Entry point: check the Louvre ticket calendar once and notify on new openings."""

import os
import sys

from patchright.sync_api import sync_playwright

from louvre_monitor import config
from louvre_monitor.messages import format_availability_message, format_failure_message
from louvre_monitor.calendar_client import navigate_to_month, read_month_days
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
    # headless=False: non-headless is the proven-safe choice already
    # validated for the Colosseum monitor's own Cloudflare/WAF interaction;
    # not yet confirmed whether Louvre's Cloudflare challenge specifically
    # requires it, but there is no reason to risk finding out the hard way.
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--window-position=-32000,-32000", "--window-size=1280,800"],
        )
        try:
            page = browser.new_page()
            page.goto(config.TICKET_URL, wait_until="domcontentloaded")
            # The Cloudflare "Just a moment..." interstitial resolves on its
            # own once its JS challenge passes; wait for the real calendar
            # rather than guessing a fixed delay.
            page.wait_for_selector(".d-month", timeout=30000)
            # The month/year header can render before the day checkboxes
            # (a separate async load) -- confirmed by testing: reading days
            # right after the header appeared intermittently returned zero
            # checkboxes. Wait for at least one real day before touching
            # navigation or reading data.
            page.wait_for_selector("#calendarContainer input[data-date]", timeout=15000)
            decline_cookies_button = page.query_selector(".orejime-Notice-declineButton")
            if decline_cookies_button:
                decline_cookies_button.click(force=True)
            navigate_to_month(page, config.CALENDAR_YEAR, config.CALENDAR_MONTH)
            page.wait_for_selector("#calendarContainer input[data-date]", timeout=15000)
            all_days = read_month_days(page)
            statuses = {date: status for date, status in all_days.items() if date in config.TARGET_DATES}
            return {"statuses": statuses, "slots": {}}
        finally:
            browser.close()


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
            subject="Monitor Louvre",
            body=content,
        )
    except Exception as exc:
        errors.append(f"Email: {exc}")

    if errors:
        raise RuntimeError("; ".join(errors))


if __name__ == "__main__":
    sys.exit(check_once())
