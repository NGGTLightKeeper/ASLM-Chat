"""HTTP client for the local sandbox daemon."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from sandbox_mcp.config import daemon_config


class SandboxDaemonError(RuntimeError):
    pass


_START_LOCK = threading.Lock()
_DAEMON_PROCESS: subprocess.Popen | None = None


def _mcp_server_root() -> Path:
    """Directory that contains the ``sandbox_mcp`` package (…/mcp_server)."""
    raw = os.environ.get("SANDBOX_MCP_SERVER_ROOT", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return Path(__file__).resolve().parent.parent


def _daemon_python() -> str:
    """Python executable used to launch sandboxd."""
    explicit = os.environ.get("SANDBOX_PYTHON", "").strip()
    return explicit or sys.executable


def _daemon_subprocess_env() -> dict[str, str]:
    """Environment for the sandboxd child process."""
    root = _mcp_server_root()
    env = os.environ.copy()
    sep = os.pathsep
    existing = env.get("PYTHONPATH", "")
    prefix = str(root)
    env["PYTHONPATH"] = prefix if not existing else f"{prefix}{sep}{existing}"
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


def _tail_log_excerpt(log_path: Path, *, max_lines: int = 8) -> str:
    if not log_path.is_file():
        return ""
    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    if not lines:
        return ""
    tail = lines[-max_lines:]
    return "\n".join(tail)


@contextmanager
def _startup_lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        import msvcrt

        with path.open("a+b") as lock_file:
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    with path.open("a+b") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _validate_health(body: dict[str, Any], url: str) -> dict[str, Any]:
    if body.get("service") != "sandboxd":
        raise SandboxDaemonError(f"{url} is not sandboxd (unexpected health response)")
    return body


def daemon_url() -> str | None:
    cfg = daemon_config()
    return cfg.url if cfg.use_daemon else None


def ensure_daemon() -> str | None:
    cfg = daemon_config()
    if not cfg.use_daemon:
        return None
    try:
        _validate_health(health(base_url=cfg.url), cfg.url)
        return cfg.url
    except SandboxDaemonError as exc:
        if not cfg.autostart:
            raise exc

    with _START_LOCK:
        with _startup_lock(cfg.startup_lock_path):
            try:
                _validate_health(health(base_url=cfg.url), cfg.url)
                return cfg.url
            except SandboxDaemonError:
                pass

            cfg.log_path.parent.mkdir(parents=True, exist_ok=True)
            log_file = cfg.log_path.open("a", encoding="utf-8")
            kwargs: dict[str, Any] = {
                "stdout": log_file,
                "stderr": subprocess.STDOUT,
                "stdin": subprocess.DEVNULL,
                "text": True,
            }
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
            mcp_root = _mcp_server_root()
            kwargs["env"] = _daemon_subprocess_env()
            kwargs["cwd"] = str(mcp_root)
            global _DAEMON_PROCESS
            _DAEMON_PROCESS = subprocess.Popen(
                [
                    _daemon_python(),
                    "-m",
                    "sandbox_mcp.daemon",
                    "--host",
                    cfg.host,
                    "--port",
                    str(cfg.port),
                ],
                **kwargs,
            )

            deadline = time.time() + 15
            last_error: Exception | None = None
            while time.time() < deadline:
                if _DAEMON_PROCESS.poll() is not None:
                    try:
                        _validate_health(health(base_url=cfg.url), cfg.url)
                        return cfg.url
                    except SandboxDaemonError:
                        excerpt = _tail_log_excerpt(cfg.log_path)
                        detail = f"\n{excerpt}" if excerpt else ""
                        raise SandboxDaemonError(
                            f"sandbox daemon exited during startup; see log: {cfg.log_path}{detail}"
                        )
                try:
                    _validate_health(health(base_url=cfg.url), cfg.url)
                    return cfg.url
                except SandboxDaemonError as exc:
                    last_error = exc
                    time.sleep(0.25)
            raise SandboxDaemonError(
                f"sandbox daemon did not become healthy at {cfg.url}; "
                f"last error: {last_error}; see log: {cfg.log_path}"
            )


def _request(method: str, path: str, payload: dict[str, Any] | None = None, *, base_url: str | None = None) -> dict[str, Any]:
    cfg = daemon_config()
    url = (base_url or daemon_url() or cfg.url).rstrip("/") + path
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json; charset=utf-8")
    try:
        with urlopen(req, timeout=10 if path in {"/health", "/status"} else None) as response:
            raw = response.read()
    except HTTPError as exc:
        raw = exc.read()
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception:
            raise SandboxDaemonError(f"daemon HTTP {exc.code}") from exc
        raise SandboxDaemonError(str(body.get("error") or f"daemon HTTP {exc.code}")) from exc
    except URLError as exc:
        raise SandboxDaemonError(f"cannot reach sandbox daemon at {url}: {exc.reason}") from exc
    try:
        body = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise SandboxDaemonError("daemon returned invalid JSON") from exc
    if not body.get("ok"):
        raise SandboxDaemonError(str(body.get("error") or "daemon request failed"))
    return body


def health(*, base_url: str | None = None) -> dict[str, Any]:
    return _request("GET", "/health", base_url=base_url)


def status(*, base_url: str | None = None) -> dict[str, Any]:
    return _request("GET", "/status", base_url=base_url)["status"]


def run(
    arguments: dict[str, Any],
    *,
    scope: str | None = None,
    timeout_s: int | None = None,
    base_url: str | None = None,
) -> str:
    if base_url is None:
        ensure_daemon()
    payload = dict(arguments)
    if scope is not None:
        payload["scope"] = scope
    if timeout_s is not None:
        payload["timeout_s"] = timeout_s
    return str(_request("POST", "/run", payload, base_url=base_url)["text"])


def run_python(
    code: str,
    *,
    scope: str | None = None,
    timeout_s: int | None = None,
    base_url: str | None = None,
) -> str:
    if base_url is None:
        ensure_daemon()
    payload: dict[str, Any] = {"code": code}
    if scope is not None:
        payload["scope"] = scope
    if timeout_s is not None:
        payload["timeout_s"] = timeout_s
    return str(_request("POST", "/python", payload, base_url=base_url)["text"])


def pool_status(*, base_url: str | None = None) -> list[dict[str, Any]]:
    if base_url is None:
        ensure_daemon()
    return _request("GET", "/pool/status", base_url=base_url)["pool"]


def pool_evict(scope: str, *, base_url: str | None = None) -> dict[str, Any]:
    if base_url is None:
        ensure_daemon()
    return _request("POST", "/pool/evict", {"scope": scope}, base_url=base_url)


def share(path: object, filename: object | None = None, *, base_url: str | None = None) -> dict[str, Any]:
    if base_url is None:
        ensure_daemon()
    payload = {"path": path}
    if filename is not None:
        payload["filename"] = filename
    return _request("POST", "/share", payload, base_url=base_url)["meta"]


def files(*, base_url: str | None = None) -> dict[str, Any]:
    if base_url is None:
        ensure_daemon()
    return _request("POST", "/files", {}, base_url=base_url)["listing"]


def doctor(*, repair: bool = False, base_url: str | None = None) -> dict[str, Any]:
    if base_url is None:
        ensure_daemon()
    return _request("POST", "/doctor", {"repair": repair}, base_url=base_url)["doctor"]


def session_new(*, base_url: str | None = None) -> dict[str, Any]:
    if base_url is None:
        ensure_daemon()
    return _request("POST", "/session/new", {}, base_url=base_url)["status"]


def session_end(*, base_url: str | None = None) -> dict[str, Any]:
    if base_url is None:
        ensure_daemon()
    return _request("POST", "/session/end", {}, base_url=base_url)["status"]


def cleanup(*, base_url: str | None = None) -> dict[str, Any]:
    if base_url is None:
        ensure_daemon()
    return _request("POST", "/cleanup", {}, base_url=base_url)["status"]
