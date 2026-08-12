from colosseum_monitor.calendar_client import build_ajax_payload


def test_build_ajax_payload_has_expected_shape():
    payload = build_ajax_payload(225, 2026, 10)
    assert payload == {
        "action": "midaabc_calendars_month",
        "page": 225,
        "year": 2026,
        "month": 10,
    }
