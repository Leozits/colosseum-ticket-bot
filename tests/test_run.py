import json
import os
from colosseum_monitor import config
from colosseum_monitor.run import check_once


def _result(statuses, slots=None):
    return {"statuses": statuses, "slots": slots or {}}


def test_check_once_logs_and_does_not_notify_when_nothing_changed(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(config, "LOG_PATH", str(tmp_path / "log.txt"))
    days = {"2026-09-12": "soldout", "2026-09-13": "closing"}
    with open(config.STATE_PATH, "w") as f:
        json.dump({"day_statuses": days, "available_slots": {}, "consecutive_failures": 0}, f)

    sent = []
    result = check_once(fetch_days=lambda: _result(days), send_message=lambda msg: sent.append(msg))

    assert result == 0
    assert sent == []
    with open(config.STATE_PATH) as f:
        state = json.load(f)
    assert state["day_statuses"] == days


def test_check_once_notifies_when_a_date_becomes_available(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(config, "LOG_PATH", str(tmp_path / "log.txt"))
    with open(config.STATE_PATH, "w") as f:
        json.dump({"day_statuses": {"2026-09-13": "closing"}, "available_slots": {}, "consecutive_failures": 0}, f)

    sent = []
    result = check_once(
        fetch_days=lambda: _result({"2026-09-13": "available"}),
        send_message=lambda msg: sent.append(msg),
    )

    assert result == 0
    assert len(sent) == 1
    assert "2026-09-13" in sent[0]


def test_check_once_includes_available_times_in_notification_and_log(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(config, "LOG_PATH", str(tmp_path / "log.txt"))
    with open(config.STATE_PATH, "w") as f:
        json.dump({"day_statuses": {"2026-09-16": "closing"}, "available_slots": {}, "consecutive_failures": 0}, f)

    slots = {"2026-09-16": {"13:15": "available", "13:30": "available", "14:00": "closed"}}
    sent = []
    result = check_once(
        fetch_days=lambda: _result({"2026-09-16": "available"}, slots),
        send_message=lambda msg: sent.append(msg),
    )

    assert result == 0
    assert "13:15" in sent[0]
    assert "13:30" in sent[0]
    assert "14:00" not in sent[0]
    with open(config.LOG_PATH) as f:
        log_contents = f.read()
    assert "SLOTS" in log_contents
    assert "2026-09-16:[13:15,13:30]" in log_contents
    with open(config.STATE_PATH) as f:
        state = json.load(f)
    assert state["available_slots"] == slots


def test_check_once_still_saves_state_when_notification_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(config, "LOG_PATH", str(tmp_path / "log.txt"))
    with open(config.STATE_PATH, "w") as f:
        json.dump({"day_statuses": {"2026-09-13": "closing"}, "available_slots": {}, "consecutive_failures": 0}, f)

    def broken_send(msg):
        raise ConnectionError("smtp unreachable")

    result = check_once(fetch_days=lambda: _result({"2026-09-13": "available"}), send_message=broken_send)

    assert result == 0
    with open(config.STATE_PATH) as f:
        state = json.load(f)
    assert state["day_statuses"] == {"2026-09-13": "available"}
    with open(config.LOG_PATH) as f:
        log_contents = f.read()
    assert "notification failed" in log_contents


def test_check_once_skips_entirely_after_monitor_end_date(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(config, "LOG_PATH", str(tmp_path / "log.txt"))
    monkeypatch.setattr(config, "MONITOR_END_DATE", "2000-01-01")

    calls = []
    result = check_once(fetch_days=lambda: calls.append(1), send_message=lambda m: None)

    assert result == 0
    assert calls == []
    assert not os.path.exists(config.STATE_PATH)


def test_check_once_logs_error_and_counts_failures_without_crashing(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(config, "LOG_PATH", str(tmp_path / "log.txt"))

    def boom():
        raise RuntimeError("site unreachable")

    sent = []
    result = check_once(fetch_days=boom, send_message=lambda msg: sent.append(msg))

    assert result == 1
    assert sent == []
    with open(config.STATE_PATH) as f:
        state = json.load(f)
    assert state["consecutive_failures"] == 1


def test_check_once_never_alerts_no_matter_how_many_consecutive_failures(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(config, "LOG_PATH", str(tmp_path / "log.txt"))
    with open(config.STATE_PATH, "w") as f:
        json.dump({"day_statuses": {}, "available_slots": {}, "consecutive_failures": 10}, f)

    def boom():
        raise RuntimeError("site unreachable")

    sent = []
    result = check_once(fetch_days=boom, send_message=lambda msg: sent.append(msg))

    assert result == 1
    assert sent == []
