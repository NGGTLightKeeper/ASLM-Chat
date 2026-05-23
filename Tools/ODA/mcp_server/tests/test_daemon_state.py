from __future__ import annotations

import logging
import json

from sandbox_mcp import daemon
from sandbox_mcp import runner


def test_restore_state_quarantines_invalid_json(monkeypatch, tmp_path, caplog):
    state = tmp_path / "state.json"
    state.write_text("{not json", encoding="utf-8")
    monkeypatch.setenv("SANDBOX_STATE_PATH", str(state))

    with caplog.at_level(logging.WARNING):
        daemon._restore_state()

    assert not state.exists()
    assert list(tmp_path.glob("state.json.bad-*"))
    assert "invalid json" in caplog.text


def test_restore_state_quarantines_invalid_run_id(monkeypatch, tmp_path):
    state = tmp_path / "state.json"
    state.write_text(
        '{"active_run_id": "bad", "active_run_dir": "C:/tmp/bad", "last_activity": 1}',
        encoding="utf-8",
    )
    monkeypatch.setenv("SANDBOX_STATE_PATH", str(state))

    daemon._restore_state()

    assert not state.exists()
    assert list(tmp_path.glob("state.json.bad-*"))


def test_restore_state_keeps_missing_run_dir_state_but_does_not_restore(monkeypatch, tmp_path, caplog):
    run_id = "a" * 32
    state = tmp_path / "state.json"
    missing = tmp_path / run_id
    state.write_text(json.dumps({
        "active_run_id": run_id,
        "active_run_dir": str(missing),
        "last_activity": 1,
    }), encoding="utf-8")
    monkeypatch.setenv("SANDBOX_STATE_PATH", str(state))
    with runner._SESSION_LOCK:
        runner._ACTIVE_RUN_ID = None
        runner._ACTIVE_RUN_DIR = None
        runner._LAST_ACTIVITY = 0.0

    with caplog.at_level(logging.WARNING):
        daemon._restore_state()

    assert state.exists()
    assert runner._ACTIVE_RUN_ID is None
    assert "missing or mismatched run dir" in caplog.text
