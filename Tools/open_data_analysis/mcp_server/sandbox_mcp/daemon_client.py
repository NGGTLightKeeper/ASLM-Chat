"""HTTP client for the local sandbox daemon."""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from sandbox_mcp.config import daemon_config


class SandboxDaemonError(RuntimeError):
    pass


_START_LOCK = threading.Lock()
_DAEMON_PROCESS: subprocess.Popen | None = None


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
            global _DAEMON_PROCESS
            _DAEMON_PROCESS = subprocess.Popen(
                [
                    sys.executable,
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
                        raise SandboxDaemonError(
                            f"sandbox daemon exited during startup; see log: {cfg.log_path}"
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


def run(arguments: dict[str, Any], *, base_url: str | None = None) -> str:
    if base_url is None:
        ensure_daemon()
    return str(_request("POST", "/run", arguments, base_url=base_url)["text"])


def run_python(code: str, *, base_url: str | None = None) -> str:
    if base_url is None:
        ensure_daemon()
    return str(_request("POST", "/python", {"code": code}, base_url=base_url)["text"])


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
