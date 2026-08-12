import json
import os
from colosseum_monitor import config
from colosseum_monitor.run import check_once


def _canned_response(capacities_by_date):
    slots = [
        {"startDateTime": f"{date_str}T06:45:00Z", "capacity": capacity}
        for date_str, capacity in capacities_by_date.items()
    ]
    return {"success": True, "data": slots}


def test_check_once_logs_and_does_not_notify_when_still_sold_out(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(config, "LOG_PATH", str(tmp_path / "log.txt"))

    sent = []
    result = check_once(
        fetch_calendar=lambda: _canned_response({d: 0 for d in config.TARGET_DATES}),
        send_message=lambda msg: sent.append(msg),
    )

    assert result == 0
    assert sent == []
    with open(config.STATE_PATH) as f:
        state = json.load(f)
    assert state["capacities"] == {d: 0 for d in config.TARGET_DATES}


def test_check_once_notifies_when_a_date_opens_up(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(config, "LOG_PATH", str(tmp_path / "log.txt"))
    with open(config.STATE_PATH, "w") as f:
        json.dump({"capacities": {d: 0 for d in config.TARGET_DATES}, "consecutive_failures": 0}, f)

    sent = []
    opened = {d: 0 for d in config.TARGET_DATES}
    opened[config.TARGET_DATES[0]] = 4
    result = check_once(
        fetch_calendar=lambda: _canned_response(opened),
        send_message=lambda msg: sent.append(msg),
    )

    assert result == 0
    assert len(sent) == 1
    assert config.TARGET_DATES[0] in sent[0]


def test_check_once_skips_entirely_after_monitor_end_date(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(config, "LOG_PATH", str(tmp_path / "log.txt"))
    monkeypatch.setattr(config, "MONITOR_END_DATE", "2000-01-01")

    calls = []
    result = check_once(fetch_calendar=lambda: calls.append(1), send_message=lambda m: None)

    assert result == 0
    assert calls == []
    assert not os.path.exists(config.STATE_PATH)


def test_check_once_logs_error_and_counts_failures_without_crashing(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(config, "LOG_PATH", str(tmp_path / "log.txt"))

    def boom():
        raise RuntimeError("site unreachable")

    sent = []
    result = check_once(fetch_calendar=boom, send_message=lambda msg: sent.append(msg))

    assert result == 1
    assert sent == []
    with open(config.STATE_PATH) as f:
        state = json.load(f)
    assert state["consecutive_failures"] == 1


def test_check_once_alerts_after_threshold_consecutive_failures(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(config, "LOG_PATH", str(tmp_path / "log.txt"))
    with open(config.STATE_PATH, "w") as f:
        json.dump({"capacities": {}, "consecutive_failures": 2}, f)

    def boom():
        raise RuntimeError("site unreachable")

    sent = []
    result = check_once(fetch_calendar=boom, send_message=lambda msg: sent.append(msg))

    assert result == 1
    assert len(sent) == 1
    assert "3 vezes" in sent[0]
