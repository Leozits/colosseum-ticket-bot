import json
from colosseum_monitor.state import load_state, save_state, DEFAULT_STATE


def test_default_state_shape():
    assert DEFAULT_STATE == {"capacities": {}, "consecutive_failures": 0}


def test_load_state_returns_default_when_file_missing(tmp_path):
    path = str(tmp_path / "state.json")
    assert load_state(path) == DEFAULT_STATE


def test_save_then_load_roundtrips(tmp_path):
    path = str(tmp_path / "state.json")
    state = {"capacities": {"2026-10-23": 5}, "consecutive_failures": 1}
    save_state(path, state)
    assert load_state(path) == state


def test_save_state_writes_valid_json(tmp_path):
    path = str(tmp_path / "state.json")
    save_state(path, {"capacities": {}, "consecutive_failures": 0})
    with open(path) as f:
        json.load(f)  # does not raise
