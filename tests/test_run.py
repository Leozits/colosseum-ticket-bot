import json
import os
from datetime import datetime, timezone
from colosseum_monitor import config
from colosseum_monitor.run import check_once
from colosseum_monitor.schedule_window import next_resume_time

FIXED_NOW = datetime(2026, 8, 13, 14, 0, 0, tzinfo=timezone.utc)  # 11:00 BRT


def test_check_once_logs_and_pauses_when_nothing_available(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(config, "LOG_PATH", str(tmp_path / "log.txt"))
    days = {"2026-09-12": "soldout", "2026-09-13": "closing"}
    with open(config.STATE_PATH, "w") as f:
        json.dump({"day_statuses": days, "consecutive_failures": 0, "paused_until": None}, f)

    sent = []
    result = check_once(
        fetch_days=lambda: days,
        send_message=lambda msg: sent.append(msg),
        now=lambda: FIXED_NOW,
    )

    assert result == 0
    assert sent == []
    with open(config.STATE_PATH) as f:
        state = json.load(f)
    assert state["day_statuses"] == days
    assert state["paused_until"] == next_resume_time(FIXED_NOW).isoformat()


def test_check_once_notifies_and_does_not_pause_when_a_date_becomes_available(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(config, "LOG_PATH", str(tmp_path / "log.txt"))
    with open(config.STATE_PATH, "w") as f:
        json.dump({"day_statuses": {"2026-09-13": "closing"}, "consecutive_failures": 0, "paused_until": None}, f)

    sent = []
    result = check_once(
        fetch_days=lambda: {"2026-09-13": "available"},
        send_message=lambda msg: sent.append(msg),
        now=lambda: FIXED_NOW,
    )

    assert result == 0
    assert len(sent) == 1
    assert "2026-09-13" in sent[0]
    with open(config.STATE_PATH) as f:
        state = json.load(f)
    assert state["paused_until"] is None


def test_check_once_skips_the_actual_check_while_paused(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(config, "LOG_PATH", str(tmp_path / "log.txt"))
    paused_until = "2026-08-14T01:00:00+00:00"  # 22:00 BRT, still in the future relative to FIXED_NOW
    with open(config.STATE_PATH, "w") as f:
        json.dump({"day_statuses": {"2026-09-12": "soldout"}, "consecutive_failures": 0, "paused_until": paused_until}, f)

    calls = []
    result = check_once(
        fetch_days=lambda: calls.append(1),
        send_message=lambda m: None,
        now=lambda: FIXED_NOW,
    )

    assert result == 0
    assert calls == []  # the site was never actually checked
    with open(config.LOG_PATH) as f:
        log_contents = f.read()
    assert "SKIP" in log_contents
    assert paused_until in log_contents


def test_check_once_resumes_checking_once_pause_has_elapsed(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(config, "LOG_PATH", str(tmp_path / "log.txt"))
    paused_until = "2026-08-13T10:00:00+00:00"  # already in the past relative to FIXED_NOW
    with open(config.STATE_PATH, "w") as f:
        json.dump({"day_statuses": {"2026-09-12": "soldout"}, "consecutive_failures": 0, "paused_until": paused_until}, f)

    calls = []
    result = check_once(
        fetch_days=lambda: calls.append(1) or {"2026-09-12": "soldout"},
        send_message=lambda m: None,
        now=lambda: FIXED_NOW,
    )

    assert result == 0
    assert calls == [1]  # the check actually ran


def test_check_once_still_saves_state_when_notification_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(config, "LOG_PATH", str(tmp_path / "log.txt"))
    with open(config.STATE_PATH, "w") as f:
        json.dump({"day_statuses": {"2026-09-13": "closing"}, "consecutive_failures": 0, "paused_until": None}, f)

    def broken_send(msg):
        raise ConnectionError("smtp unreachable")

    result = check_once(
        fetch_days=lambda: {"2026-09-13": "available"},
        send_message=broken_send,
        now=lambda: FIXED_NOW,
    )

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
    result = check_once(fetch_days=boom, send_message=lambda msg: sent.append(msg), now=lambda: FIXED_NOW)

    assert result == 1
    assert sent == []
    with open(config.STATE_PATH) as f:
        state = json.load(f)
    assert state["consecutive_failures"] == 1


def test_check_once_alerts_after_threshold_consecutive_failures(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(config, "LOG_PATH", str(tmp_path / "log.txt"))
    with open(config.STATE_PATH, "w") as f:
        json.dump({"day_statuses": {}, "consecutive_failures": 2, "paused_until": None}, f)

    def boom():
        raise RuntimeError("site unreachable")

    sent = []
    result = check_once(fetch_days=boom, send_message=lambda msg: sent.append(msg), now=lambda: FIXED_NOW)

    assert result == 1
    assert len(sent) == 1
    assert "3 vezes" in sent[0]
