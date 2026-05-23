"""Run argv inside the sandbox container (subprocess.run semantics)."""
from __future__ import annotations

import logging
import atexit
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from sandbox_mcp.files import (
    FileBridgeError,
    archive_tree,
    cleanup_file_bridge,
    collect_output_files,
    describe_shared_file,
    format_shared_file_changes,
    format_file_bridge_summary,
    list_shared_files,
    prepare_run_layout,
    prepare_shared_layout,
    send_to_trash,
    save_artifacts,
    shared_root,
    shared_file_snapshot,
    stage_input_files,
    validate_filename_list,
    validate_session_id,
)
from sandbox_mcp.output import truncate_output

log = logging.getLogger(__name__)


def _decode_subprocess_output(data: str | bytes | None) -> str:
    """Docker on Windows returns UTF-8 bytes; never decode as cp1251."""
    if not data:
        return ""
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return data


def _container_utf8_env_flags() -> list[str]:
    flags: list[str] = []
    for key, value in (
        ("LANG", "C.UTF-8"),
        ("LC_ALL", "C.UTF-8"),
        ("PYTHONIOENCODING", "utf-8"),
        ("PYTHONUTF8", "1"),
        ("PYTHONUNBUFFERED", "1"),
    ):
        flags.extend(["-e", f"{key}={value}"])
    return flags


DEFAULT_IMAGE = "sandbox:latest"
REQUIRED_IMAGE_LABEL = "org.aslm.oda.sandbox-runtime"
REQUIRED_IMAGE_LABEL_VALUE = "container-v1"
DEFAULT_TIMEOUT = 60
MIN_TIMEOUT = 1
MAX_TIMEOUT = 120
DEFAULT_MEMORY = "2g"
DEFAULT_CPUS = "1"
DEFAULT_PIDS_LIMIT = 256
DEFAULT_MAX_CONCURRENT = 1
DEFAULT_SESSION_IDLE_SECONDS = 30 * 60

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TMP_ROOT = Path(tempfile.gettempdir()) / "ada-sandbox"
DEFAULT_RUNS_ROOT = DEFAULT_TMP_ROOT / "runs"
HOLDER_UID = "999:999"
COMMAND_UID = "1000:1000"
SUPERVISOR_SCRIPT = r"""
import os
import signal
import subprocess
import sys
import tempfile
import time


def _decode(data):
    return (data or b"").decode("utf-8", errors="replace")


def _protected_pids():
    protected = {1, os.getpid(), os.getppid()}
    try:
        current = os.getpid()
        while current > 1:
            stat = open(f"/proc/{current}/stat", "r", encoding="utf-8", errors="replace").read()
            ppid = int(stat.rsplit(")", 1)[1].split()[1])
            if ppid <= 0 or ppid in protected:
                break
            protected.add(ppid)
            current = ppid
    except Exception:
        pass
    return protected


def _uid_for_pid(pid):
    try:
        for line in open(f"/proc/{pid}/status", "r", encoding="utf-8", errors="replace"):
            if line.startswith("Uid:"):
                return int(line.split()[1])
    except Exception:
        return None
    return None


def _sweep_user_processes():
    uid = os.getuid()
    protected = _protected_pids()
    targets = []
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        pid = int(name)
        if pid in protected:
            continue
        if _uid_for_pid(pid) == uid:
            targets.append(pid)
    for sig, delay in ((signal.SIGTERM, 0.25), (signal.SIGKILL, 0.0)):
        for pid in targets:
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                pass
            except PermissionError:
                pass
        if delay:
            time.sleep(delay)


def main():
    try:
        limit = int(os.environ.get("SANDBOX_CMD_TIMEOUT", "60"))
    except ValueError:
        limit = 60
    cmd = sys.argv[1:]
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        print("missing command", file=sys.stderr)
        return 2
    stdout_file = tempfile.NamedTemporaryFile(prefix="sandbox-stdout-", delete=False)
    stderr_file = tempfile.NamedTemporaryFile(prefix="sandbox-stderr-", delete=False)
    stdout_path = stdout_file.name
    stderr_path = stderr_file.name
    proc = subprocess.Popen(cmd, stdout=stdout_file, stderr=stderr_file, start_new_session=True)
    stdout_file.close()
    stderr_file.close()
    timed_out = False
    try:
        code = proc.wait(timeout=limit)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            code = proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            code = proc.wait()
        code = 124
    finally:
        _sweep_user_processes()
    try:
        stdout = open(stdout_path, "rb").read()
    except Exception:
        stdout = b""
    try:
        stderr = open(stderr_path, "rb").read()
    except Exception:
        stderr = b""
    for path in (stdout_path, stderr_path):
        try:
            os.unlink(path)
        except OSError:
            pass
    sys.stdout.write(_decode(stdout))
    sys.stderr.write(_decode(stderr))
    if timed_out:
        print(f"\n[sandbox] killed command after {limit}s timeout", file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
"""

