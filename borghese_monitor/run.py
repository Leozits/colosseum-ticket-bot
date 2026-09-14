"""Entry point: check the Galleria Borghese ticket calendar once and notify on new openings."""

import os
import sys

from patchright.sync_api import sync_playwright

from borghese_monitor import config
from borghese_monitor.messages import format_availability_message
from borghese_monitor.calendar_client import navigate_to_month, read_month_days
from monitor_common.engine import check_once as _engine_check_once
from monitor_common.notifier import send_email_message


def check_once(fetch_days=None, send_message=None, now=None):
    return _engine_check_once(
        config,
        format_availability_message=lambda dates, slots: format_availability_message(dates, config.TICKET_URL),
        fetch_days=fetch_days or _real_fetch_days,
        send_message=send_message or _real_send_message,
        now=now,
    )


def _real_fetch_days():
    # headless=False: non-headless is the proven-safe choice for every WAF
    # in this repo so far; Akamai's own bot management is tougher than the
    # others, so there is even less reason to risk headless here.
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--window-position=-32000,-32000", "--window-size=1280,800"],
        )
        try:
            page = browser.new_page()
            page.goto(config.TICKET_URL, wait_until="domcontentloaded")
            page.wait_for_selector(".btn-today.text-center", timeout=30000)
            navigate_to_month(page, config.CALENDAR_YEAR, config.CALENDAR_MONTH)
            result = read_month_days(page)
            statuses = {date: status for date, status in result["statuses"].items() if date in config.TARGET_DATES}
            slots = {date: s for date, s in result["slots"].items() if date in config.TARGET_DATES}
            return {"statuses": statuses, "slots": slots}
        finally:
            browser.close()


def _real_send_message(content):
    # Email only -- WhatsApp via CallMeBot has no free-tier quota left (see
    # the other monitors' history); attempting it here would just add
    # guaranteed-failing noise to the log for no benefit.
    send_email_message(
        smtp_host=config.SMTP_HOST,
        smtp_port=config.SMTP_PORT,
        username=os.environ["GMAIL_ADDRESS"],
        password=os.environ["GMAIL_APP_PASSWORD"],
        to_address=os.environ.get("NOTIFY_TO_EMAIL") or os.environ["GMAIL_ADDRESS"],
        subject="Monitor Galleria Borghese",
        body=content,
    )


if __name__ == "__main__":
    sys.exit(check_once())
