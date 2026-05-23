"""Integration tests against real Docker + sandbox:latest image."""
from __future__ import annotations

import re
import time
import zipfile
from pathlib import Path

import pytest

from sandbox_mcp import files, runner
from sandbox_mcp.runner import SandboxRunRequest, run_sandbox, share_sandbox_file

from .conftest import docker_available, image_available

pytestmark = pytest.mark.integration

requires_docker = pytest.mark.skipif(
    not docker_available(),
    reason="Docker not available",
)
requires_image = pytest.mark.skipif(
    not image_available(),
    reason="sandbox:latest image not built",
)


def _run_id(text: str) -> str:
    m = re.search(r"run_id: ([a-f0-9]{32})", text)
    assert m, text
    return m.group(1)


@requires_docker
@requires_image
def test_echo(bridge_dirs, monkeypatch):
    monkeypatch.setenv("SANDBOX_IMAGE", "sandbox:latest")
    monkeypatch.setenv("SANDBOX_TIMEOUT", "30")
    out = run_sandbox(SandboxRunRequest(cmd=["bash", "-lc", "echo hello"]))
    assert "exit_code: 0" in out
    assert "hello" in out


@requires_docker
@requires_image
def test_timeout(bridge_dirs, monkeypatch):
    monkeypatch.setenv("SANDBOX_IMAGE", "sandbox:latest")
    monkeypatch.setenv("SANDBOX_TIMEOUT", "5")
    out = run_sandbox(SandboxRunRequest(cmd=["bash", "-lc", "sleep 30; echo NOPE"]))
    assert "exit_code: 124" in out
    assert "NOPE" not in out


@requires_docker
@requires_image
def test_pip_missing_package_reports_pip_error(bridge_dirs, monkeypatch):
    monkeypatch.setenv("SANDBOX_IMAGE", "sandbox:latest")
    out = run_sandbox(
        SandboxRunRequest(cmd=["bash", "-lc", "pip install totally-not-allowed-pkg"])
    )
    assert "exit_code: 0" not in out
    assert "No matching distribution" in out or "Could not find a version" in out


@requires_docker
@requires_image
def test_pip_install_tabulate(bridge_dirs, monkeypatch):
    monkeypatch.setenv("SANDBOX_IMAGE", "sandbox:latest")
    monkeypatch.setenv("SANDBOX_TIMEOUT", "120")
    out = run_sandbox(
        SandboxRunRequest(
            cmd=[
                "bash",
                "-lc",
                "pip install -q tabulate && python3 -c 'import tabulate; print(tabulate.__version__)'",
            ],
        )
    )
    assert "exit_code: 0" in out


def test_long_stdout_truncated(bridge_dirs, monkeypatch):
    monkeypatch.setenv("SANDBOX_IMAGE", "sandbox:latest")
    monkeypatch.setenv("SANDBOX_TIMEOUT", "60")
    monkeypatch.setenv("SANDBOX_OUTPUT_HEAD_BYTES", str(30 * 1024))
    monkeypatch.setenv("SANDBOX_OUTPUT_TAIL_BYTES", str(30 * 1024))

    script = (
        "python3 -c \"import sys;"
        "sys.stdout.write('A'*40000);"
        "sys.stdout.write('\\n<<<MIDDLE>>>\\n');"
        "sys.stdout.write('Z'*40000)\""
    )
    out = run_sandbox(SandboxRunRequest(cmd=["bash", "-lc", script]))
    assert "exit_code: 0" in out
    assert "[output truncated: showed first" in out
    assert "30720 bytes" in out
    assert "<<<MIDDLE>>>" not in out
    assert "AAAA" in out
    assert "ZZZZ" in out
    assert len(out) < 80_000


def test_ffmpeg_available(bridge_dirs, monkeypatch):
    monkeypatch.setenv("SANDBOX_IMAGE", "sandbox:latest")
    out = run_sandbox(
        SandboxRunRequest(
            cmd=["bash", "-lc", "ffmpeg -version | head -n 1"],
        )
    )
    assert "exit_code: 0" in out
    assert "ffmpeg version" in out


@requires_docker
@requires_image
def test_file_bridge(bridge_dirs, monkeypatch):
    monkeypatch.setenv("SANDBOX_IMAGE", "sandbox:latest")
    monkeypatch.setenv("SANDBOX_TIMEOUT", "60")

    body = b"a,b\n1,2\n"
    (bridge_dirs["shared"] / "data.csv").write_bytes(body)

    out = run_sandbox(
        SandboxRunRequest(
            cmd=[
                "bash",
                "-lc",
                "cat /mnt/data/_sandbox/data.csv > /mnt/data/_sandbox/result.txt",
            ],
        )
    )
    assert "exit_code: 0" in out
    meta = share_sandbox_file("result.txt")
    assert meta["path"] == "result.txt"
    assert Path(meta["host_path"]).read_bytes() == body