_SESSION_LOCK = threading.RLock()
_ACTIVE_RUN_ID: str | None = None
_ACTIVE_RUN_DIR: Path | None = None
_LAST_ACTIVITY = 0.0


class DockerNotFoundError(Exception):
    pass


@dataclass
class SandboxRunRequest:
    cmd: list[str]
    session_id: str | None = None
    input_files: list[str] = field(default_factory=list)
    output_files: list[str] = field(default_factory=list)


def _env_int(name: str, default: int, *, min_v: int, max_v: int) -> int:
    try:
        value = int(os.environ.get(name, default))
    except ValueError:
        value = default
    return max(min_v, min(max_v, value))


def _runs_root() -> Path:
    raw = os.environ.get("SANDBOX_RUNS_ROOT")
    tmp_raw = os.environ.get("SANDBOX_TMP_ROOT")
    default_root = (Path(tmp_raw).expanduser().resolve() if tmp_raw else DEFAULT_TMP_ROOT) / "runs"
    path = Path(raw).expanduser().resolve() if raw else default_root
    path.mkdir(parents=True, exist_ok=True)
    return path


def _timeout() -> int:
    return _env_int("SANDBOX_TIMEOUT", DEFAULT_TIMEOUT, min_v=MIN_TIMEOUT, max_v=MAX_TIMEOUT)


def _image() -> str:
    return os.environ.get("SANDBOX_IMAGE", DEFAULT_IMAGE)


def _docker_bin() -> str:
    return os.environ.get("SANDBOX_DOCKER", "docker")


def _max_concurrent() -> int:
    return _env_int("SANDBOX_MAX_CONCURRENT", DEFAULT_MAX_CONCURRENT, min_v=1, max_v=4)


def _session_idle_seconds() -> int:
    return _env_int(
        "SANDBOX_SESSION_IDLE_SECONDS",
        DEFAULT_SESSION_IDLE_SECONDS,
        min_v=1,
        max_v=30 * 24 * 60 * 60,
    )


def validate_cmd(cmd: object) -> list[str]:
    if not isinstance(cmd, list) or not cmd:
        raise ValueError("cmd must be a non-empty array of strings")
    if not all(isinstance(x, str) for x in cmd):
        raise ValueError("cmd must contain only strings")
    return cmd


def parse_run_request(arguments: dict) -> SandboxRunRequest:
    cmd = validate_cmd(arguments.get("cmd"))
    session_id = arguments.get("session_id")
    if session_id is not None:
        session_id = validate_session_id(session_id)
    input_files = validate_filename_list(arguments.get("input_files"), label="input_files")
    output_files = validate_filename_list(arguments.get("output_files"), label="output_files")
    if input_files and not session_id:
        raise FileBridgeError("session_id is required when input_files is set (upload first)")
    return SandboxRunRequest(
        cmd=cmd,
        session_id=session_id,
        input_files=input_files,
        output_files=output_files,
    )


