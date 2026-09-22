"""Reads Galleria Borghese ticket-calendar day statuses via genuine browser interaction.

tosc.it (TicketOne) is protected by Akamai Bot Manager -- confirmed by
direct testing: a bare HTTP request gets no response at all (the TCP
connection is reset immediately), and the resolved IP is in Akamai's
address space. This is behavioral/fingerprinting protection, not a
one-time JS challenge, so there's no guaranteed workaround -- only
looking as close to a real, infrequent visit as possible (see the design
doc for the resulting much lower poll cadence used by the Scheduled Task).

Each day is a <div class="cal-month-day"> containing a
<span class="day-number" data-cal-date="YYYY-MM-DD"> whose class carries
"cal-event-status-available" or "cal-event-status-unavailable" -- days with
no event on sale yet have no data-cal-date attribute at all. An available
day's same .cal-month-day additionally contains one
<span class="event-time-pill" data-availability-indicator="N">HH:MM</span>
per bookable time slot; indicator "0" is a placeholder for "nothing open"
(its time text is a dummy "00:00", not real) and is skipped -- any other
indicator value means that specific time is bookable at some level (the
site's own alta/moderata/ridotta 3-tier signal, collapsed here to a plain
"available", per the design doc).
"""

_MONTH_NAMES = [
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
]


def read_current_month(page):
    """Return (year, month) currently displayed in the calendar header."""
    header = page.query_selector(".btn-today.text-center").inner_text().strip()
    month_name, year = header.rsplit(" ", 1)
    return int(year), _MONTH_NAMES.index(month_name.strip().lower()) + 1


def _read_current_month_tolerantly(page):
    """Retry read_current_month briefly -- confirmed by live testing: the
    header text can transiently come back malformed (e.g. missing a space
    between month name and year) right after a fresh page load, not just
    mid-navigation, causing an unpack error in read_current_month.
    """
    for _ in range(20):
        try:
            return read_current_month(page)
        except (AttributeError, ValueError):
            page.wait_for_timeout(250)
    return read_current_month(page)  # let the real exception surface


def navigate_to_month(page, target_year, target_month):
    """Click the calendar's prev/next arrow until the target month is displayed."""
    current_year, current_month = _read_current_month_tolerantly(page)
    delta = (target_year * 12 + target_month) - (current_year * 12 + current_month)
    selector = (
        'button[aria-label="Vai al mese prossimo"]' if delta > 0
        else 'button[aria-label="Vai al mese precedente"]'
    )
    step = 1 if delta > 0 else -1
    for _ in range(abs(delta)):
        expected_total = current_year * 12 + current_month + step
        # force=True: various transient elements can sit on top of this
        # button depending on timing -- same defensive click style already
        # proven necessary for the Colosseum and Louvre monitors' calendar
        # navigation.
        page.click(selector, force=True)
        # Polling the visible month header (rather than trusting a fixed
        # delay or a network response event) is what actually proved
        # reliable for the Louvre monitor's own month navigation -- applying
        # the same lesson here up front instead of re-discovering it live.
        for _ in range(20):
            page.wait_for_timeout(250)
            try:
                year, month = read_current_month(page)
            except (AttributeError, ValueError):
                continue  # header briefly absent or malformed mid-re-render
            if year * 12 + month == expected_total:
                current_year, current_month = year, month
                break
        else:
            raise TimeoutError(f"Calendar did not advance past {current_year}-{current_month:02d}")


def read_month_days(page):
    """Read every day cell in the currently-displayed calendar month.

    Returns {"statuses": {date_str ("YYYY-MM-DD"): "available" | "unavailable"},
              "slots": {date_str: {time_str ("HH:MM"): "available"}}} --
    "slots" only has an entry for a date when at least one real bookable
    time was found for it.
    """
    statuses = {}
    slots = {}
    for cell in page.query_selector_all(".cal-month-day"):
        day_span = cell.query_selector(".day-number[data-cal-date]")
        if day_span is None:
            continue
        date_str = day_span.get_attribute("data-cal-date")
        css_class = day_span.get_attribute("class") or ""
        statuses[date_str] = "available" if "cal-event-status-available" in css_class else "unavailable"

        day_slots = {}
        for pill in cell.query_selector_all(".event-time-pill"):
            indicator = pill.get_attribute("data-availability-indicator")
            if indicator in (None, "0"):
                continue
            time_text = pill.inner_text().strip()
            day_slots[time_text] = "available"
        if day_slots:
            slots[date_str] = day_slots

    return {"statuses": statuses, "slots": slots}
