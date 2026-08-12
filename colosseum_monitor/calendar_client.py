"""Fetches calendar availability data from the ticketing site's internal AJAX endpoint.

The endpoint (/mtajax/calendars_month) sits behind an Octofence WAF that blocks
plain HTTP requests without a real browser session -- it must be called from
inside a Playwright page that has already loaded the ticket page, via
page.evaluate, so the request carries the page's real cookies/session.
"""


def build_ajax_payload(page_id, year, month):
    return {"action": "midaabc_calendars_month", "page": page_id, "year": year, "month": month}


_FETCH_SCRIPT = """
async ({pageId, year, month}) => {
    const body = new URLSearchParams({
        action: "midaabc_calendars_month",
        page: pageId,
        year: year,
        month: month,
    });
    const resp = await fetch("/mtajax/calendars_month", {
        method: "POST",
        headers: {"Content-Type": "application/x-www-form-urlencoded"},
        body: body,
    });
    return await resp.json();
}
"""


def fetch_month_calendar(page, page_id, year, month):
    """Fetch the calendar JSON for one month, using an already-navigated Playwright page."""
    return page.evaluate(_FETCH_SCRIPT, {"pageId": page_id, "year": year, "month": month})
