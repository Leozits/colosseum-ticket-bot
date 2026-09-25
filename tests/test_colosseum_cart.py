from colosseum_monitor.cart import (
    pick_earliest_newly_available,
    set_participant_count,
    select_time_slot,
    add_to_cart,
    is_cart_empty,
    wait_for_cart_to_empty,
)


# --- pick_earliest_newly_available -----------------------------------------

def test_pick_earliest_newly_available_prefers_the_earliest_date():
    previous = {"2026-10-22": "closing", "2026-10-23": "closing"}
    current = {"2026-10-22": "available", "2026-10-23": "available"}
    slots = {"2026-10-22": {"09:00": "available"}, "2026-10-23": {"08:45": "available"}}
    assert pick_earliest_newly_available(previous, current, slots) == ("2026-10-22", "09:00")


def test_pick_earliest_newly_available_picks_earliest_time_within_a_date():
    previous = {"2026-10-22": "closing"}
    current = {"2026-10-22": "available"}
    slots = {"2026-10-22": {"12:00": "available", "09:00": "available"}}
    assert pick_earliest_newly_available(previous, current, slots) == ("2026-10-22", "09:00")


def test_pick_earliest_newly_available_ignores_dates_already_available_before():
    previous = {"2026-10-22": "available"}
    current = {"2026-10-22": "available"}
    slots = {"2026-10-22": {"09:00": "available"}}
    assert pick_earliest_newly_available(previous, current, slots) is None


def test_pick_earliest_newly_available_skips_a_date_with_no_recorded_slot():
    previous = {"2026-10-22": "closing", "2026-10-23": "closing"}
    current = {"2026-10-22": "available", "2026-10-23": "available"}
    slots = {"2026-10-23": {"08:45": "available"}}  # 2026-10-22 has no slots entry
    assert pick_earliest_newly_available(previous, current, slots) == ("2026-10-23", "08:45")


def test_pick_earliest_newly_available_returns_none_when_nothing_qualifies():
    previous = {"2026-10-22": "closing"}
    current = {"2026-10-22": "closing"}
    slots = {}
    assert pick_earliest_newly_available(previous, current, slots) is None


# --- set_participant_count --------------------------------------------------

class FakeParticipantsPage:
    def __init__(self, start_value="", increment=1):
        self.value = start_value
        self.increment = increment
        self.click_count = 0
        self.wait_calls = 0

    def query_selector(self, selector):
        if selector == ".abc-participantspicker input[type='number']":
            return _FakeInput(self)
        if selector == '.abc-participantspicker button[data-dir="up"]':
            return _FakePlusButton(self)
        return None

    def wait_for_timeout(self, ms):
        self.wait_calls += 1


class _FakeInput:
    def __init__(self, page):
        self._page = page

    def get_attribute(self, name):
        return self._page.value if name == "value" else None


class _FakePlusButton:
    def __init__(self, page):
        self._page = page

    def click(self, force=False):
        self._page.click_count += 1
        current = int(self._page.value) if self._page.value.isdigit() else 0
        self._page.value = str(current + self._page.increment)


def test_set_participant_count_clicks_until_target_reached():
    page = FakeParticipantsPage(start_value="", increment=1)
    set_participant_count(page, 2)
    assert page.value == "2"
    assert page.click_count == 2


def test_set_participant_count_stops_early_if_a_click_overshoots_the_target():
    # Confirmed live: a single click was observed jumping the value by more
    # than one increment -- this must not cause an extra, unwanted click.
    page = FakeParticipantsPage(start_value="", increment=2)
    set_participant_count(page, 1)
    assert page.value == "2"
    assert page.click_count == 1


# --- select_time_slot --------------------------------------------------------

class FakeElement:
    def __init__(self, text="", attrs=None, visible=True, on_click=None):
        self._text = text
        self._attrs = dict(attrs or {})
        self._visible = visible
        self.clicked = False
        self._on_click = on_click

    def inner_text(self):
        return self._text

    def get_attribute(self, name):
        return self._attrs.get(name)

    def is_visible(self):
        return self._visible

    def click(self, force=False):
        self.clicked = True
        if self._on_click:
            self._on_click()


class FakeLabel:
    def __init__(self, text, input_element):
        self._text = text
        self._input = input_element

    def inner_text(self):
        return self._text

    def query_selector(self, selector):
        if selector == "input[name='slot']":
            return self._input
        return None


