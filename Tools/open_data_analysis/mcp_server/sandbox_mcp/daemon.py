"""Local sandbox daemon: owns session state outside the MCP process."""
from __future__ import annotations

import argparse
import json
import logging
import os
import platform
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from sandbox_mcp.config import DEFAULT_DAEMON_HOST, DEFAULT_DAEMON_PORT, daemon_config
from sandbox_mcp.files import FileBridgeError
from sandbox_mcp import runner

_RUN_SEMAPHORE = threading.BoundedSemaphore(runner.max_concurrent())
log = logging.getLogger(__name__)
SERVICE_NAME = "sandboxd"
SERVICE_VERSION = "0.1"
_JANITOR_STARTED = False


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


def _state_path() -> Path:
    path = daemon_config().state_path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _status() -> dict[str, Any]:
    with runner._SESSION_LOCK:
        return {
            "active_run_id": runner._ACTIVE_RUN_ID,
            "active_run_dir": str(runner._ACTIVE_RUN_DIR) if runner._ACTIVE_RUN_DIR else None,
            "last_activity": runner._LAST_ACTIVITY,
            "state_path": str(_state_path()),
        }


def _bad_state_path(path: Path) -> Path:
    return path.with_name(f"{path.name}.bad-{int(time.time())}")


def _quarantine_bad_state(path: Path, reason: str) -> None:
    if not path.exists():
        return
    dest = _bad_state_path(path)
    try:
        path.replace(dest)
        log.warning("ignored bad state file path=%s backup=%s reason=%s", path, dest, reason)
    except OSError:
        log.warning("ignored bad state file path=%s reason=%s", path, reason)


def _save_state() -> None:
    path = _state_path()
    with runner._SESSION_LOCK:
        payload = {
            "active_run_id": runner._ACTIVE_RUN_ID,
            "active_run_dir": str(runner._ACTIVE_RUN_DIR) if runner._ACTIVE_RUN_DIR else None,
            "last_activity": runner._LAST_ACTIVITY,
        }
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)
    log.info("saved state active_run_id=%s path=%s", payload["active_run_id"], path)


def _restore_state() -> None:
    path = _state_path()
    if not path.is_file():
        log.info("no state file to restore path=%s", path)
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _quarantine_bad_state(path, "invalid json")
        return
    if not isinstance(data, dict):
        _quarantine_bad_state(path, "state root is not an object")
        return
    run_id = data.get("active_run_id")
    run_dir_raw = data.get("active_run_dir")
    last_activity = data.get("last_activity", 0.0)
    if not isinstance(run_id, str) or not re.fullmatch(r"[a-f0-9]{32}", run_id):
        _quarantine_bad_state(path, "invalid active_run_id")
        return
    if not isinstance(run_dir_raw, str):
        _quarantine_bad_state(path, "invalid active_run_dir")
        return
    run_dir = Path(run_dir_raw).expanduser().resolve()
    if not run_dir.is_dir() or run_dir.name != run_id:
        log.warning("state points to missing or mismatched run dir path=%s run_id=%s", run_dir, run_id)
        return
    try:
        last = float(last_activity)
    except (TypeError, ValueError):
        last = 0.0
    with runner._SESSION_LOCK:
        runner._ACTIVE_RUN_ID = run_id
        runner._ACTIVE_RUN_DIR = run_dir
        runner._LAST_ACTIVITY = last
    runner._cleanup_old_state()
    _save_state()
    log.info("restored session active_run_id=%s active_run_dir=%s", run_id, run_dir)


def _run_payload(payload: dict[str, Any]) -> str:
    request = runner.parse_run_request(payload)
    with _RUN_SEMAPHORE:
        start = time.time()
        text = runner.run_sandbox(request)
        _save_state()
        log.info("run completed elapsed=%.3fs status=%s", time.time() - start, _status()["active_run_id"])
        return text


def _python_payload(payload: dict[str, Any]) -> str:
    code = payload.get("code")
    if not isinstance(code, str) or not code.strip():
        raise ValueError("code must be a non-empty string")
    request = runner.SandboxRunRequest(cmd=["python3", "-u", "-c", code])
    with _RUN_SEMAPHORE:
        start = time.time()
        text = runner.run_sandbox(request)
        _save_state()
        log.info("python completed elapsed=%.3fs status=%s", time.time() - start, _status()["active_run_id"])
        return text