@requires_docker
@requires_image
@pytest.mark.parametrize("repeat", range(3))
def test_full_file_session_archive_and_trash_flow(bridge_dirs, monkeypatch, repeat):
    monkeypatch.setenv("SANDBOX_IMAGE", "sandbox:latest")
    monkeypatch.setenv("SANDBOX_TIMEOUT", "30")
    monkeypatch.setenv("SANDBOX_SESSION_IDLE_SECONDS", "15")
    monkeypatch.setenv("SANDBOX_ARCHIVE_TTL_SECONDS", "15")
    monkeypatch.setenv("SANDBOX_ARCHIVE_RUNS", "1")

    trashed: list[Path] = []

    def fake_trash(path: Path) -> None:
        trashed.append(path)
        if path.is_dir():
            files.remove_tree(path)
        elif path.exists():
            path.unlink()

    monkeypatch.setattr(runner, "send_to_trash", fake_trash)
    monkeypatch.setattr("sandbox_mcp.files.send_to_trash", fake_trash)

    body = b"value\n41\n"
    (bridge_dirs["shared"] / "data.csv").write_bytes(body)

    out = run_sandbox(
        SandboxRunRequest(
            cmd=[
                "python3",
                "-c",
                (
                    "from pathlib import Path\n"
                    "data = Path('/mnt/data/_sandbox/data.csv').read_text()\n"
                    "Path('/mnt/data/_sandbox/result.txt').write_text(data.replace('41', '42'))\n"
                ),
            ],
        )
    )
    assert "exit_code: 0" in out
    rid = _run_id(out)
    run_dir = bridge_dirs["runs"] / rid
    assert run_dir.is_dir()

    shared_meta = share_sandbox_file("/mnt/data/_sandbox/result.txt")
    assert Path(shared_meta["host_path"]).read_bytes() == b"value\n42\n"

    time.sleep(16)
    runner._cleanup_old_state()

    run_archives = list((bridge_dirs["archive"] / "runs").glob(f"*-{rid}.zip"))
    assert len(run_archives) == 1
    archive = run_archives[0]
    assert trashed == [run_dir]
    assert not run_dir.exists()
    assert bridge_dirs["shared"].exists()
    with zipfile.ZipFile(archive) as zf:
        names = set(zf.namelist())
        assert "work" not in names

    time.sleep(16)
    runner._cleanup_old_state()

    assert archive in trashed
    assert not archive.exists()


@requires_docker
@requires_image
def test_persistent_container_keeps_tmp_but_sweeps_background_processes(bridge_dirs, monkeypatch):
    monkeypatch.setenv("SANDBOX_IMAGE", "sandbox:latest")
    monkeypatch.setenv("SANDBOX_TIMEOUT", "30")

    out1 = run_sandbox(
        SandboxRunRequest(
            cmd=[
                "bash",
                "-lc",
                "echo tmp-ok > /tmp/persistent.txt; sleep 120 & echo background-started",
            ],
        )
    )
    assert "exit_code: 0" in out1
    assert "background-started" in out1

    out2 = run_sandbox(
        SandboxRunRequest(
            cmd=[
                "bash",
                "-lc",
                "cat /tmp/persistent.txt; pgrep -u sandbox -a sleep || true",
            ],
        )
    )
    assert "exit_code: 0" in out2
    assert "tmp-ok" in out2
    assert "sleep 120" not in out2


@requires_docker
@requires_image
def test_model_self_kill_does_not_kill_session_holder(bridge_dirs, monkeypatch):
    monkeypatch.setenv("SANDBOX_IMAGE", "sandbox:latest")
    monkeypatch.setenv("SANDBOX_TIMEOUT", "30")

    out1 = run_sandbox(
        SandboxRunRequest(cmd=["bash", "-lc", "echo alive > /tmp/session-alive; id -u"])
    )
    assert "exit_code: 0" in out1
    rid = _run_id(out1)

    out2 = run_sandbox(
        SandboxRunRequest(
            cmd=[
                "bash",
                "-lc",
                "python3 - <<'PY'\nimport os, signal\nos.kill(-1, signal.SIGTERM)\nPY\n",
            ],
        )
    )
    assert "exit_code: 143" in out2

    out3 = run_sandbox(
        SandboxRunRequest(
            cmd=[
                "bash",
                "-lc",
                "cat /tmp/session-alive; ps -eo uid,comm | grep sleep",
            ],
        )
    )
    assert "exit_code: 0" in out3
    assert _run_id(out3) == rid
    assert "alive" in out3
    assert "999 sleep" in out3


@requires_docker
@requires_image
def test_zombie_processes_are_swept_without_waiting_for_background_stdout(bridge_dirs, monkeypatch):
    monkeypatch.setenv("SANDBOX_IMAGE", "sandbox:latest")
    monkeypatch.setenv("SANDBOX_TIMEOUT", "30")
    script = r"""
python3 - <<'PY' &
import os, time
pid = os.fork()
if pid == 0:
    os._exit(0)
time.sleep(120)
PY
sleep 0.5
ps -eo pid,ppid,uid,stat,comm | grep -E ' Z|python' || true
"""

    out1 = run_sandbox(SandboxRunRequest(cmd=["bash", "-lc", script]))
    assert "exit_code: 0" in out1
    assert " Z" in out1

    out2 = run_sandbox(
        SandboxRunRequest(
            cmd=["bash", "-lc", "ps -eo pid,ppid,uid,stat,comm | grep -E ' Z' || true"],
        )
    )
    assert "exit_code: 0" in out2
    assert " Z" not in out2


@requires_docker
@requires_image
def test_doctor_repairs_killed_session_container(bridge_dirs, monkeypatch):
    monkeypatch.setenv("SANDBOX_IMAGE", "sandbox:latest")
    monkeypatch.setenv("SANDBOX_TIMEOUT", "30")

    out1 = run_sandbox(
        SandboxRunRequest(cmd=["bash", "-lc", "echo repairable > /mnt/data/work/repair.txt"])
    )
    assert "exit_code: 0" in out1
    rid = _run_id(out1)
    container = f"sandbox-{rid}"

    runner._docker(["kill", container], check=False)
    report = runner.doctor_sandbox(repair=False)
    assert report["ok"] is False
    report = runner.doctor_sandbox(repair=True)
    assert report["ok"] is True

    out2 = run_sandbox(SandboxRunRequest(cmd=["bash", "-lc", "cat repair.txt; id -u"]))
    assert "exit_code: 0" in out2
    assert _run_id(out2) == rid
    assert "repairable" in out2
    assert "1000" in out2