class FakeSlotPage:
    def __init__(self, labels):
        self._labels = labels

    def query_selector_all(self, selector):
        if selector == ".abc-slotpicker label":
            return self._labels
        return []


def test_select_time_slot_clicks_the_matching_available_radio():
    target_input = FakeElement()
    other_input = FakeElement()
    page = FakeSlotPage([
        FakeLabel("09:00Vendita chiusa o sold out", other_input),
        FakeLabel("09:45Disponibilità: 4", target_input),
    ])
    assert select_time_slot(page, "09:45") is True
    assert target_input.clicked is True
    assert other_input.clicked is False


def test_select_time_slot_returns_false_when_the_matching_time_is_disabled():
    disabled_input = FakeElement(attrs={"disabled": ""})
    page = FakeSlotPage([FakeLabel("09:45Vendita chiusa o sold out", disabled_input)])
    assert select_time_slot(page, "09:45") is False
    assert disabled_input.clicked is False


def test_select_time_slot_returns_false_when_time_not_found():
    page = FakeSlotPage([FakeLabel("09:45Disponibilità: 4", FakeElement())])
    assert select_time_slot(page, "10:30") is False


# --- add_to_cart / is_cart_empty ---------------------------------------------

class FakeCartPage:
    def __init__(self, buttons, showcart_visible):
        self._buttons = buttons
        self._showcart_visible = showcart_visible

    def query_selector_all(self, selector):
        if selector == "button":
            return self._buttons
        return []

    def query_selector(self, selector):
        if selector == "#btn-showcart":
            return FakeElement(visible=self._showcart_visible)
        return None

    def wait_for_timeout(self, ms):
        pass


def test_add_to_cart_returns_true_when_cart_becomes_non_empty():
    page = FakeCartPage(buttons=[], showcart_visible=False)
    add_button = FakeElement(text="Aggiungi", on_click=lambda: setattr(page, "_showcart_visible", True))
    page._buttons = [FakeElement(text="Altro"), add_button]

    assert add_to_cart(page) is True
    assert add_button.clicked is True


def test_add_to_cart_returns_false_when_cart_stays_empty():
    # Mirrors the real observed failure: the button is clickable, the click
    # goes through, but the site's own 403 (Turnstile) means nothing was
    # actually added.
    add_button = FakeElement(text="Aggiungi")
    page = FakeCartPage(buttons=[add_button], showcart_visible=False)
    assert add_to_cart(page) is False


def test_add_to_cart_returns_false_when_button_not_found():
    page = FakeCartPage(buttons=[FakeElement(text="Outro")], showcart_visible=False)
    assert add_to_cart(page) is False


def test_is_cart_empty_reflects_showcart_visibility():
    assert is_cart_empty(FakeCartPage(buttons=[], showcart_visible=False)) is True
    assert is_cart_empty(FakeCartPage(buttons=[], showcart_visible=True)) is False


# --- wait_for_cart_to_empty ---------------------------------------------------

class FakeCartWaitPage:
    def __init__(self, empty_after_n_reloads):
        self.reload_count = 0
        self._empty_after = empty_after_n_reloads
        self.wait_calls = []

    def wait_for_timeout(self, ms):
        self.wait_calls.append(ms)

    def reload(self, wait_until=None):
        self.reload_count += 1

    def wait_for_selector(self, selector, timeout=None):
        pass

    def query_selector(self, selector):
        if selector == "#btn-showcart":
            return FakeElement(visible=self.reload_count < self._empty_after)
        return None


def test_wait_for_cart_to_empty_polls_until_showcart_disappears():
    page = FakeCartWaitPage(empty_after_n_reloads=3)
    result = wait_for_cart_to_empty(page, poll_interval_seconds=5, max_wait_seconds=3600)
    assert result is True
    assert page.reload_count == 3
    assert page.wait_calls == [5000, 5000, 5000]


def test_wait_for_cart_to_empty_gives_up_after_max_wait():
    page = FakeCartWaitPage(empty_after_n_reloads=999)
    result = wait_for_cart_to_empty(page, poll_interval_seconds=10, max_wait_seconds=25)
    assert result is False
    assert page.reload_count == 3
