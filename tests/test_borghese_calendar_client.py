import pytest
from borghese_monitor.calendar_client import read_current_month, navigate_to_month, read_month_days

_MONTH_NAMES = [
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
]


class FakeElement:
    def __init__(self, text="", attrs=None):
        self._text = text
        self._attrs = attrs or {}

    def inner_text(self):
        return self._text

    def get_attribute(self, name):
        return self._attrs.get(name)


class FakeCell:
    def __init__(self, day_span=None, pills=None):
        self._day_span = day_span
        self._pills = pills or []

    def query_selector(self, selector):
        if selector == ".day-number[data-cal-date]":
            return self._day_span
        return None

    def query_selector_all(self, selector):
        if selector == ".event-time-pill":
            return self._pills
        return []


class FakeDaysPage:
    def __init__(self, cells):
        self._cells = cells

    def query_selector_all(self, selector):
        if selector == ".cal-month-day":
            return self._cells
        return []


class FakeMonthPage:
    def __init__(self, month_name, year):
        self.year = year
        self.month = _MONTH_NAMES.index(month_name.lower()) + 1
        self.click_log = []
        self.wait_calls = 0

    def query_selector(self, selector):
        if selector == ".btn-today.text-center":
            return FakeElement(text=f"{_MONTH_NAMES[self.month - 1].capitalize()} {self.year}")
        return None

    def click(self, selector, force=False):
        self.click_log.append(selector)
        step = 1 if selector == 'button[aria-label="Vai al mese prossimo"]' else -1
        total = self.year * 12 + self.month + step
        self.year, month_zero_based = divmod(total - 1, 12)
        self.month = month_zero_based + 1

    def wait_for_timeout(self, ms):
        self.wait_calls += 1


class StuckFakeMonthPage(FakeMonthPage):
    def click(self, selector, force=False):
        self.click_log.append(selector)  # month never actually advances


def test_read_current_month_parses_italian_month_name_and_year():
    page = FakeMonthPage("Settembre", 2026)
    assert read_current_month(page) == (2026, 9)


def test_navigate_to_month_clicks_next_for_future_month():
    page = FakeMonthPage("Settembre", 2026)
    navigate_to_month(page, 2026, 10)
    assert page.click_log == ['button[aria-label="Vai al mese prossimo"]']


def test_navigate_to_month_clicks_previous_for_past_month():
    page = FakeMonthPage("Ottobre", 2026)
    navigate_to_month(page, 2026, 9)
    assert page.click_log == ['button[aria-label="Vai al mese precedente"]']


def test_navigate_to_month_does_nothing_when_already_on_target():
    page = FakeMonthPage("Ottobre", 2026)
    navigate_to_month(page, 2026, 10)
    assert page.click_log == []


def test_navigate_to_month_raises_if_calendar_never_advances():
    page = StuckFakeMonthPage("Settembre", 2026)
    with pytest.raises(TimeoutError):
        navigate_to_month(page, 2026, 10)


def test_navigate_to_month_tolerates_a_transiently_malformed_initial_header():
    # Confirmed by live testing: the header text intermittently comes back
    # with no space between month and year (e.g. right after a fresh page
    # load), which used to crash read_current_month's rsplit-based parsing
    # with "not enough values to unpack".
    class FlakyOnceThenFinePage(FakeMonthPage):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._first_title_read = True

        def query_selector(self, selector):
            if selector == ".btn-today.text-center" and self._first_title_read:
                self._first_title_read = False
                return FakeElement(text="2026")  # no space -- rsplit(" ", 1) yields 1 item
            return super().query_selector(selector)

    page = FlakyOnceThenFinePage("Settembre", 2026)
    navigate_to_month(page, 2026, 10)
    assert (page.year, page.month) == (2026, 10)


def test_read_month_days_maps_available_class_and_lists_real_slots():
    cell = FakeCell(
        day_span=FakeElement(attrs={"data-cal-date": "2026-10-23", "class": "day-number cal-event-status-available"}),
        pills=[
            FakeElement(text="19:00", attrs={"data-availability-indicator": "2"}),
            FakeElement(text="00:00", attrs={"data-availability-indicator": "0"}),
        ],
    )
    page = FakeDaysPage([cell])
    assert read_month_days(page) == {
        "statuses": {"2026-10-23": "available"},
        "slots": {"2026-10-23": {"19:00": "available"}},
    }


def test_read_month_days_maps_missing_status_class_to_unavailable():
    cell = FakeCell(day_span=FakeElement(attrs={"data-cal-date": "2026-10-25", "class": "day-number"}))
    page = FakeDaysPage([cell])
    assert read_month_days(page) == {"statuses": {"2026-10-25": "unavailable"}, "slots": {}}


def test_read_month_days_skips_cells_without_a_day_number():
    page = FakeDaysPage([FakeCell(day_span=None)])
    assert read_month_days(page) == {"statuses": {}, "slots": {}}
