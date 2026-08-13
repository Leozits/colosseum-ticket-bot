import json
from colosseum_monitor.state import load_state, save_state, DEFAULT_STATE


def test_default_state_shape():
    assert DEFAULT_STATE == {"day_statuses": {}, "consecutive_failures": 0, "paused_until": None}


def test_load_state_returns_default_when_file_missing(tmp_path):
    path = str(tmp_path / "state.json")
    assert load_state(path) == DEFAULT_STATE


def test_save_then_load_roundtrips(tmp_path):
    path = str(tmp_path / "state.json")
    state = {
        "day_statuses": {"2026-09-12": "soldout"},
        "consecutive_failures": 1,
        "paused_until": "2026-08-14T01:00:00+00:00",
    }
    save_state(path, state)
    assert load_state(path) == state


def test_save_state_writes_valid_json(tmp_path):
    path = str(tmp_path / "state.json")
    save_state(path, {"day_statuses": {}, "consecutive_failures": 0, "paused_until": None})
    with open(path) as f:
        json.load(f)  # does not raise
