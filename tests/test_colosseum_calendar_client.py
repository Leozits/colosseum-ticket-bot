from colosseum_monitor.calendar_client import read_current_month, navigate_to_month

_ITALIAN_MONTHS = [
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


class FakeNavButton:
    def __init__(self, page, selector, css_class):
        self._page = page
        self._selector = selector
        self._css_class = css_class

    def get_attribute(self, name):
        if name == "class":
            return self._css_class
        return None

    def click(self, force=False):
        self._page.click_log.append(self._selector)
        step = 1 if self._selector == ".ui-datepicker-next" else -1
        total = self._page.year * 12 + self._page.month + step
        self._page.year, month_zero_based = divmod(total - 1, 12)
        self._page.month = month_zero_based + 1


class FakeMonthPage:
    def __init__(self, month_name, year, next_disabled=False):
        self.year = year
        self.month = _ITALIAN_MONTHS.index(month_name.lower()) + 1
        self.next_disabled = next_disabled
        self.click_log = []
        self.wait_calls = 0

    def query_selector(self, selector):
        if selector == ".ui-datepicker-title":
            return FakeElement(text=f"{_ITALIAN_MONTHS[self.month - 1].capitalize()} {self.year}")
        if selector == ".ui-datepicker-next":
            cls = "ui-datepicker-next ui-state-disabled" if self.next_disabled else "ui-datepicker-next"
            return FakeNavButton(self, ".ui-datepicker-next", cls)
        if selector == ".ui-datepicker-prev":
            return FakeNavButton(self, ".ui-datepicker-prev", "ui-datepicker-prev")
        return None

    def wait_for_timeout(self, ms):
        self.wait_calls += 1


def test_read_current_month_parses_italian_month_name_and_year():
    page = FakeMonthPage("Settembre", 2026)
    assert read_current_month(page) == (2026, 9)


def test_navigate_to_month_clicks_next_for_future_month():
    page = FakeMonthPage("Settembre", 2026)
    navigate_to_month(page, 2026, 10)
    assert page.click_log == [".ui-datepicker-next"]
    assert (page.year, page.month) == (2026, 10)


def test_navigate_to_month_clicks_previous_for_past_month():
    page = FakeMonthPage("Ottobre", 2026)
    navigate_to_month(page, 2026, 9)
    assert page.click_log == [".ui-datepicker-prev"]


def test_navigate_to_month_does_nothing_when_already_on_target():
    page = FakeMonthPage("Ottobre", 2026)
    navigate_to_month(page, 2026, 10)
    assert page.click_log == []


def test_navigate_to_month_stops_early_when_next_is_disabled():
    # The site's own booking horizon doesn't reach the target month yet --
    # this is what was silently going wrong for the Colosseum monitor
    # before this fix: it used to click "next" until disabled and just read
    # whatever month that landed on, rather than a specific target month.
    page = FakeMonthPage("Settembre", 2026, next_disabled=True)
    navigate_to_month(page, 2026, 12)
    assert page.click_log == []
    assert (page.year, page.month) == (2026, 9)


def test_navigate_to_month_tolerates_a_transiently_malformed_initial_header():
    # Confirmed by testing on the Borghese monitor: the header can
    # transiently be malformed (missing month or year text) right after a
    # fresh page load, not just mid-navigation -- this exercises the same
    # tolerant-retry path fixed there.
    class FlakyOnceThenFinePage(FakeMonthPage):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._first_title_read = True

        def query_selector(self, selector):
            if selector == ".ui-datepicker-title" and self._first_title_read:
                self._first_title_read = False
                return FakeElement(text="")
            return super().query_selector(selector)

    page = FlakyOnceThenFinePage("Settembre", 2026)
    navigate_to_month(page, 2026, 10)
    assert (page.year, page.month) == (2026, 10)
