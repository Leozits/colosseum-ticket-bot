import json
from versailles_monitor import config
from versailles_monitor.run import check_once


def _result(statuses):
    return {"statuses": statuses, "slots": {}}


def test_check_once_notifies_with_versailles_wording_when_a_date_becomes_available(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(config, "LOG_PATH", str(tmp_path / "log.txt"))
    with open(config.STATE_PATH, "w") as f:
        json.dump({"day_statuses": {"2026-10-14": "unavailable"}, "available_slots": {}, "consecutive_failures": 0}, f)

    sent = []
    result = check_once(
        fetch_days=lambda: _result({"2026-10-14": "available"}),
        send_message=lambda msg: sent.append(msg),
    )

    assert result == 0
    assert len(sent) == 1
    assert "Versalhes" in sent[0]
    assert "2026-10-14" in sent[0]
    assert config.TICKET_URL in sent[0]


def test_check_once_does_not_notify_when_nothing_changed(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(config, "LOG_PATH", str(tmp_path / "log.txt"))
    days = {"2026-10-14": "unavailable"}
    with open(config.STATE_PATH, "w") as f:
        json.dump({"day_statuses": days, "available_slots": {}, "consecutive_failures": 0}, f)

    sent = []
    result = check_once(fetch_days=lambda: _result(days), send_message=lambda msg: sent.append(msg))

    assert result == 0
    assert sent == []


def test_check_once_skips_entirely_after_monitor_end_date(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(config, "LOG_PATH", str(tmp_path / "log.txt"))
    monkeypatch.setattr(config, "MONITOR_END_DATE", "2000-01-01")

    calls = []
    result = check_once(fetch_days=lambda: calls.append(1), send_message=lambda m: None)

    assert result == 0
    assert calls == []
