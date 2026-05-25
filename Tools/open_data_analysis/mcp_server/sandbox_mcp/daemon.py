"""Local sandbox daemon: per-scope Docker container pool."""
from __future__ import annotations

import argparse
import json
import logging
import os
import platform
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from sandbox_mcp.config import DEFAULT_DAEMON_HOST, DEFAULT_DAEMON_PORT, daemon_config
from sandbox_mcp.files import FileBridgeError
from sandbox_mcp import container_pool
from sandbox_mcp import runner

log = logging.getLogger(__name__)
SERVICE_NAME = "sandboxd"
SERVICE_VERSION = "0.2"

# Fallback scope for callers that don't pass one (legacy compat).
_DEFAULT_SCOPE = "default"

# Semaphore applied per scope is handled inside pool; this global one
# limits total concurrent docker exec calls across all scopes.
_RUN_SEMAPHORE = threading.BoundedSemaphore(runner.max_concurrent())


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _configure_logging() -> None:
    cfg = daemon_config()
    cfg.log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[
            logging.FileHandler(cfg.log_path, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


# ---------------------------------------------------------------------------
# State: pool scopes persisted to disk so daemon restart can reattach.
# ---------------------------------------------------------------------------

def _state_path() -> Path:
    path = daemon_config().state_path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _status() -> dict[str, Any]:
    """Return a lightweight status dict for the daemon."""
    return {
        "pool": container_pool.pool_status(),
        "state_path": str(_state_path()),
    }


def _save_state() -> None:
    """Persist current pool state so containers can be reattached on restart."""
    path = _state_path()
    with container_pool._POOL_LOCK:
        scopes = {
            safe: {
                "container": e.container_name,
                "scope": e.scope,
                "last_used": e.last_used,
            }
            for safe, e in container_pool._POOL.items()
        }
    payload = {"scopes": scopes}
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)
    log.debug("saved state scopes=%d path=%s", len(scopes), path)


def _restore_state() -> None:
    """Reattach still-running containers from previous daemon run."""
    path = _state_path()
    if not path.is_file():
        log.info("no state file path=%s", path)
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("state file unreadable: %s; ignoring", exc)
        return
    if not isinstance(data, dict):
        log.warning("state file malformed; ignoring")
        return
    scopes = data.get("scopes")
    if not isinstance(scopes, dict):
        return
    reattached = 0
    for safe, entry in scopes.items():
        if not isinstance(entry, dict):
            continue
        scope = entry.get("scope") or safe
        container = entry.get("container")
        last_used = entry.get("last_used", 0.0)
        if not container:
            continue
        if not container_pool._container_running(container):
            log.info("state: container %s no longer running; skipping", container)
            continue
        healthy, msg = container_pool._health_check(container)
        if not healthy:
            log.warning("state: container %s unhealthy (%s); skipping", container, msg)
            container_pool._remove_container(container)
            continue
        with container_pool._POOL_LOCK:
            entry_obj = container_pool._PoolEntry(
                container_name=container,
                scope=scope,
                last_used=float(last_used),
            )
            container_pool._POOL[safe] = entry_obj
        reattached += 1
        log.info("state: reattached container %s scope=%s", container, safe)
    log.info("state: reattached %d containers", reattached)


# ---------------------------------------------------------------------------
# Request handlers
# ---------------------------------------------------------------------------

def _resolve_scope(payload: dict[str, Any]) -> str:
    raw = payload.get("scope")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return _DEFAULT_SCOPE


def _resolve_timeout(payload: dict[str, Any]) -> int | None:
    raw = payload.get("timeout_s")
    if raw is None:
        return None
    try:
        v = int(raw)
        return max(1, v)
    except (TypeError, ValueError):
        return None


def _python_payload(payload: dict[str, Any]) -> tuple[str, str]:
    code = payload.get("code")
    if not isinstance(code, str) or not code.strip():
        raise ValueError("code must be a non-empty string")
    scope = _resolve_scope(payload)
    timeout_s = _resolve_timeout(payload)

    with _RUN_SEMAPHORE:
        start = time.time()
        exit_code, stdout, stderr, timed_out = container_pool.exec_in_pool(
            scope,
            ["python3", "-u", "-c", code],
            timeout_s=timeout_s,
        )
        _save_state()
        elapsed = time.time() - start

    parts: list[str] = [f"exit_code: {exit_code}"]
    extra = f"scope: {scope}\nshared_dir: /mnt/data/_sandbox"
    if extra:
        parts.append(extra.rstrip())
    if stdout:
        parts.append(f"stdout:\n{stdout.rstrip()}")
    if stderr:
        parts.append(f"stderr:\n{stderr.rstrip()}")
    text = "\n\n".join(parts)

    log.info(
        "python completed scope=%s elapsed=%.3fs exit_code=%d timed_out=%s",
        scope, elapsed, exit_code, timed_out,
    )
    return text, scope


def _run_payload(payload: dict[str, Any]) -> tuple[str, str]:
    """Low-level run: execute arbitrary argv in the pool container."""
    cmd_raw = payload.get("cmd")
    if not isinstance(cmd_raw, list) or not cmd_raw:
        raise ValueError("cmd must be a non-empty array of strings")
    cmd = [str(x) for x in cmd_raw]
    scope = _resolve_scope(payload)
    timeout_s = _resolve_timeout(payload)

    with _RUN_SEMAPHORE:
        start = time.time()
        exit_code, stdout, stderr, timed_out = container_pool.exec_in_pool(
            scope, cmd, timeout_s=timeout_s,
        )
        _save_state()
        elapsed = time.time() - start

    parts: list[str] = [f"exit_code: {exit_code}"]
    extra = f"scope: {scope}\nshared_dir: /mnt/data/_sandbox"
    parts.append(extra)
    if stdout:
        parts.append(f"stdout:\n{stdout.rstrip()}")
    if stderr:
        parts.append(f"stderr:\n{stderr.rstrip()}")
    text = "\n\n".join(parts)

    log.info("run completed scope=%s elapsed=%.3fs exit_code=%d", scope, elapsed, exit_code)
    return text, scope


def _share_payload(payload: dict[str, Any]) -> dict[str, Any]:
    meta = runner.share_sandbox_file(payload.get("path"), payload.get("filename"))
    log.info("share completed path=%s", payload.get("path"))
    return meta


def _files_payload() -> dict[str, Any]:
    listing = runner.list_sandbox_files()
    log.info("files listed count=%s", len(listing.get("files", [])))
    return listing


def _doctor_payload(payload: dict[str, Any]) -> dict[str, Any]:
    repair = bool(payload.get("repair"))
    report = runner.doctor_sandbox(repair=repair)
    log.info("doctor completed ok=%s repair=%s", report.get("ok"), repair)
    return report


def _pool_evict_payload(payload: dict[str, Any]) -> dict[str, Any]:
    scope = _resolve_scope(payload)
    removed = container_pool.evict(scope)
    _save_state()
    log.info("pool/evict scope=%s removed=%s", scope, removed)
    return {"scope": scope, "removed": removed}


def _cleanup_payload() -> dict[str, Any]:
    runner._cleanup_old_state()
    _save_state()
    log.info("cleanup completed")
    return _status()


# ---------------------------------------------------------------------------
# Janitor
# ---------------------------------------------------------------------------

_JANITOR_STARTED = False


def _start_janitor() -> None:
    global _JANITOR_STARTED
    if _JANITOR_STARTED:
        return
    cfg = daemon_config()
    container_pool.start_janitor(interval_seconds=cfg.cleanup_interval_seconds)
    _JANITOR_STARTED = True


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class SandboxDaemonHandler(BaseHTTPRequestHandler):
    server_version = f"sandboxd/{SERVICE_VERSION}"

    def log_message(self, fmt: str, *args: Any) -> None:
        log.info("%s - %s", self.address_string(), fmt % args)

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_payload(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length <= 0:
            return {}
        if length > 10 * 1024 * 1024:
            raise ValueError("request body too large")
        body = self.rfile.read(length)
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return payload

    def do_GET(self) -> None:
        if self.path == "/health":
            cfg = daemon_config()
            self._send_json(
                200,
                {
                    "ok": True,
                    "service": SERVICE_NAME,
                    "version": SERVICE_VERSION,
                    "pid": os.getpid(),
                    "host": cfg.host,
                    "port": cfg.port,
                    "state_path": str(_state_path()),
                    "log_path": str(cfg.log_path),
                    "platform": platform.platform(),
                },
            )
            return
        if self.path == "/status":
            self._send_json(200, {"ok": True, "status": _status()})
            return
        if self.path == "/pool/status":
            self._send_json(200, {"ok": True, "pool": container_pool.pool_status()})
            return
        self._send_json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:
        try:
            payload = self._read_payload()
            if self.path == "/run":
                text, scope = _run_payload(payload)
                self._send_json(200, {"ok": True, "text": text, "scope": scope, "status": _status()})
                return
            if self.path == "/python":
                text, scope = _python_payload(payload)
                self._send_json(200, {"ok": True, "text": text, "scope": scope, "status": _status()})
                return
            if self.path == "/share":
                self._send_json(200, {"ok": True, "meta": _share_payload(payload), "status": _status()})
                return
            if self.path == "/files":
                self._send_json(200, {"ok": True, "listing": _files_payload(), "status": _status()})
                return
            if self.path == "/doctor":
                self._send_json(200, {"ok": True, "doctor": _doctor_payload(payload), "status": _status()})
                return
            if self.path == "/pool/evict":
                self._send_json(200, {"ok": True, **_pool_evict_payload(payload)})
                return
            if self.path == "/cleanup":
                self._send_json(200, {"ok": True, "status": _cleanup_payload()})
                return
            # Legacy session endpoints — kept for backward compat.
            if self.path == "/session/new":
                runner._end_active_session()
                runner._get_active_run_dir()
                self._send_json(200, {"ok": True, "status": _status()})
                return
            if self.path == "/session/end":
                runner._end_active_session()
                self._send_json(200, {"ok": True, "status": _status()})
                return
            self._send_json(404, {"ok": False, "error": "not found"})
        except (ValueError, FileBridgeError, KeyError, container_pool.PoolError) as exc:
            log.warning("request failed path=%s error=%s", self.path, exc)
            self._send_json(400, {"ok": False, "error": str(exc), "status": _status()})
        except Exception as exc:
            log.exception("request crashed path=%s", self.path)
            self._send_json(500, {"ok": False, "error": f"{type(exc).__name__}: {exc}", "status": _status()})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def serve(host: str | None = None, port: int | None = None) -> None:
    _configure_logging()
    cfg = daemon_config()
    host = host or cfg.host
    port = port or cfg.port
    _restore_state()
    # Remove leftover old-style containers from before the pool refactor.
    try:
        removed = container_pool.evict_legacy_sandbox_containers()
        if removed:
            log.info("startup: removed %d legacy sandbox containers", removed)
    except Exception:
        log.warning("startup: legacy container sweep failed (non-fatal)", exc_info=True)
    _start_janitor()
    server = ThreadingHTTPServer((host, port), SandboxDaemonHandler)
    log.info(
        "sandboxd listening url=http://%s:%s state=%s log=%s",
        host, port, _state_path(), cfg.log_path,
    )
    print(f"sandboxd listening on http://{host}:{port}", flush=True)
    server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local sandbox daemon (pool mode).")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()
    serve(args.host, args.port)


if __name__ == "__main__":
    main()
