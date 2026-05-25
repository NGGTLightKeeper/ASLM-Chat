"""Unit tests for runner helpers (no Docker)."""
from __future__ import annotations

import asyncio
import json

import pytest

from sandbox_mcp.output import truncate_output
from sandbox_mcp.runner import (
    MAX_TIMEOUT,
    MIN_TIMEOUT,
    SandboxRunRequest,
    _container_name,
    _docker_create_argv,
    _docker_run_flags,
    _ensure_container,
    _ensure_image,
    _verify_image_local,
    _cleanup_orphan_containers,
    _timeout,
    _volume_mounts,
    doctor_sandbox,
    format_result,
    parse_run_request,
    validate_cmd,
)


def test_validate_cmd():
    assert validate_cmd(["echo", "a"]) == ["echo", "a"]
    with pytest.raises(ValueError):
        validate_cmd([])
    with pytest.raises(ValueError):
        validate_cmd(["ok", 1])


def test_parse_run_request_minimal():
    req = parse_run_request({"cmd": ["bash", "-lc", "true"]})
    assert req.cmd == ["bash", "-lc", "true"]
    assert req.input_files == []
    assert req.output_files == []


def test_timeout_clamp(monkeypatch):
    monkeypatch.setenv("SANDBOX_TIMEOUT", "9999")
    assert _timeout() == MAX_TIMEOUT
    monkeypatch.setenv("SANDBOX_TIMEOUT", "0")
    assert _timeout() == MIN_TIMEOUT


def test_truncate_output_defaults():
    text, truncated = truncate_output("hello")
    assert text == "hello"
    assert truncated is False
    big = "x" * 100_000
    text, truncated = truncate_output(big)
    assert truncated is True
    assert "output truncated" in text


def test_decode_subprocess_output_utf8_bytes():
    from sandbox_mcp.runner import _decode_subprocess_output

    raw = "привет мир — тест".encode("utf-8")
    assert _decode_subprocess_output(raw) == "привет мир — тест"


def test_format_result_extra():
    out = format_result(0, "out", "err", extra="run_id: abc")
    assert "exit_code: 0" in out
    assert "run_id: abc" in out
    assert "stdout:\nout" in out


def test_docker_run_flags_hardening():
    flags = _docker_run_flags()
    assert "--pull" in flags
    assert "never" in flags
    assert "--read-only" in flags
    assert "--cap-drop" in flags
    assert "ALL" in flags
    assert "no-new-privileges" in flags
    assert "--pids-limit" in flags


def test_volume_mounts_layout(bridge_dirs, tmp_path):
    run_dir = tmp_path / "run1"
    from sandbox_mcp.files import prepare_run_layout, prepare_shared_layout

    prepare_run_layout(run_dir)
    prepare_shared_layout(run_dir)

    joined = " ".join(_volume_mounts(run_dir))
    assert "/mnt/data/work:rw" in joined
    assert "/mnt/data/_sandbox:rw" in joined
    assert ":/home/sandbox/.local:rw" in joined
    assert ":/home/sandbox/.cache:rw" in joined
    assert "/mnt/data/input:ro" not in joined
    assert "/mnt/data/output:rw" not in joined


def test_persistent_container_create_argv(bridge_dirs, tmp_path):
    run_dir = tmp_path / "run1"
    from sandbox_mcp.files import prepare_run_layout, prepare_shared_layout

    prepare_run_layout(run_dir)
    prepare_shared_layout(run_dir)

    argv = _docker_create_argv(
        container_name="sandbox-test",
        image="sandbox:latest",
        run_dir=run_dir,
    )
    joined = " ".join(argv)
    assert "-d" in argv
    assert "--rm" in argv
    assert "--label ada.sandbox=1" in joined
    assert "--label ada.sandbox.run_id=run1" in joined
    assert "-u 999:999" in joined
    assert "--entrypoint /bin/sleep" in joined
    assert argv[-1] == "infinity"


def test_container_name_is_run_id_scoped():
    rid = "a" * 32
    assert _container_name(rid) == f"sandbox-{rid}"


def test_ensure_container_reuses_healthy_running_container(monkeypatch, tmp_path):
    calls: list[list[str]] = []

    monkeypatch.setattr("sandbox_mcp.runner._container_running", lambda name: True)
    monkeypatch.setattr("sandbox_mcp.runner._container_health", lambda name: (True, "ok"))
    monkeypatch.setattr("sandbox_mcp.runner._docker", lambda args, **kwargs: calls.append(args))

    err = _ensure_container(container_name="sandbox-test", image="sandbox:latest", run_dir=tmp_path)

    assert err is None
    assert calls == []


def test_verify_image_local_requires_oda_runtime_label(monkeypatch):
    payload = [
        {
            "Id": "sha256:test",
            "Config": {
                "Labels": {
                    "org.aslm.oda.sandbox-runtime": "container-v1",
                },
            },
        },
    ]

    monkeypatch.setattr(
        "sandbox_mcp.runner._docker",
        lambda args, **kwargs: type(
            "Completed",
            (),
            {"returncode": 0, "stdout": json.dumps(payload), "stderr": ""},
        )(),
    )

    assert _verify_image_local("sandbox:latest") is None


def test_verify_image_local_rejects_missing_runtime_label(monkeypatch):
    monkeypatch.setattr(
        "sandbox_mcp.runner._docker",
        lambda args, **kwargs: type(
            "Completed",
            (),
            {"returncode": 0, "stdout": json.dumps([{"Id": "sha256:test", "Config": {"Labels": {}}}]), "stderr": ""},
        )(),
    )

    assert "missing ODA runtime label" in (_verify_image_local("sandbox:latest") or "")