def _share_payload(payload: dict[str, Any]) -> dict[str, Any]:
    with _RUN_SEMAPHORE:
        meta = runner.share_sandbox_file(payload.get("path"), payload.get("filename"))
        _save_state()
        log.info("share completed path=%s", payload.get("path"))
        return meta


def _files_payload() -> dict[str, Any]:
    with _RUN_SEMAPHORE:
        from sandbox_mcp.runner import list_sandbox_files

        listing = list_sandbox_files()
        _save_state()
        log.info("files listed count=%s skipped=%s", len(listing.get("files", [])), len(listing.get("skipped", [])))
        return listing


def _doctor_payload(payload: dict[str, Any]) -> dict[str, Any]:
    with _RUN_SEMAPHORE:
        repair = bool(payload.get("repair"))
        report = runner.doctor_sandbox(repair=repair)
        _save_state()
        log.info("doctor completed ok=%s repair=%s", report.get("ok"), repair)
        return report


def _new_session_payload() -> dict[str, Any]:
    with _RUN_SEMAPHORE:
        runner._end_active_session()
        runner._get_active_run_dir()
        _save_state()
        log.info("created new session active_run_id=%s", _status()["active_run_id"])
        return _status()


def _end_session_payload() -> dict[str, Any]:
    with _RUN_SEMAPHORE:
        runner._end_active_session()
        _save_state()
        log.info("ended session")
        return _status()


def _cleanup_payload() -> dict[str, Any]:
    with _RUN_SEMAPHORE:
        runner._cleanup_old_state()
        _save_state()
        log.info("cleanup completed")
        return _status()


def _janitor_loop(interval_seconds: int) -> None:
    while True:
        time.sleep(interval_seconds)
        try:
            with _RUN_SEMAPHORE:
                runner._cleanup_old_state()
                _save_state()
            log.info("janitor cleanup completed")
        except Exception:
            log.exception("janitor cleanup failed")


def _start_janitor() -> None:
    global _JANITOR_STARTED
    if _JANITOR_STARTED:
        return
    cfg = daemon_config()
    thread = threading.Thread(
        target=_janitor_loop,
        args=(cfg.cleanup_interval_seconds,),
        name="sandboxd-janitor",
        daemon=True,
    )
    thread.start()
    _JANITOR_STARTED = True
    log.info("janitor started interval=%ss", cfg.cleanup_interval_seconds)


class SandboxDaemonHandler(BaseHTTPRequestHandler):
    server_version = "sandboxd/0.1"

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
        self._send_json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:
        try:
            payload = self._read_payload()
            if self.path == "/run":
                self._send_json(200, {"ok": True, "text": _run_payload(payload), "status": _status()})
                return
            if self.path == "/python":
                self._send_json(200, {"ok": True, "text": _python_payload(payload), "status": _status()})
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
            if self.path == "/session/new":
                self._send_json(200, {"ok": True, "status": _new_session_payload()})
                return
            if self.path == "/session/end":
                self._send_json(200, {"ok": True, "status": _end_session_payload()})
                return
            if self.path == "/cleanup":
                self._send_json(200, {"ok": True, "status": _cleanup_payload()})
                return
            self._send_json(404, {"ok": False, "error": "not found"})
        except (ValueError, FileBridgeError, KeyError) as exc:
            log.warning("request failed path=%s error=%s", self.path, exc)
            self._send_json(400, {"ok": False, "error": str(exc), "status": _status()})
        except Exception as exc:
            log.exception("request crashed path=%s", self.path)
            self._send_json(500, {"ok": False, "error": f"{type(exc).__name__}: {exc}", "status": _status()})


def serve(host: str | None = None, port: int | None = None) -> None:
    _configure_logging()
    cfg = daemon_config()
    host = host or cfg.host
    port = port or cfg.port
    _restore_state()
    _start_janitor()
    server = ThreadingHTTPServer((host, port), SandboxDaemonHandler)
    log.info("sandboxd listening url=http://%s:%s state=%s log=%s", host, port, _state_path(), cfg.log_path)
    print(f"sandboxd listening on http://{host}:{port}", flush=True)
    server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local sandbox daemon.")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()
    serve(args.host, args.port)


if __name__ == "__main__":
    main()
