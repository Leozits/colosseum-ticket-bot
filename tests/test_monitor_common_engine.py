import json
import os
from types import SimpleNamespace

from monitor_common.engine import check_once


def _config(tmp_path, **overrides):
    defaults = dict(
        STATE_PATH=str(tmp_path / "state.json"),
        LOG_PATH=str(tmp_path / "log.txt"),
        MONITOR_END_DATE="2099-01-01",
        CONSECUTIVE_FAILURES_ALERT_THRESHOLD=3,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _result(statuses, slots=None):
    return {"statuses": statuses, "slots": slots or {}}


def _format_availability_message(dates, slots):
    return "AVAILABLE:" + ",".join(dates)


def _format_failure_message(consecutive_failures, error_message):
    return f"FAILED:{consecutive_failures}:{error_message}"


def test_check_once_logs_and_does_not_notify_when_nothing_changed(tmp_path):
    config = _config(tmp_path)
    days = {"2026-09-12": "soldout", "2026-09-13": "closing"}
    with open(config.STATE_PATH, "w") as f:
        json.dump({"day_statuses": days, "available_slots": {}, "consecutive_failures": 0}, f)

    sent = []
    result = check_once(
        config, _format_availability_message, _format_failure_message,
        fetch_days=lambda: _result(days), send_message=lambda msg: sent.append(msg),
    )

    assert result == 0
    assert sent == []
    with open(config.STATE_PATH) as f:
        assert json.load(f)["day_statuses"] == days


def test_check_once_notifies_when_a_date_becomes_available(tmp_path):
    config = _config(tmp_path)
    with open(config.STATE_PATH, "w") as f:
        json.dump({"day_statuses": {"2026-09-13": "closing"}, "available_slots": {}, "consecutive_failures": 0}, f)

    sent = []
    result = check_once(
        config, _format_availability_message, _format_failure_message,
        fetch_days=lambda: _result({"2026-09-13": "available"}),
        send_message=lambda msg: sent.append(msg),
    )

    assert result == 0
    assert sent == ["AVAILABLE:2026-09-13"]


def test_check_once_still_saves_state_when_notification_fails(tmp_path):
    config = _config(tmp_path)
    with open(config.STATE_PATH, "w") as f:
        json.dump({"day_statuses": {"2026-09-13": "closing"}, "available_slots": {}, "consecutive_failures": 0}, f)

    def broken_send(msg):
        raise ConnectionError("smtp unreachable")

    result = check_once(
        config, _format_availability_message, _format_failure_message,
        fetch_days=lambda: _result({"2026-09-13": "available"}), send_message=broken_send,
    )

    assert result == 0
    with open(config.STATE_PATH) as f:
        assert json.load(f)["day_statuses"] == {"2026-09-13": "available"}
    with open(config.LOG_PATH) as f:
        assert "notification failed" in f.read()


def test_check_once_skips_entirely_after_monitor_end_date(tmp_path):
    config = _config(tmp_path, MONITOR_END_DATE="2000-01-01")

    calls = []
    result = check_once(
        config, _format_availability_message, _format_failure_message,
        fetch_days=lambda: calls.append(1), send_message=lambda m: None,
    )

    assert result == 0
    assert calls == []
    assert not os.path.exists(config.STATE_PATH)


def test_check_once_logs_error_and_counts_failures_without_crashing(tmp_path):
    config = _config(tmp_path)

    def boom():
        raise RuntimeError("site unreachable")

    sent = []
    result = check_once(
        config, _format_availability_message, _format_failure_message,
        fetch_days=boom, send_message=lambda msg: sent.append(msg),
    )

    assert result == 1
    assert sent == []
    with open(config.STATE_PATH) as f:
        assert json.load(f)["consecutive_failures"] == 1


def test_check_once_alerts_after_threshold_consecutive_failures(tmp_path):
    config = _config(tmp_path)
    with open(config.STATE_PATH, "w") as f:
        json.dump({"day_statuses": {}, "available_slots": {}, "consecutive_failures": 2}, f)

    def boom():
        raise RuntimeError("site unreachable")

    sent = []
    result = check_once(
        config, _format_availability_message, _format_failure_message,
        fetch_days=boom, send_message=lambda msg: sent.append(msg),
    )

    assert result == 1
    assert sent == ["FAILED:3:site unreachable"]
