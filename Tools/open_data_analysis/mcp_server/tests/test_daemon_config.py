from __future__ import annotations

import subprocess
import sys

import pytest

from sandbox_mcp import daemon_client
from sandbox_mcp.config import daemon_config


def test_daemon_config_uses_aslm_env_port(monkeypatch):
    monkeypatch.delenv("SANDBOX_DAEMON_PORT", raising=False)
    monkeypatch.setenv("ASLM_ODA_DAEMON_PORT", "9876")

    cfg = daemon_config()

    assert cfg.port == 9876
    assert cfg.url == "http://127.0.0.1:9876"


def test_daemon_config_prefers_sandbox_env_over_aslm_env(monkeypatch):
    monkeypatch.setenv("ASLM_ODA_DAEMON_PORT", "9876")
    monkeypatch.setenv("SANDBOX_DAEMON_PORT", "9911")

    cfg = daemon_config()

    assert cfg.port == 9911
    assert cfg.url == "http://127.0.0.1:9911"


def test_daemon_config_uses_env_port_and_paths(monkeypatch, tmp_path):
    state = tmp_path / "state.json"
    log = tmp_path / "sandboxd.log"
    monkeypatch.setenv("SANDBOX_USE_DAEMON", "1")
    monkeypatch.setenv("SANDBOX_DAEMON_PORT", "9911")
    monkeypatch.setenv("SANDBOX_STATE_PATH", str(state))
    monkeypatch.setenv("SANDBOX_DAEMON_LOG", str(log))

    cfg = daemon_config()

    assert cfg.use_daemon is True
    assert cfg.autostart is True
    assert cfg.url == "http://127.0.0.1:9911"
    assert cfg.state_path == state.resolve()
    assert cfg.log_path == log.resolve()
    assert cfg.startup_lock_path.name == "sandboxd-127.0.0.1-9911.lock"


def test_explicit_daemon_url_does_not_autostart_by_default(monkeypatch):
    monkeypatch.setenv("SANDBOX_DAEMON_URL", "http://127.0.0.1:9999")
    monkeypatch.delenv("SANDBOX_USE_DAEMON", raising=False)
    monkeypatch.delenv("SANDBOX_DAEMON_AUTOSTART", raising=False)

    cfg = daemon_config()

    assert cfg.use_daemon is True
    assert cfg.autostart is False
    assert daemon_client.daemon_url() == "http://127.0.0.1:9999"


def test_ensure_daemon_lazy_starts_when_allowed(monkeypatch, tmp_path):
    monkeypatch.setenv("SANDBOX_USE_DAEMON", "1")
    monkeypatch.setenv("SANDBOX_DAEMON_PORT", "9922")
    monkeypatch.setenv("SANDBOX_DAEMON_LOG", str(tmp_path / "sandboxd.log"))
    daemon_client._DAEMON_PROCESS = None
    calls = {"health": 0, "popen": None}

    def fake_health(*, base_url=None):
        calls["health"] += 1
        if calls["health"] < 3:
            raise daemon_client.SandboxDaemonError("down")
        return {"ok": True, "service": "sandboxd"}

    class FakeProcess:
        def poll(self):
            return None

    def fake_popen(argv, **kwargs):
        calls["popen"] = (argv, kwargs)
        return FakeProcess()

    monkeypatch.setattr(daemon_client, "health", fake_health)
    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    assert daemon_client.ensure_daemon() == "http://127.0.0.1:9922"
    argv, kwargs = calls["popen"]
    assert argv[:3] == [sys.executable, "-m", "sandbox_mcp.daemon"]
    assert "--port" in argv
    assert "9922" in argv
    assert kwargs["stdin"] is subprocess.DEVNULL


def test_ensure_daemon_reuses_existing_sandboxd_after_lock(monkeypatch, tmp_path):
    monkeypatch.setenv("SANDBOX_USE_DAEMON", "1")
    monkeypatch.setenv("SANDBOX_DAEMON_PORT", "9944")
    monkeypatch.setenv("SANDBOX_DAEMON_STARTUP_LOCK", str(tmp_path / "startup.lock"))
    daemon_client._DAEMON_PROCESS = None
    calls = {"health": 0, "popen": 0}

    def fake_health(*, base_url=None):
        calls["health"] += 1
        if calls["health"] == 1:
            raise daemon_client.SandboxDaemonError("down")
        return {"ok": True, "service": "sandboxd"}

    def fake_popen(*args, **kwargs):
        calls["popen"] += 1
        raise AssertionError("should not spawn when second health succeeds")

    monkeypatch.setattr(daemon_client, "health", fake_health)
    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    assert daemon_client.ensure_daemon() == "http://127.0.0.1:9944"
    assert calls["popen"] == 0


def test_ensure_daemon_rejects_non_sandboxd_health(monkeypatch):
    monkeypatch.setenv("SANDBOX_DAEMON_URL", "http://127.0.0.1:9955")
    monkeypatch.delenv("SANDBOX_USE_DAEMON", raising=False)
    monkeypatch.delenv("SANDBOX_DAEMON_AUTOSTART", raising=False)

    monkeypatch.setattr(daemon_client, "health", lambda *, base_url=None: {"ok": True})

    with pytest.raises(daemon_client.SandboxDaemonError, match="not sandboxd"):
        daemon_client.ensure_daemon()


def test_ensure_daemon_refuses_autostart_for_explicit_url(monkeypatch):
    monkeypatch.setenv("SANDBOX_DAEMON_URL", "http://127.0.0.1:9933")
    monkeypatch.delenv("SANDBOX_USE_DAEMON", raising=False)
    monkeypatch.delenv("SANDBOX_DAEMON_AUTOSTART", raising=False)

    def fake_health(*, base_url=None):
        raise daemon_client.SandboxDaemonError("down")

    monkeypatch.setattr(daemon_client, "health", fake_health)

    with pytest.raises(daemon_client.SandboxDaemonError, match="down"):
        daemon_client.ensure_daemon()
