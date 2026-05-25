"""Per-scope Docker container pool for the ODA sandbox.

One long-lived container is kept per *scope* (typically ``chat_id``).
The container runs ``sleep infinity`` as holder uid 999, and all user
commands are executed via ``docker exec -u 1000`` + supervisor script.

Key differences from the legacy ``runner.py`` session model:
- Scope is identified by an arbitrary string (chat_id) rather than a
  per-process UUID run-dir.
- On ``docker exec`` timeout the *command* is killed but the container is
  **not** removed — only the janitor evicts containers by idle time.
- pip / .local / .cache are persisted across calls on the same scope via
  host bind-mounts under ``{tmp_root}/pool/<scope>/``.
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from sandbox_mcp.files import shared_root, tmp_root
from sandbox_mcp.output import truncate_output

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants (overridable via env)
# ---------------------------------------------------------------------------

DEFAULT_POOL_IMAGE = "sandbox:latest"
REQUIRED_IMAGE_LABEL = "org.aslm.oda.sandbox-runtime"
REQUIRED_IMAGE_LABEL_VALUE = "container-v1"

DEFAULT_POOL_TIMEOUT = 300          # per-command default seconds
MIN_POOL_TIMEOUT = 1
MAX_POOL_TIMEOUT = 1800

DEFAULT_POOL_IDLE_SECONDS = 24 * 60 * 60   # keep warm container 24 h
DEFAULT_POOL_MEMORY = "2g"
DEFAULT_POOL_CPUS = "1"
DEFAULT_POOL_PIDS_LIMIT = 256

HOLDER_UID = "999:999"
COMMAND_UID = "1000:1000"

# Safe name for container: alphanumeric + dash only, max 60 chars.
_SCOPE_SAFE_RE = re.compile(r"[^a-z0-9-]")
_CONTAINER_PREFIX = "oda-chat-"

# Supervisor script injected via ``docker exec python3 -c <script>``
# Identical logic to runner.py supervisor but reads SANDBOX_CMD_TIMEOUT from env.
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
        limit = int(os.environ.get("SANDBOX_CMD_TIMEOUT", "300"))
    except ValueError:
        limit = 300
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


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

class PoolError(RuntimeError):
    pass


class DockerNotFoundError(PoolError):
    pass


def _decode(data: str | bytes | None) -> str:
    if not data:
        return ""
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return data


def _env_int(name: str, default: int, *, min_v: int, max_v: int) -> int:
    try:
        value = int(os.environ.get(name, default))
    except ValueError:
        value = default
    return max(min_v, min(max_v, value))


def _docker_bin() -> str:
    return os.environ.get("SANDBOX_DOCKER", "docker")


def _image() -> str:
    return os.environ.get("SANDBOX_IMAGE", DEFAULT_POOL_IMAGE)


def _pool_idle_seconds() -> int:
    return _env_int(
        "SANDBOX_POOL_IDLE_SECONDS",
        DEFAULT_POOL_IDLE_SECONDS,
        min_v=60,
        max_v=30 * 24 * 60 * 60,
    )


def _command_timeout(requested: int | None) -> int:
    default = _env_int("SANDBOX_TIMEOUT", DEFAULT_POOL_TIMEOUT, min_v=MIN_POOL_TIMEOUT, max_v=MAX_POOL_TIMEOUT)
    if requested is None:
        return default
    return max(MIN_POOL_TIMEOUT, min(MAX_POOL_TIMEOUT, requested))


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
        stdout=_decode(completed.stdout),
        stderr=_decode(completed.stderr),
    )


def _pool_root() -> Path:
    raw = os.environ.get("SANDBOX_POOL_ROOT", "").strip()
    path = Path(raw).expanduser().resolve() if raw else tmp_root() / "pool"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _scope_dir(scope: str) -> Path:
    """Return per-scope host directory for work/.local/.cache."""
    safe = _sanitize_scope(scope)
    path = _pool_root() / safe
    path.mkdir(parents=True, exist_ok=True)
    return path


def _sanitize_scope(scope: str) -> str:
    """Lower-case, strip non-alphanumeric/dash chars, cap at 60 chars."""
    s = _SCOPE_SAFE_RE.sub("-", scope.lower()).strip("-")
    return (s or "default")[:60]


def _container_name(scope: str) -> str:
    return f"{_CONTAINER_PREFIX}{_sanitize_scope(scope)}"


def _docker_run_flags() -> list[str]:
    memory = os.environ.get("SANDBOX_MEMORY", DEFAULT_POOL_MEMORY)
    cpus = os.environ.get("SANDBOX_CPUS", DEFAULT_POOL_CPUS)
    pids = str(_env_int("SANDBOX_PIDS_LIMIT", DEFAULT_POOL_PIDS_LIMIT, min_v=8, max_v=512))
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


def _utf8_env_flags() -> list[str]:
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


def _volume_mounts(scope_dir: Path) -> list[str]:
    work_dir = scope_dir / "work"
    local_dir = scope_dir / ".local"
    cache_dir = scope_dir / ".cache"
    shared_dir = shared_root()
    for path in (work_dir, local_dir, cache_dir):
        path.mkdir(parents=True, exist_ok=True)
        os.chmod(path, 0o700)
    return [
        "-v", f"{work_dir}:/mnt/data/work:rw",
        "-w", "/mnt/data/work",
        "-v", f"{shared_dir}:/mnt/data/_sandbox:rw",
        "-v", f"{local_dir}:/home/sandbox/.local:rw",
        "-v", f"{cache_dir}:/home/sandbox/.cache:rw",
    ]


def _create_container_argv(container_name: str, scope: str, image: str) -> list[str]:
    scope_dir = _scope_dir(scope)
    return [
        "run",
        "-d",
        # No --rm: we manage lifecycle explicitly via janitor / evict
        "--name", container_name,
        "--label", "ada.pool=1",
        "--label", f"ada.pool.scope={_sanitize_scope(scope)}",
        "--label", f"ada.pool.last_used={int(time.time())}",
        "--init",
        "--stop-timeout", "1",
        "-u", HOLDER_UID,
        *_docker_run_flags(),
        *_volume_mounts(scope_dir),
        *_utf8_env_flags(),
        "--entrypoint", "/bin/sleep",
        image,
        "infinity",
    ]


def _update_last_used_label(container_name: str) -> None:
    """Best-effort: update last_used timestamp on container label."""
    _docker(["label", container_name, f"ada.pool.last_used={int(time.time())}"], check=False)


def _container_running(name: str) -> bool:
    r = _docker(["inspect", "-f", "{{.State.Running}}", name])
    return r.returncode == 0 and r.stdout.strip().lower() == "true"


def _container_label(name: str, label: str) -> str:
    r = _docker(["inspect", "-f", "{{json .Config.Labels}}", name])
    if r.returncode != 0:
        return ""
    try:
        labels = json.loads(r.stdout or "{}")
    except json.JSONDecodeError:
        return ""
    v = labels.get(label)
    return v if isinstance(v, str) else ""


def _remove_container(name: str) -> None:
    _docker(["rm", "-f", name])


def _health_check(container_name: str) -> tuple[bool, str]:
    probe = _docker(
        [
            "exec",
            "-u", COMMAND_UID,
            "-w", "/mnt/data/work",
            container_name,
            "python3", "-c",
            (
                "import os, sys; "
                "checks = ["
                "('uid', os.getuid() == 1000), "
                "('work', os.access('/mnt/data/work', os.W_OK)), "
                "('shared', os.access('/mnt/data/_sandbox', os.W_OK)), "
                "('tmp', os.access('/tmp', os.W_OK)), "
                "('local', os.access('/home/sandbox/.local', os.W_OK)), "
                "('cache', os.access('/home/sandbox/.cache', os.W_OK))"
                "]; "
                "bad = [n for n, ok in checks if not ok]; "
                "print('ok' if not bad else 'bad:' + ','.join(bad)); "
                "sys.exit(1 if bad else 0)"
            ),
        ]
    )
    msg = (probe.stdout or probe.stderr).strip()
    return probe.returncode == 0, msg


def _verify_image(image: str) -> str | None:
    """Return None if image is valid locally, else error string."""
    r = _docker(["image", "inspect", image])
    if r.returncode != 0:
        return f"image not found locally: {image}"
    try:
        data = json.loads(r.stdout)
        labels = (data[0].get("Config", {}).get("Labels") or {}) if data else {}
    except (json.JSONDecodeError, AttributeError, KeyError, TypeError):
        return f"could not validate image metadata: {image}"
    if labels.get(REQUIRED_IMAGE_LABEL) != REQUIRED_IMAGE_LABEL_VALUE:
        return f"image missing ODA runtime label: {image}"
    return None


# ---------------------------------------------------------------------------
# Pool state
# ---------------------------------------------------------------------------

@dataclass
class _PoolEntry:
    container_name: str
    scope: str
    last_used: float = field(default_factory=time.time)

    def touch(self) -> None:
        self.last_used = time.time()


_POOL_LOCK = threading.RLock()
_POOL: dict[str, _PoolEntry] = {}   # sanitized_scope -> entry
_JANITOR_STARTED = False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def acquire(scope: str, *, image: str | None = None) -> str:
    """Ensure a running container for *scope* and return its name.

    If the container already exists and is healthy, reuse it.
    If it is absent or unhealthy, create a fresh one.
    Raises ``PoolError`` on failure.
    """
    img = image or _image()
    err = _verify_image(img)
    if err:
        raise PoolError(err)

    safe = _sanitize_scope(scope)
    name = _container_name(scope)

    with _POOL_LOCK:
        entry = _POOL.get(safe)
        if entry is not None:
            if _container_running(entry.container_name):
                healthy, msg = _health_check(entry.container_name)
                if healthy:
                    entry.touch()
                    log.debug("pool: reusing container %s for scope %s", name, safe)
                    return entry.container_name
                log.warning("pool: container %s unhealthy (%s); recreating", name, msg)
                _remove_container(entry.container_name)
            else:
                log.warning("pool: container %s stopped; recreating", name)
                _remove_container(entry.container_name)
            del _POOL[safe]

        # Check if a container with this name already exists in Docker
        # (e.g. daemon restarted but container survived).
        if _container_running(name):
            healthy, msg = _health_check(name)
            if healthy:
                entry = _PoolEntry(container_name=name, scope=scope)
                _POOL[safe] = entry
                log.info("pool: reattached existing container %s scope=%s", name, safe)
                return name
            log.warning("pool: found stale container %s (%s); removing", name, msg)
            _remove_container(name)

        # Create new container.
        argv = _create_container_argv(name, scope, img)
        result = _docker(argv)
        if result.returncode != 0:
            raise PoolError(
                f"failed to create container {name}: "
                f"{result.stderr or result.stdout or 'unknown error'}"
            )

        healthy, msg = _health_check(name)
        if not healthy:
            _remove_container(name)
            raise PoolError(f"container {name} failed health check: {msg}")

        entry = _PoolEntry(container_name=name, scope=scope)
        _POOL[safe] = entry
        log.info("pool: created container %s scope=%s image=%s", name, safe, img)
        return name


def exec_in_pool(
    scope: str,
    cmd: list[str],
    *,
    timeout_s: int | None = None,
) -> tuple[int, str, str, bool]:
    """Execute *cmd* in the pool container for *scope*.

    Returns ``(exit_code, stdout, stderr, timed_out)``.

    On timeout the command subprocess is killed via the supervisor, but the
    **container is NOT removed** — only the running command dies.
    The container remains available for the next call on the same scope.
    """
    limit = _command_timeout(timeout_s)
    container_name = acquire(scope)

    supervisor_argv = [
        "exec",
        "-u", COMMAND_UID,
        "-w", "/mnt/data/work",
        "-e", f"SANDBOX_CMD_TIMEOUT={limit}",
        container_name,
        "python3", "-c", SUPERVISOR_SCRIPT,
        "--", *cmd,
    ]

    timed_out = False
    # outer wall-clock: limit + overhead; supervisor handles inner kill.
    outer_timeout = limit + 15
    try:
        completed = subprocess.run(
            [_docker_bin(), *supervisor_argv],
            capture_output=True,
            timeout=outer_timeout,
        )
        stdout = _decode(completed.stdout)
        stderr = _decode(completed.stderr)
        exit_code = completed.returncode
    except FileNotFoundError as exc:
        raise DockerNotFoundError(str(exc)) from exc
    except subprocess.TimeoutExpired as exc:
        # Outer wall-clock expired — the docker exec call itself hung.
        # Kill just the docker exec client process; the container stays up.
        timed_out = True
        stdout = _decode(exc.stdout)
        stderr = _decode(exc.stderr)
        exit_code = 124
        log.warning(
            "pool: outer timeout on exec for scope=%s container=%s; "
            "container preserved",
            _sanitize_scope(scope),
            container_name,
        )

    stdout, _ = truncate_output(stdout)
    stderr, _ = truncate_output(stderr)

    # Touch last_used after successful exec.
    with _POOL_LOCK:
        entry = _POOL.get(_sanitize_scope(scope))
        if entry:
            entry.touch()

    return exit_code, stdout, stderr, timed_out


def evict(scope: str) -> bool:
    """Stop and remove the container for *scope*.  Returns True if anything removed."""
    safe = _sanitize_scope(scope)
    name = _container_name(scope)
    with _POOL_LOCK:
        _POOL.pop(safe, None)
    if _container_running(name):
        _remove_container(name)
        log.info("pool: evicted container %s scope=%s", name, safe)
        return True
    return False


def pool_status() -> list[dict]:
    """Return a snapshot of the current pool state."""
    with _POOL_LOCK:
        entries = list(_POOL.values())
    return [
        {
            "scope": e.scope,
            "container": e.container_name,
            "last_used": e.last_used,
            "running": _container_running(e.container_name),
        }
        for e in entries
    ]


# ---------------------------------------------------------------------------
# Janitor
# ---------------------------------------------------------------------------

def _janitor_once() -> int:
    """Evict containers idle longer than SANDBOX_POOL_IDLE_SECONDS."""
    idle = _pool_idle_seconds()
    now = time.time()
    evicted = 0

    with _POOL_LOCK:
        stale_scopes = [
            safe for safe, entry in _POOL.items()
            if now - entry.last_used >= idle
        ]

    for safe in stale_scopes:
        with _POOL_LOCK:
            entry = _POOL.get(safe)
        if entry is None:
            continue
        age = now - entry.last_used
        if age < idle:
            continue
        log.info(
            "pool: janitor evicting %s scope=%s idle=%.0fs",
            entry.container_name,
            safe,
            age,
        )
        with _POOL_LOCK:
            _POOL.pop(safe, None)
        _remove_container(entry.container_name)
        evicted += 1

    # Also sweep Docker for orphaned pool containers not tracked in _POOL.
    _sweep_docker_orphans(now, idle)
    return evicted


def _sweep_docker_orphans(now: float, idle: float) -> None:
    """Remove pool containers in Docker that we no longer track."""
    listed = _docker(["ps", "-a", "--filter", "label=ada.pool=1", "--format", "{{.Names}}"])
    if listed.returncode != 0:
        return
    with _POOL_LOCK:
        tracked = {e.container_name for e in _POOL.values()}

    for name in listed.stdout.splitlines():
        name = name.strip()
        if not name or name in tracked:
            continue
        # Check last_used label.
        raw_ts = _container_label(name, "ada.pool.last_used")
        try:
            last_used = float(raw_ts)
        except (ValueError, TypeError):
            last_used = 0.0
        age = now - last_used
        if age >= idle or not _container_running(name):
            log.info("pool: janitor removing orphan container %s age=%.0fs", name, age)
            _remove_container(name)


def _janitor_loop(interval: int) -> None:
    while True:
        time.sleep(interval)
        try:
            _janitor_once()
        except Exception:
            log.exception("pool: janitor error")


def start_janitor(interval_seconds: int = 5 * 60) -> None:
    global _JANITOR_STARTED
    with _POOL_LOCK:
        if _JANITOR_STARTED:
            return
        _JANITOR_STARTED = True
    t = threading.Thread(
        target=_janitor_loop,
        args=(interval_seconds,),
        name="oda-pool-janitor",
        daemon=True,
    )
    t.start()
    log.info("pool: janitor started interval=%ds", interval_seconds)


# ---------------------------------------------------------------------------
# Migration helper: evict old-style ada.sandbox containers
# ---------------------------------------------------------------------------

def evict_legacy_sandbox_containers() -> int:
    """Remove containers labelled ``ada.sandbox=1`` (old runner.py scheme)."""
    listed = _docker(["ps", "-a", "--filter", "label=ada.sandbox=1", "--format", "{{.Names}}"])
    if listed.returncode != 0:
        return 0
    removed = 0
    for name in listed.stdout.splitlines():
        name = name.strip()
        if not name:
            continue
        log.info("pool: removing legacy sandbox container %s", name)
        _remove_container(name)
        removed += 1
    if removed:
        log.info("pool: removed %d legacy sandbox containers", removed)
    return removed
