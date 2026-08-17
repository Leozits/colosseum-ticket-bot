from louvre_monitor.calendar_client import read_current_month, navigate_to_month, read_month_days


class FakeElement:
    def __init__(self, text="", attrs=None):
        self._text = text
        self._attrs = attrs or {}

    def inner_text(self):
        return self._text

    def get_attribute(self, name):
        return self._attrs.get(name)


class FakePage:
    def __init__(self, month_name, year, day_elements=None):
        self._month_name = month_name
        self._year = year
        self._day_elements = day_elements or []
        self.click_log = []
        self.wait_calls = 0

    def query_selector(self, selector):
        if selector == ".d-month":
            return FakeElement(text=self._month_name)
        if selector == ".d-year":
            return FakeElement(text=str(self._year))
        return None

    def query_selector_all(self, selector):
        if selector == "#calendarContainer input[data-date]":
            return self._day_elements
        return []

    def click(self, selector, force=False):
        self.click_log.append(selector)

    def wait_for_timeout(self, ms):
        self.wait_calls += 1


def test_read_current_month_parses_month_name_and_year():
    page = FakePage("August", 2026)
    assert read_current_month(page) == (2026, 8)


def test_navigate_to_month_clicks_next_for_future_month():
    page = FakePage("August", 2026)
    navigate_to_month(page, 2026, 10)
    assert page.click_log == ["#d-next", "#d-next"]


def test_navigate_to_month_clicks_previous_for_past_month():
    page = FakePage("October", 2026)
    navigate_to_month(page, 2026, 8)
    assert page.click_log == ["#d-previous", "#d-previous"]


def test_navigate_to_month_does_nothing_when_already_on_target():
    page = FakePage("October", 2026)
    navigate_to_month(page, 2026, 10)
    assert page.click_log == []


def test_read_month_days_maps_disabled_attribute_to_unavailable():
    page = FakePage("October", 2026, day_elements=[
        FakeElement(attrs={"data-date": "2026-10-14T03:00:00.000Z"}),
        FakeElement(attrs={"data-date": "2026-10-15T03:00:00.000Z", "disabled": ""}),
    ])
    assert read_month_days(page) == {
        "2026-10-14": "available",
        "2026-10-15": "unavailable",
    }