def test_ensure_image_delegates_to_setup_script(monkeypatch):
    calls = {"verify": 0, "run": None}

    def fake_verify(image):
        calls["verify"] += 1
        return "missing" if calls["verify"] == 1 else None

    def fake_run(*args, **kwargs):
        calls["run"] = (args, kwargs)
        return type("Completed", (), {"returncode": 0, "stdout": "ok", "stderr": ""})()

    monkeypatch.setattr("sandbox_mcp.runner._verify_image_local", fake_verify)
    monkeypatch.setattr("sandbox_mcp.runner.subprocess.run", fake_run)

    assert _ensure_image("sandbox:latest") is None
    assert calls["verify"] == 2
    assert calls["run"] is not None


def test_ensure_container_recreates_unhealthy_running_container(monkeypatch, tmp_path):
    calls: list[list[str]] = []
    health = [(False, "bad:tmp"), (True, "ok")]

    def fake_docker(args, **kwargs):
        calls.append(args)
        return type("Completed", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr("sandbox_mcp.runner._container_running", lambda name: True)
    monkeypatch.setattr("sandbox_mcp.runner._container_health", lambda name: health.pop(0))
    monkeypatch.setattr("sandbox_mcp.runner._docker", fake_docker)

    err = _ensure_container(container_name="sandbox-test", image="sandbox:latest", run_dir=tmp_path)

    assert err is None
    assert ["rm", "-f", "sandbox-test"] in calls
    assert any(call[:2] == ["run", "-d"] for call in calls)


def test_doctor_without_active_session(monkeypatch, bridge_dirs):
    from sandbox_mcp import runner

    monkeypatch.setattr(
        "sandbox_mcp.runner._docker",
        lambda args, **kwargs: type("Completed", (), {"returncode": 0, "stdout": "28.0", "stderr": ""})(),
    )
    monkeypatch.setattr("sandbox_mcp.runner._verify_image_local", lambda image: None)
    with runner._SESSION_LOCK:
        runner._ACTIVE_RUN_ID = None
        runner._ACTIVE_RUN_DIR = None
        runner._LAST_ACTIVITY = 0.0

    report = doctor_sandbox()

    assert report["ok"] is True
    assert any(check["name"] == "session" for check in report["checks"])


def test_cleanup_orphan_containers_removes_missing_run_dir(monkeypatch, tmp_path):
    from sandbox_mcp import runner

    removed: list[str] = []
    rid = "b" * 32

    def fake_docker(args, **kwargs):
        if args[:4] == ["ps", "-a", "--filter", "label=ada.sandbox=1"]:
            return type("Completed", (), {"returncode": 0, "stdout": f"sandbox-{rid}\n", "stderr": ""})()
        if args[:3] == ["inspect", "-f", "{{json .Config.Labels}}"]:
            return type("Completed", (), {
                "returncode": 0,
                "stdout": (
                    '{"ada.sandbox.run_id": "'
                    + rid
                    + '", "ada.sandbox.run_dir": "'
                    + str(tmp_path / rid).replace("\\", "\\\\")
                    + '"}'
                ),
                "stderr": "",
            })()
        if args[:3] == ["inspect", "-f", "{{.State.Running}}"]:
            return type("Completed", (), {"returncode": 0, "stdout": "true\n", "stderr": ""})()
        if args[:2] == ["rm", "-f"]:
            removed.append(args[2])
            return type("Completed", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        raise AssertionError(args)

    monkeypatch.setattr("sandbox_mcp.runner._docker", fake_docker)
    with runner._SESSION_LOCK:
        runner._ACTIVE_RUN_ID = None

    assert _cleanup_orphan_containers() == 1
    assert removed == [f"sandbox-{rid}"]


def test_cleanup_orphan_containers_removes_stopped_container(monkeypatch):
    removed: list[str] = []
    rid = "c" * 32

    def fake_docker(args, **kwargs):
        if args[:4] == ["ps", "-a", "--filter", "label=ada.sandbox=1"]:
            return type("Completed", (), {"returncode": 0, "stdout": f"sandbox-{rid}\n", "stderr": ""})()
        if args[:3] == ["inspect", "-f", "{{json .Config.Labels}}"]:
            return type("Completed", (), {
                "returncode": 0,
                "stdout": '{"ada.sandbox.run_id": "' + rid + '"}',
                "stderr": "",
            })()
        if args[:3] == ["inspect", "-f", "{{.State.Running}}"]:
            return type("Completed", (), {"returncode": 0, "stdout": "false\n", "stderr": ""})()
        if args[:2] == ["rm", "-f"]:
            removed.append(args[2])
            return type("Completed", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        raise AssertionError(args)

    monkeypatch.setattr("sandbox_mcp.runner._docker", fake_docker)

    assert _cleanup_orphan_containers() == 1
    assert removed == [f"sandbox-{rid}"]


def test_run_sandbox_missing_image(monkeypatch, bridge_dirs):
    from sandbox_mcp import runner as r

    # Patch _ensure_image to return an error directly (avoids real Docker or
    # setup-sandbox.py being called, which can succeed on dev machines).
    monkeypatch.setattr(r, "_ensure_image", lambda img: f"image not found locally: {img}")
    monkeypatch.setenv("SANDBOX_IMAGE", "sandbox:definitely-not-built-xyz")
    result = r.run_sandbox(SandboxRunRequest(cmd=["true"]))
    assert "exit_code: 1" in result
    assert "image not found" in result


def test_model_facing_tools_include_file_and_image_tools():
    from sandbox_mcp.server import list_tools

    tools = asyncio.run(list_tools())
    assert {tool.name for tool in tools} == {"oda_python", "oda_share_file", "oda_view_image"}
