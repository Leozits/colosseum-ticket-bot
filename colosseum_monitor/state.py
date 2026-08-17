"""Load/save monitor state (last known day statuses + consecutive failure count) as JSON."""

import json
import os

DEFAULT_STATE = {"day_statuses": {}, "available_slots": {}, "consecutive_failures": 0}


def load_state(path):
    if not os.path.exists(path):
        return dict(DEFAULT_STATE)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(path, state):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)