def format_result(exit_code: int, stdout: str, stderr: str, *, extra: str = "") -> str:
    parts: list[str] = [f"exit_code: {exit_code}"]
    if extra:
        parts.append(extra.rstrip())
    if stdout:
        parts.append(f"stdout:\n{stdout.rstrip()}")
    if stderr:
        parts.append(f"stderr:\n{stderr.rstrip()}")
    return "\n\n".join(parts)


def _docker(args: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    try:
        kwargs.pop("text", None)
        kwargs.pop("encoding", None)
        completed = subprocess.run(
            [_docker_bin(), *args],
            capture_output=True,
            **kwargs,
        )
    except FileNotFoundError as exc:
        raise DockerNotFoundError(str(exc)) from exc
    return subprocess.CompletedProcess(
        args=completed.args,
        returncode=completed.returncode,
        stdout=_decode_subprocess_output(completed.stdout),
        stderr=_decode_subprocess_output(completed.stderr),
    )


def _docker_error_message() -> str:
    return (
        f"{_docker_bin()} not found. Install Docker and build the image "
        f"(python setup-sandbox.py --source local)"
    )


def _verify_image_local(image: str) -> str | None:
    inspect = _docker(["image", "inspect", image])
    if inspect.returncode != 0:
        return f"image not found locally: {image}"
    try:
        image_data = json.loads(inspect.stdout)
        labels = (image_data[0].get("Config", {}).get("Labels") or {}) if image_data else {}
    except (json.JSONDecodeError, AttributeError, KeyError, TypeError):
        return f"could not validate image metadata: {image}"
    if labels.get(REQUIRED_IMAGE_LABEL) != REQUIRED_IMAGE_LABEL_VALUE:
        return f"image missing ODA runtime label: {image}"
    image_id = str(image_data[0].get("Id") or "").strip() if image_data else ""
    expected = os.environ.get("SANDBOX_EXPECT_IMAGE_ID", "").strip()
    if expected and image_id != expected:
        return f"image id mismatch: expected {expected}, got {image_id}"
    return None


def _ensure_image(image: str) -> str | None:
    if _verify_image_local(image) is None:
        return None

    setup_script = _REPO_ROOT / "setup-sandbox.py"
    if not setup_script.is_file():
        return f"image not ready and setup script not found: {setup_script}"

    env = os.environ.copy()
    env.setdefault("SANDBOX_IMAGE", image)
    result = subprocess.run(
        [sys.executable, str(setup_script)],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )
    if result.returncode != 0:
        details = (result.stderr or result.stdout).strip()
        suffix = f": {details}" if details else ""
        return f"image setup failed (exit {result.returncode}){suffix}"

    return _verify_image_local(image)


def _docker_run_flags() -> list[str]:
    memory = os.environ.get("SANDBOX_MEMORY", DEFAULT_MEMORY)
    cpus = os.environ.get("SANDBOX_CPUS", DEFAULT_CPUS)
    pids = str(_env_int("SANDBOX_PIDS_LIMIT", DEFAULT_PIDS_LIMIT, min_v=8, max_v=512))
    return [
        "--pull",
        "never",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--ipc",
        "private",
        "--cgroupns",
        "private",
        "--pids-limit",
        pids,
        "--memory",
        memory,
        "--memory-swap",
        memory,
        "--cpus",
        cpus,
        "--shm-size",
        "1g",
        "--tmpfs",
        "/tmp:rw,nosuid,size=1g,mode=1777",
        "--tmpfs",
        "/home/sandbox/.config:rw,nosuid,size=256m,uid=1000,gid=1000,mode=700",
    ]


def _volume_mounts(run_dir: Path) -> list[str]:
    work_dir = run_dir / "work"
    local_dir = run_dir / ".local"
    cache_dir = run_dir / ".cache"
    shared_dir = shared_root()
    for path in (local_dir, cache_dir):
        path.mkdir(parents=True, exist_ok=True)
        os.chmod(path, 0o700)
    mounts = [
        "-v",
        f"{work_dir}:/mnt/data/work:rw",
        "-w",
        "/mnt/data/work",
        "-v",
        f"{shared_dir}:/mnt/data/_sandbox:rw",
        "-v",
        f"{local_dir}:/home/sandbox/.local:rw",
        "-v",
        f"{cache_dir}:/home/sandbox/.cache:rw",
    ]
    return mounts


def _stop_container(name: str) -> None:
    _docker(["kill", "-s", "KILL", name], check=False)


def _remove_container(name: str) -> None:
    _docker(["rm", "-f", name], check=False)


def _container_name(run_id: str) -> str:
    return f"sandbox-{run_id}"


def _docker_create_argv(
    *,
    container_name: str,
    image: str,
    run_dir: Path,
) -> list[str]:
    return [
        "run",
        "-d",
        "--rm",
        "--name",
        container_name,
        "--label",
        "ada.sandbox=1",
        "--label",
        f"ada.sandbox.run_id={run_dir.name}",
        "--label",
        f"ada.sandbox.run_dir={run_dir}",
        "--init",
        "--stop-timeout",
        "1",
        "-u",
        HOLDER_UID,
        *_docker_run_flags(),
        *_volume_mounts(run_dir),
        *_container_utf8_env_flags(),
        "--entrypoint",
        "/bin/sleep",
        image,
        "infinity",
    ]


def _container_running(container_name: str) -> bool:
    inspect = _docker(["inspect", "-f", "{{.State.Running}}", container_name])
    return inspect.returncode == 0 and inspect.stdout.strip().lower() == "true"


def _container_health(container_name: str) -> tuple[bool, str]:
    probe = _docker(
        [
            "exec",
            "-u",
            COMMAND_UID,
            "-w",
            "/mnt/data/work",
            container_name,
            "python3",
            "-c",
            (
                "import os, pathlib, sys; "
                "checks = ["
                "('uid', os.getuid() == 1000), "
                "('work', os.access('/mnt/data/work', os.W_OK)), "
                "('shared', os.access('/mnt/data/_sandbox', os.W_OK)), "
                "('tmp', os.access('/tmp', os.W_OK)), "
                "('config', os.access('/home/sandbox/.config', os.W_OK)), "
                "('local', os.access('/home/sandbox/.local', os.W_OK)), "
                "('cache', os.access('/home/sandbox/.cache', os.W_OK))"
                "]; "
                "bad = [name for name, ok in checks if not ok]; "
                "print('ok' if not bad else 'bad:' + ','.join(bad)); "
                "sys.exit(1 if bad else 0)"
            ),
        ]
    )
    message = (probe.stdout or probe.stderr).strip()
    return probe.returncode == 0, message


def _ensure_container(*, container_name: str, image: str, run_dir: Path) -> str | None:
    if _container_running(container_name):
        healthy, message = _container_health(container_name)
        if healthy:
            return None
        log.warning("sandbox container unhealthy; recreating", extra={"container": container_name, "health": message})
        _remove_container(container_name)
    _remove_container(container_name)
    argv = _docker_create_argv(container_name=container_name, image=image, run_dir=run_dir)
    created = _docker(argv)
    if created.returncode != 0:
        return created.stderr or created.stdout or "failed to start sandbox container"
    healthy, message = _container_health(container_name)
    if not healthy:
        _remove_container(container_name)
        return f"sandbox container started but failed health check: {message}"
    return None


def _doctor_check(name: str, ok: bool, message: str = "", **details) -> dict[str, object]:
    result: dict[str, object] = {"name": name, "ok": ok}
    if message:
        result["message"] = message
    result.update(details)
    return result


def doctor_sandbox(*, repair: bool = False) -> dict[str, object]:
    checks: list[dict[str, object]] = []
    docker = _docker(["version", "--format", "{{.Server.Version}}"])
    docker_ok = docker.returncode == 0
    checks.append(_doctor_check("docker", docker_ok, (docker.stdout or docker.stderr).strip()))
    image = _image()
    image_ok = False
    if docker_ok:
        image_err = _verify_image_local(image)
        image_ok = image_err is None
        checks.append(_doctor_check("image", image_ok, image_err or image, image=image))
    else:
        checks.append(_doctor_check("image", False, "skipped: docker unavailable", image=image))

    with _SESSION_LOCK:
        run_id = _ACTIVE_RUN_ID
        run_dir = _ACTIVE_RUN_DIR
    if not run_id or not run_dir:
        checks.append(_doctor_check("session", True, "no active session"))
        return {"ok": all(bool(check["ok"]) for check in checks), "checks": checks}

    run_dir_ok = run_dir.is_dir()
    checks.append(_doctor_check("run_dir", run_dir_ok, str(run_dir), run_id=run_id))
    container_name = _container_name(run_id)
    if not docker_ok or not image_ok or not run_dir_ok:
        checks.append(_doctor_check("container", False, "skipped: prerequisites failed", container=container_name))
        return {"ok": all(bool(check["ok"]) for check in checks), "checks": checks, "run_id": run_id}

    running = _container_running(container_name)
    if not running and repair:
        err = _ensure_container(container_name=container_name, image=image, run_dir=run_dir)
        running = err is None and _container_running(container_name)
        if err:
            checks.append(_doctor_check("repair", False, err, container=container_name))
    checks.append(_doctor_check("container_running", running, container_name, container=container_name))

    if running:
        healthy, message = _container_health(container_name)
        if not healthy and repair:
            err = _ensure_container(container_name=container_name, image=image, run_dir=run_dir)
            healthy = err is None
            message = "recreated" if healthy else err or message
        checks.append(_doctor_check("container_exec", healthy, message, container=container_name))
    else:
        checks.append(_doctor_check("container_exec", False, "skipped: container is not running", container=container_name))

    return {
        "ok": all(bool(check["ok"]) for check in checks),
        "checks": checks,
        "run_id": run_id,
        "run_dir": str(run_dir),
        "container": container_name,
    }


def _exec_container_sync(
    *,
    container_name: str,
    cmd: list[str],
    limit: int,
) -> tuple[int, str, str, bool]:
    """Run one command inside the persistent session container via supervisor."""
    supervisor = [
        "exec",
        "-u",
        COMMAND_UID,
        "-w",
        "/mnt/data/work",
        "-e",
        f"SANDBOX_CMD_TIMEOUT={limit}",
        container_name,
        "python3",
        "-c",
        SUPERVISOR_SCRIPT,
        "--",
        *cmd,
    ]
    timed_out = False
    try:
        completed = subprocess.run(
            [_docker_bin(), *supervisor],
            capture_output=True,
            timeout=limit + 10,
        )
        stdout = _decode_subprocess_output(completed.stdout)
        stderr = _decode_subprocess_output(completed.stderr)
        exit_code = completed.returncode
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        _stop_container(container_name)
        _remove_container(container_name)
        stdout = _decode_subprocess_output(exc.stdout)
        stderr = _decode_subprocess_output(exc.stderr)
        exit_code = 124
    except FileNotFoundError as exc:
        raise DockerNotFoundError(str(exc)) from exc
    stdout, _ = truncate_output(stdout)
    stderr, _ = truncate_output(stderr)
    return exit_code, stdout, stderr, timed_out


def _make_run_dir() -> Path:
    run_dir = _runs_root() / uuid.uuid4().hex
    run_dir.mkdir(parents=True, exist_ok=False)
    os.chmod(run_dir, 0o700)
    return run_dir


def _cleanup_run_dir(run_dir: Path) -> None:
    if os.environ.get("SANDBOX_KEEP_RUN_DIR", "").strip() in ("1", "true", "yes"):
        return
    if os.environ.get("SANDBOX_ARCHIVE_RUNS", "0").strip().lower() in {"1", "true", "yes"}:
        archive_tree(run_dir, "runs")
    if re.fullmatch(r"[a-f0-9]{32}", run_dir.name):
        _remove_container(_container_name(run_dir.name))
    try:
        send_to_trash(run_dir)
    except OSError:
        pass


def _touch_active_session() -> None:
    global _LAST_ACTIVITY
    with _SESSION_LOCK:
        _LAST_ACTIVITY = time.time()


def _active_session_expired(now: float | None = None) -> bool:
    with _SESSION_LOCK:
        if not _ACTIVE_RUN_DIR or not _ACTIVE_RUN_ID:
            return False
        if not _ACTIVE_RUN_DIR.exists():
            return True
        current = time.time() if now is None else now
        return current - _LAST_ACTIVITY >= _session_idle_seconds()


def _end_active_session() -> None:
    global _ACTIVE_RUN_ID, _ACTIVE_RUN_DIR, _LAST_ACTIVITY
    with _SESSION_LOCK:
        run_dir = _ACTIVE_RUN_DIR
        _ACTIVE_RUN_ID = None
        _ACTIVE_RUN_DIR = None
        _LAST_ACTIVITY = 0.0
    if run_dir:
        _cleanup_run_dir(run_dir)


def _get_active_run_dir() -> tuple[str, Path]:
    global _ACTIVE_RUN_ID, _ACTIVE_RUN_DIR, _LAST_ACTIVITY
    now = time.time()
    with _SESSION_LOCK:
        if _active_session_expired(now):
            run_dir = _ACTIVE_RUN_DIR
            _ACTIVE_RUN_ID = None
            _ACTIVE_RUN_DIR = None
            _LAST_ACTIVITY = 0.0
        else:
            run_dir = None

    if run_dir:
        _cleanup_run_dir(run_dir)

    with _SESSION_LOCK:
        if _ACTIVE_RUN_ID and _ACTIVE_RUN_DIR and _ACTIVE_RUN_DIR.exists():
            _LAST_ACTIVITY = time.time()
            return _ACTIVE_RUN_ID, _ACTIVE_RUN_DIR

        run_dir = _make_run_dir()
        _ACTIVE_RUN_ID = run_dir.name
        _ACTIVE_RUN_DIR = run_dir
        _LAST_ACTIVITY = time.time()
        return _ACTIVE_RUN_ID, run_dir


def _cleanup_old_run_dirs() -> int:
    now = time.time()
    removed = 0
    root = _runs_root()
    with _SESSION_LOCK:
        active = _ACTIVE_RUN_ID
    for child in root.iterdir():
        if not child.is_dir() or not re.fullmatch(r"[a-f0-9]{32}", child.name):
            continue
        if active and child.name == active:
            continue
        try:
            age = now - child.stat().st_mtime
        except OSError:
            continue
        if age < _session_idle_seconds():
            continue
        _cleanup_run_dir(child)
        removed += 1
    return removed


def _container_label(container_name: str, label: str) -> str:
    inspected = _docker(
        [
            "inspect",
            "-f",
            "{{json .Config.Labels}}",
            container_name,
        ]
    )
    if inspected.returncode != 0:
        return ""
    try:
        labels = json.loads(inspected.stdout or "{}")
    except json.JSONDecodeError:
        return ""
    if not isinstance(labels, dict):
        return ""
    value = labels.get(label)
    return value if isinstance(value, str) else ""


def _cleanup_orphan_containers() -> int:
    listed = _docker(["ps", "-a", "--filter", "label=ada.sandbox=1", "--format", "{{.Names}}"])
    if listed.returncode != 0:
        return 0
    with _SESSION_LOCK:
        active = _ACTIVE_RUN_ID
    now = time.time()
    removed = 0
    for name in listed.stdout.splitlines():
        name = name.strip()
        if not name:
            continue
        rid = _container_label(name, "ada.sandbox.run_id")
        if active and rid == active:
            continue
        if not _container_running(name):
            _remove_container(name)
            removed += 1
            continue
        run_dir_raw = _container_label(name, "ada.sandbox.run_dir")
        run_dir = Path(run_dir_raw) if run_dir_raw else None
        should_remove = False
        if not rid or not re.fullmatch(r"[a-f0-9]{32}", rid):
            should_remove = True
        elif run_dir is None or not run_dir.exists():
            should_remove = True
        else:
            try:
                should_remove = now - run_dir.stat().st_mtime >= _session_idle_seconds()
            except OSError:
                should_remove = True
        if should_remove:
            _remove_container(name)
            removed += 1
    return removed


def _cleanup_active_session_at_exit() -> None:
    try:
        _end_active_session()
    except Exception:
        pass


atexit.register(_cleanup_active_session_at_exit)


def _cleanup_old_state() -> None:
    if _active_session_expired():
        _end_active_session()
    _cleanup_old_run_dirs()
    _cleanup_orphan_containers()
    cleanup_file_bridge()


def run_sandbox(request: SandboxRunRequest) -> str:
    _cleanup_old_state()
    shared_before = shared_file_snapshot()
    image = _image()
    try:
        if err := _ensure_image(image):
            return format_result(1, "", err)
    except DockerNotFoundError:
        return format_result(1, "", _docker_error_message())

    limit = _timeout()
    run_id, run_dir = _get_active_run_dir()
    container_name = _container_name(run_id)

    try:
        prepare_run_layout(run_dir)
        prepare_shared_layout(run_dir)
        staged_inputs: list[str] = []
        if request.input_files:
            staged_inputs = stage_input_files(
                run_dir, request.session_id or "", request.input_files
            )

        log.info("sandbox used network", extra={"run_id": run_id, "image": image})
        if err := _ensure_container(container_name=container_name, image=image, run_dir=run_dir):
            return format_result(1, "", err)
        exit_code, stdout, stderr, timed_out = _exec_container_sync(
            container_name=container_name,
            cmd=request.cmd,
            limit=limit,
        )
    except (DockerNotFoundError, FileBridgeError) as exc:
        return format_result(1, "", str(exc))

    outputs: dict[str, bytes] = {}
    bridge_err = ""
    if request.output_files and exit_code == 0 and not timed_out:
        try:
            outputs = collect_output_files(run_dir, request.output_files)
        except FileBridgeError as exc:
            bridge_err = str(exc)
            exit_code = 1
    elif request.output_files and exit_code != 0:
        bridge_err = "outputs not collected: command failed or timed out"

    if outputs:
        save_artifacts(
            run_id,
            exit_code=exit_code,
            session_id=request.session_id,
            inputs=staged_inputs,
            outputs=outputs,
            stdout=stdout,
            stderr=stderr,
            timed_out=timed_out,
        )

    _touch_active_session()

    extra = f"run_id: {run_id}\nshared_dir: /mnt/data/_sandbox"
    if outputs:
        bridge_summary = format_file_bridge_summary(
            run_id=run_id,
            session_id=request.session_id,
            inputs=staged_inputs,
            outputs=list(outputs.keys()),
        )
        extra = f"{extra}\n{bridge_summary}"
    if bridge_err:
        extra = f"{extra.rstrip()}\nbridge_error: {bridge_err}".strip()
    shared_after = list_shared_files()
    shared_changes = format_shared_file_changes(shared_before, shared_after)
    if shared_changes:
        extra = f"{extra.rstrip()}\n{shared_changes}".strip()

    if timed_out:
        return format_result(
            124,
            stdout,
            (stderr + f"\n[sandbox] killed container after {limit}s timeout").strip(),
            extra=extra,
        )

    return format_result(exit_code, stdout, stderr, extra=extra)


def max_concurrent() -> int:
    return _max_concurrent()


def share_sandbox_file(path: object, filename: object | None = None) -> dict:
    _cleanup_old_state()
    with _SESSION_LOCK:
        run_dir = _ACTIVE_RUN_DIR
    if not run_dir or not run_dir.exists():
        raise FileBridgeError("no active sandbox session; run oda_python first")
    result = describe_shared_file(path, filename)
    _touch_active_session()
    return result


def list_sandbox_files() -> dict:
    _cleanup_old_state()
    result = list_shared_files()
    _touch_active_session()
    return result
