# Copyright NGGT.LightKeeper. All Rights Reserved.

from __future__ import annotations

import asyncio
import atexit
import importlib.util
import inspect
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from queue import Queue
from types import ModuleType
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit

from Services import user_mcp_client
from Settings import mcp_json
from Settings import skills as skills_config
from Settings import settings as runtime_settings

logger = logging.getLogger(__name__)

TOOLS_DIR = Path(__file__).resolve().parent.parent / "Tools"
SERVER_FILENAME = "mcp-server.py"
WORKER_FILE = Path(__file__).resolve().parent.parent / "Services" / "tool_worker.py"
SERVER_DISPATCHER_NAMES = ("call_tool", "run_tool", "execute_tool", "execute")
SERVER_METADATA_NAMES = ("MCP_SERVER", "SERVER")
TOOL_HANDLER_NAMES = ("TOOL_HANDLERS", "TOOL_EXECUTORS")
WORKER_RESPONSE_IDLE_TIMEOUT_SECONDS = 20.0
WORKER_TIMEOUT_BUFFER_SECONDS = 45.0
WORKER_DEFAULT_TIMEOUT_SECONDS = 180.0
WORKER_MAX_TIMEOUT_SECONDS = 7200.0

_SERVER_CACHE_SIGNATURE: tuple[tuple[str, int], ...] | None = None
_SERVER_CACHE: dict[str, dict[str, Any]] = {}
_WORKER_SESSION_LOCK = threading.Lock()
_WORKER_SESSIONS: dict[str, "ExternalWorkerSession"] = {}
_ASYNC_CALLABLE_RUNNER: "AsyncCallableRunner | None" = None
_ASYNC_CALLABLE_RUNNER_LOCK = threading.Lock()
_SEARCH_IO_LOG_LOCK = threading.Lock()
_SEARCH_IO_LOG_PATH = TOOLS_DIR / "mcp-web-search" / "logs" / "model_search_io.json"
_TOOL_COOLDOWN_SECONDS = 30.0
_TOOL_COOLDOWN_LOCK = threading.Lock()
_TOOL_COOLDOWNS: dict[str, float] = {}
TOOL_CALL_QUOTAS = {
    "web_search": 15,
    "read_page": 10,
}
HIGH_EFFORT_WEB_SEARCH_QUOTA = 3
TOOL_BLOCK_FINAL_PROMPT = (
    "Tool loop guard: repeated tool calls were blocked because they duplicate recent work, "
    "hit a quota, or are in cooldown. Do not call tools again. Use the evidence already "
    "present in the conversation and answer the user now. If the collected evidence is "
    "insufficient for a claim, say that clearly instead of searching again."
)


# Run async tool handlers on one persistent event loop.
class AsyncCallableRunner:

    # Initialize the shared runner state.
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._lock = threading.Lock()

    # Host the dedicated asyncio loop on a background thread.
    def _thread_main(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._ready.set()
        try:
            loop.run_forever()
        finally:
            loop.close()

    # Start the background loop thread when it is not already running.
    def ensure_started(self) -> None:
        if self._thread is not None and self._thread.is_alive() and self._loop is not None:
            return

        with self._lock:
            if self._thread is not None and self._thread.is_alive() and self._loop is not None:
                return

            self._ready.clear()
            self._thread = threading.Thread(
                target=self._thread_main,
                name="aslm-async-tool-runner",
                daemon=True,
            )
            self._thread.start()
            self._ready.wait()

    # Run one coroutine on the shared loop and wait for its result.
    def run(self, coro: Any, *, timeout: float | None = None) -> Any:
        self.ensure_started()
        assert self._loop is not None
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    # Stop the background loop and join its thread.
    def close(self) -> None:
        loop = self._loop
        thread = self._thread
        self._loop = None
        self._thread = None
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(loop.stop)
        if thread is not None and thread.is_alive():
            thread.join(timeout=3)


# Return the process-wide async callable runner singleton.
def _get_async_callable_runner() -> AsyncCallableRunner:
    global _ASYNC_CALLABLE_RUNNER
    with _ASYNC_CALLABLE_RUNNER_LOCK:
        if _ASYNC_CALLABLE_RUNNER is None:
            _ASYNC_CALLABLE_RUNNER = AsyncCallableRunner()
        return _ASYNC_CALLABLE_RUNNER


# Build a clean environment for one isolated Python venv.
def _venv_subprocess_env(python_path: Path) -> dict[str, str]:
    """Return subprocess environment aligned with the selected venv."""

    env = os.environ.copy()
    venv_path = python_path.parent.parent
    env["VIRTUAL_ENV"] = str(venv_path)
    env["PATH"] = str(python_path.parent) + os.pathsep + env.get("PATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env.pop("PYTHONHOME", None)
    return env


# Keep one isolated tool worker process alive for stateful servers.
class ExternalWorkerSession:

    # Bind one worker process to a server entrypoint and venv Python.
    def __init__(self, server_file: Path, python_path: Path) -> None:
        self.server_file = server_file
        self.python_path = python_path
        self.process: subprocess.Popen[str] | None = None
        self.lock = threading.Lock()

    # Spawn the worker process when it is missing or has exited.
    def _start(self) -> None:
        if self.process is not None and self.process.poll() is None:
            return

        self.close()
        self.process = subprocess.Popen(
            [str(self.python_path), str(WORKER_FILE), "serve", str(self.server_file)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(self.server_file.parent),
            env=_venv_subprocess_env(self.python_path),
            bufsize=1,
        )

    # Send one JSON request to the worker and return its result envelope.
    def request(
        self,
        operation: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout_s: float | None = None,
    ) -> Any:
        """Send one request to the worker process and return its result."""

        with self.lock:
            request_payload = {
                "operation": operation,
                "payload": payload or {},
            }

            raw_response = ""
            last_error: Exception | None = None
            for attempt in range(2):
                self._start()
                assert self.process is not None
                assert self.process.stdin is not None
                assert self.process.stdout is not None

                try:
                    self.process.stdin.write(json.dumps(request_payload, ensure_ascii=False) + "\n")
                    self.process.stdin.flush()
                    raw_response = self._read_response_line(timeout_s or _worker_timeout_seconds(operation, payload))
                except TimeoutError as exc:
                    last_error = exc
                    raw_response = ""
                    self.close()
                    break
                except (BrokenPipeError, OSError) as exc:
                    last_error = exc
                    raw_response = ""

                if raw_response:
                    break

                self.close()
                if attempt == 0:
                    logger.warning("Tool worker stopped before response; restarting once for %s", self.server_file)
                    continue

            if not raw_response:
                self.close()
                if last_error is not None:
                    raise RuntimeError(f"Tool worker stopped for {self.server_file}: {last_error}")
                raise RuntimeError(f"Tool worker stopped for {self.server_file}.")

            try:
                envelope = json.loads(raw_response)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Tool worker returned invalid JSON: {raw_response[:500]}") from exc

            if not isinstance(envelope, dict):
                raise RuntimeError(f"Tool worker returned invalid envelope: {raw_response[:500]}")

            if not envelope.get("ok"):
                raise RuntimeError(str(envelope.get("error") or "Unknown tool worker error."))

            return envelope.get("result")

    # Read worker protocol lines until a final JSON envelope arrives.
    def _read_response_line(self, timeout_s: float) -> str:
        """Read worker protocol lines until a final envelope arrives."""

        process = self.process
        if process is None or process.stdout is None:
            return ""

        deadline = time.monotonic() + max(1.0, float(timeout_s))
        while True:
            lines: Queue[str] = Queue()

            # Read one stdout line in a background thread.
            def reader() -> None:
                try:
                    lines.put(process.stdout.readline())
                except Exception:
                    lines.put("")

            thread = threading.Thread(target=reader, name="aslm-tool-worker-readline", daemon=True)
            thread.start()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self.close()
                raise TimeoutError(f"Tool worker timed out after {timeout_s:.0f}s for {self.server_file}.")
            wait_s = min(WORKER_RESPONSE_IDLE_TIMEOUT_SECONDS, remaining)
            thread.join(timeout=wait_s)
            if thread.is_alive():
                self.close()
                raise TimeoutError(
                    f"Tool worker produced no heartbeat or result within {wait_s:.0f}s for {self.server_file}."
                )

            raw_line = lines.get()
            if not raw_line:
                return ""
            try:
                envelope = json.loads(raw_line)
            except json.JSONDecodeError:
                return raw_line
            if isinstance(envelope, dict) and envelope.get("event") == "heartbeat":
                continue
            return raw_line

    # Stop the worker process if it is running.
    def close(self) -> None:

        process = self.process
        self.process = None
        if process is None:
            return

        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
        finally:
            for stream in (process.stdin, process.stdout, process.stderr):
                try:
                    if stream is not None:
                        stream.close()
                except Exception:
                    pass


# Print one shared runtime event.
def _print_runtime_event(message: str) -> None:
    """Emit one console-visible runtime event."""

    print(f"[ASLM-Chat] {message}", flush=True)


# Return a wall-clock timeout for one worker request.
def _worker_timeout_seconds(operation: str, payload: dict[str, Any] | None = None) -> float:
    """Return a wall-clock timeout for one worker request."""

    timeout_s = WORKER_DEFAULT_TIMEOUT_SECONDS
    payload = payload if isinstance(payload, dict) else {}
    if operation == "call":
        arguments = payload.get("arguments")
        if isinstance(arguments, dict):
            try:
                timeout_s = float(arguments.get("timeout_s") or timeout_s)
            except (TypeError, ValueError):
                timeout_s = WORKER_DEFAULT_TIMEOUT_SECONDS
    return min(WORKER_MAX_TIMEOUT_SECONDS, max(1.0, timeout_s + WORKER_TIMEOUT_BUFFER_SECONDS))


# Check whether debug logging is enabled.
def _is_debug_logging_enabled() -> bool:
    """Return whether debug-or-higher MCP events should be printed."""

    return runtime_settings.is_console_debug_enabled()


# Check whether trace logging is enabled.
def _is_trace_logging_enabled() -> bool:
    """Return whether trace-level MCP events should be printed."""

    return runtime_settings.is_console_trace_enabled()


# Render one compact debug preview.
def _preview_jsonish(value: Any, limit: int = 240) -> str:
    """Return a compact one-line preview for arguments and results."""

    try:
        if isinstance(value, str):
            rendered = value
        else:
            rendered = json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        rendered = str(value)

    rendered = re.sub(r"\s+", " ", str(rendered or "")).strip()
    if len(rendered) <= limit:
        return rendered
    return f"{rendered[:max(0, limit - 3)].rstrip()}..."


# Summarize one tool result.
def _summarize_tool_result(result: Any) -> str:
    """Return a short textual summary of a tool result payload."""

    if isinstance(result, dict) and "_image_b64" in result:
        return f"image:{result.get('_mime_type', 'image')} path={result.get('_path', '') or '(inline)'}"
    if result is None:
        return "empty"
    if isinstance(result, str):
        return f"text chars={len(result)} preview={_preview_jsonish(result, limit=140)}"
    if isinstance(result, (dict, list, tuple)):
        try:
            size_hint = len(result)
        except TypeError:
            size_hint = "?"
        return f"{type(result).__name__} size={size_hint} preview={_preview_jsonish(result, limit=140)}"
    return f"{type(result).__name__} value={_preview_jsonish(result, limit=140)}"


# Summarize one tool context.
def _summarize_tool_context(context: dict[str, Any]) -> str:
    """Return a compact summary of the runtime context passed into a tool."""

    parts: list[str] = []
    for key in ("engine", "model_name", "chat_id", "tool_round_index", "tool_call_index"):
        value = context.get(key)
        if value not in {None, ""}:
            parts.append(f"{key}={value}")

    if _is_trace_logging_enabled():
        for key in ("server_file", "tools_dir"):
            value = context.get(key)
            if value not in {None, ""}:
                parts.append(f"{key}={value}")

    return ", ".join(parts) if parts else "none"


# Enforce per-response tool quotas and cooldowns.
# Return the canonical tool id used for per-response quotas.
def _quota_tool_id(tool_event: dict[str, Any] | None) -> str:
    """Return the canonical tool id used for per-response quotas."""

    if not isinstance(tool_event, dict):
        return ""
    tool_id = _slugify(str(tool_event.get("tool_id") or ""))
    alias = _slugify(str(tool_event.get("alias") or ""))
    for quota_tool_id in TOOL_CALL_QUOTAS:
        if tool_id == quota_tool_id or alias == quota_tool_id or alias.endswith(f"__{quota_tool_id}"):
            return quota_tool_id
    return ""


# Return the normalized web-search effort value from tool arguments.
def _search_effort(arguments: dict[str, Any] | None) -> str:
    """Return the normalized web-search effort value from tool arguments."""

    if not isinstance(arguments, dict):
        return ""

    value = arguments.get("effort")
    if value is None and isinstance(arguments.get("query"), dict):
        value = arguments["query"].get("effort")
    return str(value or "").strip().lower()


# Return the per-response quota for one tool call.
def _tool_quota_limit(quota_tool_id: str, arguments: dict[str, Any] | None = None) -> int:
    """Return the per-response quota for one tool call."""

    if quota_tool_id == "web_search" and _search_effort(arguments) == "high":
        return HIGH_EFFORT_WEB_SEARCH_QUOTA
    return TOOL_CALL_QUOTAS[quota_tool_id]


# Append complete model/search tool IO as a readable JSON array.
def _write_search_io_event(event: dict[str, Any]) -> None:
    """Append complete model/search tool IO as a readable JSON array."""

    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        **dict(event or {}),
    }
    record = _without_duplicate_preview(record)
    try:
        _SEARCH_IO_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _SEARCH_IO_LOG_LOCK:
            entries: list[Any] = []
            if _SEARCH_IO_LOG_PATH.exists():
                try:
                    loaded = json.loads(_SEARCH_IO_LOG_PATH.read_text(encoding="utf-8") or "[]")
                    if isinstance(loaded, list):
                        entries = loaded
                except Exception:
                    entries = []
            entries.append(record)
            _SEARCH_IO_LOG_PATH.write_text(
                json.dumps(entries, ensure_ascii=False, default=str, indent=2),
                encoding="utf-8",
            )
    except Exception:
        logger.debug("Failed to write search IO JSON event.", exc_info=True)


# Remove preview fields from diagnostics when they duplicate snippet text.
def _without_duplicate_preview(value: Any) -> Any:
    """Remove preview fields from diagnostics when they exactly duplicate snippet."""

    if isinstance(value, list):
        return [_without_duplicate_preview(item) for item in value]
    if not isinstance(value, dict):
        return value

    cleaned = {
        key: _without_duplicate_preview(item)
        for key, item in value.items()
    }
    snippet = cleaned.get("snippet")
    preview = cleaned.get("preview")
    if isinstance(snippet, str) and isinstance(preview, str) and snippet == preview:
        cleaned.pop("preview", None)
    return cleaned


# Log exactly what search/read-page tools receive from and return to the model.
def log_search_tool_io(
    phase: str,
    tool_event: dict[str, Any] | None,
    arguments: Any = None,
    context: dict[str, Any] | None = None,
    result: Any = None,
    error: Any = None,
    elapsed_seconds: float | None = None,
) -> None:
    """Log exactly what search/read-page tools receive from and return to the model."""

    quota_tool_id = _quota_tool_id(tool_event)
    if not quota_tool_id:
        return
    _write_search_io_event(
        {
            "layer": "api_tool_bridge",
            "phase": phase,
            "tool_id": quota_tool_id,
            "tool_event": tool_event or {},
            "context": context or {},
            "arguments": arguments,
            "result": result,
            "error": str(error) if error is not None else None,
            "elapsed_seconds": elapsed_seconds,
        }
    )


# Increment one quota counter and return an error when the call is over limit.
def consume_tool_quota(
    tool_event: dict[str, Any] | None,
    counters: dict[str, int],
    arguments: dict[str, Any] | None = None,
) -> str | None:
    """Increment one quota counter and return an error message if the call is over limit."""

    quota_tool_id = _quota_tool_id(tool_event)
    if not quota_tool_id:
        return None

    limit = _tool_quota_limit(quota_tool_id, arguments)
    current = int(counters.get(quota_tool_id, 0) or 0)
    if current >= limit:
        display_name = str((tool_event or {}).get("tool_name") or quota_tool_id).strip() or quota_tool_id
        if quota_tool_id == "web_search" and _search_effort(arguments) == "high":
            return (
                f"Tool quota exceeded: {display_name} high mode is unavailable "
                "for the rest of this assistant response; use medium or low."
            )
        return (
            f"Tool quota exceeded: {display_name} can be used at most {limit} times "
            "in one assistant response. Stop calling this tool and answer with the evidence already collected."
        )

    counters[quota_tool_id] = current + 1
    return None


# Return whether a tool result is a guardrail message, not fresh evidence.
def is_blocking_tool_result(result: Any) -> bool:
    """Return whether a tool result is a guardrail/block message, not fresh evidence."""

    text = str(result or "").strip()
    return text.startswith(
        (
            "Duplicate tool call blocked:",
            "Duplicate web_search blocked:",
            "Duplicate read_page blocked:",
            "Tool quota exceeded:",
        )
    )


# Return the instruction used when the tool loop must stop retrying tools.
def forced_final_prompt_after_tool_blocks() -> str:
    """Return the instruction used when the tool loop must stop retrying tools."""

    return TOOL_BLOCK_FINAL_PROMPT


# Return a stable representation for duplicate tool-call detection.
def _canonical_tool_arguments(value: Any) -> Any:
    """Return a stable representation for duplicate tool-call detection."""

    if isinstance(value, str):
        text = re.sub(r"\s+", " ", value).strip()
        if text and text[0] in "[{":
            try:
                return _canonical_tool_arguments(json.loads(text))
            except Exception:
                return text
        return text
    if isinstance(value, dict):
        return {
            str(key): _canonical_tool_arguments(value[key])
            for key in sorted(value.keys(), key=str)
        }
    if isinstance(value, list):
        return [_canonical_tool_arguments(item) for item in value]
    return value


# Return an error message when the same quota-controlled tool call repeats.
def consume_duplicate_tool_call(
    tool_event: dict[str, Any] | None,
    arguments: dict[str, Any] | None,
    seen_signatures: set[str],
) -> str | None:
    """Return an error message when the same quota-controlled tool call repeats."""

    quota_tool_id = _quota_tool_id(tool_event)
    if not quota_tool_id:
        return None

    canonical_args = _canonical_tool_arguments(arguments or {})
    try:
        args_key = json.dumps(canonical_args, ensure_ascii=False, sort_keys=True, default=str)
    except TypeError:
        args_key = str(canonical_args)
    signature = f"{quota_tool_id}:{args_key}"

    if signature in seen_signatures:
        display_name = str((tool_event or {}).get("tool_name") or quota_tool_id).strip() or quota_tool_id
        return (
            f"Duplicate tool call blocked: {display_name} was already called with the same arguments "
            "in this assistant response. Do not retry identical searches or page reads; use the existing result."
        )

    seen_signatures.add(signature)
    return None


# Extract normalized read_page URL arguments from one tool payload.
def _read_page_urls(arguments: dict[str, Any] | None) -> list[str]:
    if not isinstance(arguments, dict):
        return []
    raw_url = arguments.get("url", "")
    if isinstance(raw_url, str):
        text = raw_url.strip()
        if text and text[0] == "[":
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    raw_url = parsed
                else:
                    raw_url = text
            except Exception:
                raw_url = text
        else:
            raw_url = text
    if isinstance(raw_url, list):
        return [str(item).strip() for item in raw_url if str(item or "").strip()]
    return [str(raw_url).strip()] if str(raw_url or "").strip() else []


# Normalize one read_page URL for cooldown comparison.
def _normalize_read_page_url(url: str) -> str:
    text = re.sub(r"\s+", " ", str(url or "").strip())
    if not text:
        return ""
    try:
        parsed = urlsplit(text)
    except Exception:
        return text.lower()
    if not parsed.scheme or not parsed.netloc:
        return text.rstrip("/").lower()
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path or ""
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit((scheme, netloc, path, parsed.query, ""))


# Normalize one cooldown key payload for stable comparison.
def _normalize_cooldown_value(value: Any) -> Any:
    canonical = _canonical_tool_arguments(value)
    if isinstance(canonical, str):
        return re.sub(r"\s+", " ", canonical).strip().lower()
    if isinstance(canonical, dict):
        return {
            str(key): _normalize_cooldown_value(canonical[key])
            for key in sorted(canonical.keys(), key=str)
        }
    if isinstance(canonical, list):
        return [_normalize_cooldown_value(item) for item in canonical]
    return canonical


# Build cooldown keys for one search or read_page tool invocation.
def _tool_cooldown_keys(tool_event: dict[str, Any] | None, arguments: dict[str, Any] | None) -> list[tuple[str, str]]:
    tool_id = _quota_tool_id(tool_event)
    if tool_id == "read_page":
        urls = [_normalize_read_page_url(url) for url in _read_page_urls(arguments)]
        return [
            (f"{tool_id}:url:{url}", url)
            for url in dict.fromkeys(url for url in urls if url)
        ]
    if tool_id == "web_search":
        canonical = _normalize_cooldown_value(arguments or {})
        try:
            key = json.dumps(canonical, ensure_ascii=False, sort_keys=True, default=str)
        except TypeError:
            key = str(canonical)
        label = _preview_jsonish(canonical, limit=220)
        return [(f"{tool_id}:args:{key}", label)] if key and key != "{}" else []
    return []


# Format the duplicate-tool cooldown message shown to the model.
def _tool_cooldown_message(tool_id: str, entries: list[tuple[str, int]]) -> str:
    display = "web_search" if tool_id == "web_search" else "read_page"
    thing = "query" if tool_id == "web_search" else "URL"
    lines = [
        f"Duplicate {display} blocked: this {thing} was already used in the last 30 seconds.",
        f"Do not call {display} for it again right now; use the content already returned by the previous tool result.",
        "Repeated calls waste tool calls and add no new evidence.",
        "",
        "Cooldown entries:",
    ]
    for label, remaining in entries:
        lines.append(f"- {label} ({remaining}s remaining)")
    return "\n".join(lines)


# Block repeated search/read-page calls within a short cooldown window.
def consume_tool_cooldown(tool_event: dict[str, Any] | None, arguments: dict[str, Any] | None) -> str | None:
    """Block repeated search/read-page calls within a short cooldown window."""

    tool_id = _quota_tool_id(tool_event)
    entries = _tool_cooldown_keys(tool_event, arguments)
    if not tool_id or not entries:
        return None

    now = time.monotonic()
    with _TOOL_COOLDOWN_LOCK:
        expired = [key for key, expires_at in _TOOL_COOLDOWNS.items() if expires_at <= now]
        for key in expired:
            _TOOL_COOLDOWNS.pop(key, None)

        duplicate_entries: list[tuple[str, int]] = []
        for key, label in entries:
            expires_at = _TOOL_COOLDOWNS.get(key)
            if expires_at and expires_at > now:
                duplicate_entries.append((label, max(1, int(round(expires_at - now)))))

    if len(duplicate_entries) == len(entries):
        return _tool_cooldown_message(tool_id, duplicate_entries)
    return None


# Mark search/read-page calls as recently used.
def remember_tool_cooldown(tool_event: dict[str, Any] | None, arguments: dict[str, Any] | None) -> None:
    """Mark search/read-page calls as recently used."""

    entries = _tool_cooldown_keys(tool_event, arguments)
    if not entries:
        return
    expires_at = time.monotonic() + _TOOL_COOLDOWN_SECONDS
    with _TOOL_COOLDOWN_LOCK:
        for key, _label in entries:
            _TOOL_COOLDOWNS[key] = expires_at


# Delegate read_page cooldown checks to the shared tool cooldown helper.
def consume_read_page_cooldown(tool_event: dict[str, Any] | None, arguments: dict[str, Any] | None) -> str | None:
    return consume_tool_cooldown(tool_event, arguments)


# Delegate read_page cooldown bookkeeping to the shared tool cooldown helper.
def remember_read_page_cooldown(tool_event: dict[str, Any] | None, arguments: dict[str, Any] | None) -> None:
    remember_tool_cooldown(tool_event, arguments)


# Manage the server discovery cache.
# Clear the cached registry.
def reset_cache() -> None:
    """Clear cached discovery so local edits are picked up immediately."""

    global _SERVER_CACHE_SIGNATURE, _SERVER_CACHE

    _SERVER_CACHE_SIGNATURE = None
    _SERVER_CACHE = {}
    user_mcp_client.shutdown_all()


# Yield one server's source files.
def _iter_server_source_files(server_dir: Path):
    """Yield relevant source files for one local MCP server."""

    for path in sorted(server_dir.rglob("*"), key=lambda item: str(item).casefold()):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts:
            continue
        if path.suffix.lower() not in {".py", ".json"}:
            continue
        yield path


# Build the server cache signature.
def _server_signature() -> tuple[tuple[str, int], ...]:
    """Build a stable signature for every local MCP server source file."""

    if not TOOLS_DIR.exists():
        return ()

    entries: list[tuple[str, int]] = []
    for child in sorted(TOOLS_DIR.iterdir(), key=lambda item: item.name.casefold()):
        server_file = child / SERVER_FILENAME
        if not child.is_dir() or not server_file.is_file():
            continue

        for source_file in _iter_server_source_files(child):
            try:
                stat = source_file.stat()
            except OSError:
                continue

            entries.append((str(source_file), stat.st_mtime_ns))

    mcp_sig = mcp_json.mcp_json_signature()
    if mcp_sig is not None:
        entries.append(mcp_sig)

    return tuple(entries)


# Yield server entrypoint files.
def _iter_server_files():
    """Yield top-level MCP server entrypoints from the Tools directory."""

    if not TOOLS_DIR.exists():
        return

    for child in sorted(TOOLS_DIR.iterdir(), key=lambda item: item.name.casefold()):
        server_file = child / SERVER_FILENAME
        if child.is_dir() and server_file.is_file():
            yield server_file


# Load and normalize server definitions.
# Normalize one server id.
def _slugify(value: str) -> str:
    """Normalize folder and public identifiers into a stable slug."""

    normalized = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")
    return normalized or "tool"

# Purge modules from one server root.
def _purge_modules_under(server_root: Path) -> None:
    """Drop previously imported modules loaded from one tool directory."""

    resolved_root = server_root.resolve()
    stale_module_names: list[str] = []

    for module_name, module in list(sys.modules.items()):
        module_file = getattr(module, "__file__", None)
        if not module_file:
            continue

        try:
            module_path = Path(module_file).resolve()
        except OSError:
            continue

        if module_path.is_relative_to(resolved_root):
            stale_module_names.append(module_name)

    for module_name in stale_module_names:
        sys.modules.pop(module_name, None)


# Load one server module.
def _load_module(server_file: Path) -> ModuleType:
    """Load one ``mcp-server.py`` file into an isolated Python module."""

    _purge_modules_under(server_file.parent)

    module_name = f"aslm_chat_mcp_server_{_slugify(server_file.parent.name)}"
    spec = importlib.util.spec_from_file_location(module_name, server_file)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load MCP server module from {server_file}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Return the configured worker Python for one tool server when available.
def _get_worker_python(server_file: Path) -> Path | None:
    """Return the isolated Python executable assigned to one tool server."""

    try:
        from Services import venv_manager

        return venv_manager.get_tool_python(server_file.parent.name)
    except Exception as exc:
        logger.warning("Could not resolve tool venv for %s: %s", server_file, exc)
        return None


# Close all persistent external workers.
def close_external_workers() -> None:
    """Stop persistent external tool workers owned by this process."""

    with _WORKER_SESSION_LOCK:
        sessions = list(_WORKER_SESSIONS.values())
        _WORKER_SESSIONS.clear()

    for session in sessions:
        session.close()

    global _ASYNC_CALLABLE_RUNNER
    with _ASYNC_CALLABLE_RUNNER_LOCK:
        runner = _ASYNC_CALLABLE_RUNNER
        _ASYNC_CALLABLE_RUNNER = None
    if runner is not None:
        runner.close()


atexit.register(close_external_workers)


# Return one persistent external worker for a server file.
def _get_worker_session(server_file: Path) -> ExternalWorkerSession:
    """Return a long-lived worker session for one external tool server."""

    python_path = _get_worker_python(server_file)
    if python_path is None:
        raise RuntimeError(f"No isolated Python environment is available for {server_file.parent.name}.")

    session_key = str(server_file.resolve())
    with _WORKER_SESSION_LOCK:
        session = _WORKER_SESSIONS.get(session_key)
        if session is None or session.python_path != python_path:
            if session is not None:
                session.close()
            session = ExternalWorkerSession(server_file, python_path)
            _WORKER_SESSIONS[session_key] = session
        return session


# Execute one isolated tool worker operation.
def _run_worker(
    server_file: Path,
    operation: str,
    payload: dict[str, Any] | None = None,
    *,
    persistent: bool = False,
) -> Any:
    """Run a tool worker operation and return its result payload."""

    if persistent:
        return _get_worker_session(server_file).request(
            operation,
            payload,
            timeout_s=_worker_timeout_seconds(operation, payload),
        )

    python_path = _get_worker_python(server_file)
    if python_path is None:
        raise RuntimeError(f"No isolated Python environment is available for {server_file.parent.name}.")

    request_payload = json.dumps(payload or {}, ensure_ascii=False)
    result = subprocess.run(
        [str(python_path), str(WORKER_FILE), operation, str(server_file)],
        input=request_payload,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(server_file.parent),
        env=_venv_subprocess_env(python_path),
        check=False,
        timeout=_worker_timeout_seconds(operation, payload),
    )

    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    if not stdout:
        raise RuntimeError(stderr or f"Tool worker returned no output for {server_file}.")

    envelope = None
    for line in reversed(stdout.splitlines()):
        try:
            envelope = json.loads(line)
            break
        except json.JSONDecodeError:
            continue
    if not isinstance(envelope, dict):
        raise RuntimeError(f"Tool worker returned invalid JSON: {stdout[:500]}")

    if not envelope.get("ok"):
        error = str(envelope.get("error") or stderr or "Unknown tool worker error.")
        raise RuntimeError(error)

    return envelope.get("result")


# Load one server definition through its isolated worker.
def _load_external_server(server_file: Path) -> dict[str, Any]:
    """Load one server definition without importing it into the Django process."""

    description = _run_worker(server_file, "describe", {})
    if not isinstance(description, dict):
        raise ValueError("Tool worker describe response must be a dictionary.")

    server_id = _slugify(str(description.get("id") or server_file.parent.name))
    tools = description.get("tools")
    if not isinstance(tools, list) or not tools:
        raise ValueError("Tool worker did not return any tools.")

    return {
        "id": server_id,
        "name": str(description.get("name") or server_file.parent.name).strip() or server_file.parent.name,
        "description": str(description.get("description") or "").strip(),
        "tools": tools,
        "module": None,
        "supports": None,
        "server_callable": None,
        "tool_handlers": {},
        "server_file": server_file,
        "external": True,
    }


# Normalize one tool schema.
def _normalize_schema(schema: Any) -> dict[str, Any]:
    """Return a JSON-schema-like mapping suitable for tool payloads."""

    if not isinstance(schema, dict):
        return {"type": "object", "properties": {}}

    normalized = dict(schema)
    normalized.setdefault("type", "object")
    normalized.setdefault("properties", {})
    if not isinstance(normalized.get("properties"), dict):
        normalized["properties"] = {}

    return normalized

# Resolve the server dispatcher.
def _resolve_server_callable(module: ModuleType):
    """Return the generic server dispatcher when one is exported."""

    for attr_name in SERVER_DISPATCHER_NAMES:
        candidate = getattr(module, attr_name, None)
        if callable(candidate):
            return candidate

    return None

# Collect explicit tool handlers.
def _normalize_tool_handlers(module: ModuleType) -> dict[str, Any]:
    """Return explicit per-tool handlers exported by a server module."""

    raw_handlers: Any = None
    for attr_name in TOOL_HANDLER_NAMES:
        raw_handlers = getattr(module, attr_name, None)
        if raw_handlers is not None:
            break

    if not isinstance(raw_handlers, dict):
        return {}

    normalized_handlers: dict[str, Any] = {}
    for raw_key, raw_value in raw_handlers.items():
        if callable(raw_value):
            normalized_handlers[_slugify(str(raw_key or ""))] = raw_value

    return normalized_handlers

# Validate the tool list.
def _normalize_server_tools(raw_tools: Any, server_id: str) -> list[dict[str, Any]]:
    """Validate and normalize tool definitions exposed by one server."""

    if not isinstance(raw_tools, list) or not raw_tools:
        raise ValueError("MCP server module must expose a non-empty TOOLS list")

    normalized_tools: list[dict[str, Any]] = []
    seen_tool_ids: set[str] = set()

    for index, raw_tool in enumerate(raw_tools, start=1):
        if not isinstance(raw_tool, dict):
            raise ValueError("Each MCP server tool definition must be a dictionary")

        tool_id = _slugify(str(raw_tool.get("id") or f"tool_{index}"))
        if tool_id in seen_tool_ids:
            raise ValueError(f"Duplicate tool id '{tool_id}' in server '{server_id}'")

        seen_tool_ids.add(tool_id)

        name = str(raw_tool.get("name") or tool_id).strip() or tool_id
        description = str(raw_tool.get("description") or "").strip()
        parameters = _normalize_schema(raw_tool.get("parameters"))

        normalized_tools.append(
            {
                "id": tool_id,
                "alias": f"{server_id}__{tool_id}",
                "name": name,
                "description": description,
                "parameters": parameters,
            }
        )

    return normalized_tools


# Append servers from MCP/mcp.json to the registry payload.
def _merge_user_mcp_servers(discovered: dict[str, dict[str, Any]]) -> None:
    """Append servers from ``MCP/mcp.json`` to the registry payload."""

    try:
        mcp_json.ensure_default_mcp_json()
        reserved = set(discovered.keys())
        for entry in mcp_json.iter_user_mcp_entries(reserved):
            tools, err = user_mcp_client.fetch_tool_definitions(entry)
            description = f"User MCP server ({entry.transport})"
            if err:
                description = f"{description}. {err}"
            placeholder = mcp_json.MCP_DIR / f".user_mcp_{entry.server_id}"
            discovered[entry.server_id] = {
                "id": entry.server_id,
                "name": entry.display_name,
                "description": description[:500],
                "tools": tools,
                "user_mcp": True,
                "user_mcp_entry": entry,
                "module": None,
                "supports": None,
                "server_callable": None,
                "tool_handlers": {},
                "server_file": placeholder,
                "external": False,
            }
    except Exception as exc:
        logger.warning("Failed to merge user MCP servers: %s", exc)


# Build one server definition.
def _extract_server_definition(module: ModuleType, folder_name: str, server_file: Path) -> dict[str, Any]:
    """Validate a local MCP module and normalize its public metadata."""

    raw_server: Any = {}
    # Support both current and legacy metadata export names.
    for attr_name in SERVER_METADATA_NAMES:
        raw_server = getattr(module, attr_name, None)
        if raw_server is not None:
            break

    if raw_server is None:
        raw_server = {}
    if not isinstance(raw_server, dict):
        raise ValueError("MCP server module must expose an MCP_SERVER dictionary")

    raw_tools = getattr(module, "TOOLS", None)
    if raw_tools is None:
        legacy_tool = getattr(module, "TOOL", None)
        if isinstance(legacy_tool, dict):
            raw_tools = [legacy_tool]

    server_id = _slugify(str(raw_server.get("id") or folder_name))
    server_name = str(raw_server.get("name") or folder_name).strip() or folder_name
    description = str(raw_server.get("description") or "").strip()
    supports_fn = getattr(module, "supports", None)
    tool_handlers = _normalize_tool_handlers(module)
    server_callable = _resolve_server_callable(module)
    tools = _normalize_server_tools(raw_tools, server_id)

    # A server is valid only if it exposes either dedicated handlers per tool
    # or one generic dispatcher that can receive tool invocations.
    if not tool_handlers and server_callable is None:
        raise ValueError(
            "MCP server module must expose TOOL_HANDLERS or a generic call_tool/tool dispatcher"
        )

    return {
        "id": server_id,
        "name": server_name,
        "description": description,
        "tools": tools,
        "module": module,
        "supports": supports_fn if callable(supports_fn) else None,
        "server_callable": server_callable,
        "tool_handlers": tool_handlers,
        "server_file": server_file,
    }


# Refresh the server registry.
def _ensure_registry_loaded() -> dict[str, dict[str, Any]]:
    """Discover and cache valid local MCP-style server modules."""

    global _SERVER_CACHE_SIGNATURE, _SERVER_CACHE

    signature = _server_signature()
    # The cache is keyed by file mtimes so local edits become visible without
    # forcing a full rediscovery on every call.
    if signature == _SERVER_CACHE_SIGNATURE:
        return _SERVER_CACHE

    user_mcp_client.shutdown_all()

    discovered: dict[str, dict[str, Any]] = {}
    for server_file in _iter_server_files():
        folder_name = server_file.parent.name

        try:
            if _get_worker_python(server_file) is not None:
                server_definition = _load_external_server(server_file)
            else:
                module = _load_module(server_file)
                server_definition = _extract_server_definition(module, folder_name, server_file)
            discovered[server_definition["id"]] = server_definition
        except Exception as exc:
            logger.warning("Skipping invalid MCP server module %s: %s", server_file, exc)

    _merge_user_mcp_servers(discovered)

    _SERVER_CACHE_SIGNATURE = signature
    _SERVER_CACHE = discovered
    return _SERVER_CACHE

# Check whether one server is supported.
def _server_is_supported(
    server_definition: dict[str, Any],
    engine: str | None,
    model_name: str | None,
) -> bool:
    """Return whether a server supports the current engine and model."""

    if server_definition.get("user_mcp"):
        return True

    if server_definition.get("external"):
        try:
            return bool(_run_worker(
                Path(server_definition["server_file"]),
                "supports",
                {"engine": engine, "model_name": model_name},
            ))
        except Exception as exc:
            logger.warning("Server %s support check failed: %s", server_definition["id"], exc)
            return False

    supports_fn = server_definition.get("supports")
    if not callable(supports_fn):
        return True

    try:
        return bool(supports_fn(engine=engine, model_name=model_name))
    except TypeError:
        # Older handlers may still accept only positional arguments.
        try:
            return bool(supports_fn(engine, model_name))
        except Exception as exc:
            logger.warning("Server %s support check failed: %s", server_definition["id"], exc)
            return False
    except Exception as exc:
        logger.warning("Server %s support check failed: %s", server_definition["id"], exc)
        return False

# List matching servers.
def list_servers(engine: str | None = None, model_name: str | None = None) -> list[dict[str, Any]]:
    """Return discovered servers that support the current engine and model."""

    registry = _ensure_registry_loaded()
    return [
        _serialize_server(server_definition)
        for server_definition in registry.values()
        if _server_is_supported(server_definition, engine, model_name)
    ]

# Get one matching server.
def get_server(
    server_id: str | None,
    engine: str | None = None,
    model_name: str | None = None,
) -> dict[str, Any] | None:
    """Return one discovered server when it is available in the current context."""

    normalized_id = _slugify(str(server_id or ""))
    if not normalized_id:
        return None

    registry = _ensure_registry_loaded()
    server_definition = registry.get(normalized_id)
    if not server_definition:
        return None
    if not _server_is_supported(server_definition, engine, model_name):
        return None

    return server_definition


# Serialize registry data.
# Serialize one tool.
def _serialize_tool(tool_definition: dict[str, Any]) -> dict[str, Any]:
    """Return the frontend-facing representation of one tool."""

    return {
        "id": tool_definition["id"],
        "name": tool_definition["name"],
        "description": tool_definition["description"],
    }

# Serialize one server.
def _serialize_server(server_definition: dict[str, Any]) -> dict[str, Any]:
    """Return the frontend-facing representation of one server."""

    tools = [_serialize_tool(tool_definition) for tool_definition in server_definition["tools"]]
    payload: dict[str, Any] = {
        "id": server_definition["id"],
        "name": server_definition["name"],
        "description": server_definition["description"],
        "tool_count": len(tools),
        "tools": tools,
    }
    if server_definition.get("user_mcp"):
        payload["user_mcp"] = True
    return payload

# Build Ollama-compatible tool definitions.
def build_ollama_tools(
    server_ids: str | list[str] | None,
    engine: str | None = None,
    model_name: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Return Ollama-compatible tool payloads for one or more selected servers."""

    if isinstance(server_ids, str):
        server_ids = [server_ids] if server_ids else []
    elif not server_ids:
        server_ids = []

    tools: list[dict[str, Any]] = []
    tool_lookup: dict[str, dict[str, Any]] = {}

    for server_id in server_ids:
        server_definition = get_server(server_id, engine=engine, model_name=model_name)
        if not server_definition:
            continue

        for tool_definition in server_definition["tools"]:
            alias = tool_definition["alias"]
            # Tool aliases are global in the conversation, so skip duplicates
            # when multiple selected servers resolve to the same public alias.
            if alias in tool_lookup:
                continue
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": alias,
                        "description": tool_definition["description"] or tool_definition["name"],
                        "parameters": tool_definition["parameters"],
                    },
                }
            )
            tool_lookup[alias] = {"server": server_definition, "tool": tool_definition}

    if tools and _is_debug_logging_enabled():
        selected_servers = []
        for server_id in server_ids:
            server_definition = get_server(server_id, engine=engine, model_name=model_name)
            if server_definition:
                selected_servers.append(server_definition["id"])

        _print_runtime_event(
            "Tool registry prepared: "
            f"engine={engine or 'unknown'}, "
            f"model={model_name or '(auto)'}, "
            f"servers={selected_servers or list(server_ids)}, "
            f"tools={len(tools)}"
        )
        if _is_trace_logging_enabled():
            aliases = ", ".join(sorted(tool_lookup.keys(), key=str.casefold))
            _print_runtime_event(f"Tool aliases: {aliases}")

    return tools, tool_lookup


# Execute tool callables.
# Run one async callable.
async def _run_async_callable(callable_fn, *args: Any) -> Any:
    """Execute an async callable with the provided arguments."""

    return await callable_fn(*args)

# Run one sync callable.
def _run_sync_callable(callable_fn, *args: Any) -> Any:
    """Execute a synchronous callable with the provided arguments."""

    return callable_fn(*args)

# Execute one callable safely.
def _execute_callable(callable_fn, *args: Any) -> Any:
    """Execute sync and async callables behind one shared helper."""

    if inspect.iscoroutinefunction(callable_fn):
        return _get_async_callable_runner().run(_run_async_callable(callable_fn, *args))

    return _run_sync_callable(callable_fn, *args)

# Dispatch one generic server handler.
def _dispatch_server_callable(
    callable_fn,
    tool_id: str,
    arguments: dict[str, Any],
    context: dict[str, Any],
) -> Any:
    """Call a generic server dispatcher with a tolerant signature strategy."""

    parameter_names = list(inspect.signature(callable_fn).parameters)

    # Accept older dispatchers that still use positional signatures instead of
    # the newer ``(tool_id, arguments, context)`` convention.
    if len(parameter_names) <= 1:
        return _execute_callable(callable_fn, arguments)

    if len(parameter_names) == 2:
        first_name = parameter_names[0].lower()
        if first_name in {"tool_id", "tool", "name", "tool_name"}:
            return _execute_callable(callable_fn, tool_id, arguments)

        return _execute_callable(callable_fn, arguments, context)

    return _execute_callable(callable_fn, tool_id, arguments, context)


# Serialize tool results.
# Serialize one tool result.
def _serialize_tool_result(result: Any) -> str:
    """Convert a tool result into text suitable for a model tool message."""

    if result is None:
        return "Tool returned no content."

    if isinstance(result, str):
        return result

    shared_file = _extract_shared_file_payload(result)
    if shared_file is not None:
        filename = str(shared_file.get("filename") or shared_file.get("name") or shared_file.get("path") or "file")
        return str(shared_file.get("model_context") or f"Shared file ready for download: {filename}")

    if isinstance(result, dict) and isinstance(result.get("model_context"), str):
        return result["model_context"]

    if isinstance(result, (dict, list, tuple, int, float, bool)):
        return json.dumps(result, ensure_ascii=False, indent=2)

    return str(result)


# Normalize tool result payloads.
# Parse JSON tool payloads returned as plain strings.
def _coerce_tool_result_object(result: Any) -> Any:
    """Parse JSON tool payloads returned as plain strings."""

    if not isinstance(result, str):
        return result
    text = result.strip()
    if not text.startswith("{"):
        return result
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return result
    return parsed if isinstance(parsed, dict) else result


# Return a normalized shared-file payload from direct or sandbox-wrapped results.
def _extract_shared_file_payload(result: Any) -> dict[str, Any] | None:
    """Return a normalized shared-file payload from direct or sandbox-wrapped results."""

    result = _coerce_tool_result_object(result)
    if not isinstance(result, dict):
        return None

    candidate: Any = result
    if result.get("tool") == "share_file" and isinstance(result.get("result"), dict):
        candidate = result["result"]
    elif result.get("kind") != "shared_file" and isinstance(result.get("file"), dict):
        candidate = result["file"]

    if not isinstance(candidate, dict) or candidate.get("kind") != "shared_file":
        return None

    path = str(candidate.get("path") or candidate.get("file") or "").strip()
    if not path:
        return None

    filename = str(
        candidate.get("filename")
        or candidate.get("name")
        or Path(path).name
        or "download"
    )
    payload = dict(candidate)
    payload["kind"] = "shared_file"
    payload["path"] = path
    payload["filename"] = filename
    if not payload.get("download_url") and not payload.get("downloadUrl"):
        host_path = str(payload.get("host_path") or "").strip()
        if host_path:
            payload["download_url"] = "/api/shared-file/download/?" + urlencode(
                {"path": host_path, "name": filename}
            )
    return payload


# Return frontend metadata for rich structured tool results.
def _extract_structured_tool_result(result: Any) -> dict[str, Any] | None:
    """Return frontend metadata for rich structured tool results."""

    result = _coerce_tool_result_object(result)
    if not isinstance(result, dict):
        return None
    shared_file = _extract_shared_file_payload(result)
    if shared_file is not None:
        return {
            "kind": "shared_file",
            "file": shared_file,
            "ui": {
                "kind": "shared_file",
                "status": "done",
                "file": shared_file,
            },
        }
    if not isinstance(result.get("model_context"), str):
        return None
    if not isinstance(result.get("ui"), dict) and not isinstance(result.get("sources"), list):
        return None
    return result


# Split one tool result into model-visible text and UI-only metadata.
def split_tool_result_payload(content: Any) -> tuple[str, dict[str, Any]]:
    """Split one tool result into model-visible text and UI-only metadata."""

    if isinstance(content, dict) and "_image_b64" in content:
        return f"[Image: {content.get('_path', 'image')}]", _image_tool_result_extras(content)

    structured = _extract_structured_tool_result(content)
    if isinstance(structured, dict):
        extras: dict[str, Any] = {"structured_content": structured}
        ui_payload = structured.get("ui")
        if isinstance(ui_payload, dict):
            extras["tool_ui"] = ui_payload
        return _serialize_tool_result(content), extras

    if isinstance(content, dict) and "_tool_result_content" in content:
        extras: dict[str, Any] = {}
        wrapped_structured = content.get("_tool_result_structured")
        if isinstance(wrapped_structured, dict):
            extras["structured_content"] = wrapped_structured
            ui_payload = wrapped_structured.get("ui")
            if isinstance(ui_payload, dict):
                extras["tool_ui"] = ui_payload
        return str(content.get("_tool_result_content") or ""), extras

    return _serialize_tool_result(content), {}


# Build UI-only metadata for an inline image tool result.
def _image_tool_result_extras(content: dict[str, Any]) -> dict[str, Any]:
    """Build UI-only metadata for an inline image tool result."""

    data_base64 = content.get("_image_b64")
    if not data_base64:
        return {}

    mime_type = str(content.get("_mime_type") or "image/png").strip().lower()
    if not mime_type or mime_type == "image":
        mime_type = "image/png"
    elif "/" not in mime_type:
        mime_type = f"image/{mime_type}"
    payload: dict[str, Any] = {
        "path": content.get("_path", ""),
        "kind": "image",
        "mime": mime_type,
        "preview": {
            "type": "inline_base64",
            "mime_type": mime_type,
            "data_base64": data_base64,
        },
    }
    for source_key, target_key in (
        ("_size_bytes", "size_bytes"),
        ("_width", "width"),
        ("_height", "height"),
    ):
        value = content.get(source_key)
        if value is not None:
            payload[target_key] = value

    return {
        "structured_content": payload,
        "tool_ui": {
            "image": payload,
        },
    }


# Extract one inline image payload.
def _extract_inline_image_payload(result: Any) -> dict[str, Any] | None:
    """Extract an Ollama image payload from the sandbox v2 read envelope."""

    if not isinstance(result, dict) or not result.get("ok"):
        return None

    payload = result.get("result")
    if not isinstance(payload, dict):
        return None

    preview = payload.get("preview")
    if not isinstance(preview, dict):
        return None

    data_base64 = preview.get("data_base64")
    if not data_base64:
        return None

    return {
        "_image_b64": data_base64,
        "_mime_type": preview.get("mime_type", payload.get("mime", "image/png")),
        "_path": payload.get("path", ""),
        "_size_bytes": payload.get("size_bytes"),
        "_width": payload.get("width"),
        "_height": payload.get("height"),
    }

# Execute one local tool.
def call_ollama_tool(
    tool_lookup: dict[str, dict[str, Any]],
    alias: str,
    arguments: dict[str, Any] | None,
    context: dict[str, Any] | None = None,
) -> str | dict:
    """Execute a local tool and serialize its result for Ollama.

    Returns a str for normal results, or a dict with ``_image_b64`` and
    ``_mime_type`` keys when the tool returns an image payload.
    """

    lookup_entry = tool_lookup.get(alias)
    if not lookup_entry:
        return f"Unknown tool: {alias}"

    server_definition = lookup_entry["server"]
    tool_definition = lookup_entry["tool"]
    call_arguments = arguments if isinstance(arguments, dict) else {}
    call_context = dict(context or {})

    # Fill the standard context expected by local tool handlers.
    call_context.setdefault("server_id", server_definition["id"])
    call_context.setdefault("server_name", server_definition["name"])
    call_context.setdefault("tool_id", tool_definition["id"])
    call_context.setdefault("tool_name", tool_definition["name"])
    call_context.setdefault("tool_alias", tool_definition["alias"])
    if not server_definition.get("user_mcp"):
        call_context.setdefault("server_file", str(server_definition["server_file"]))
    call_context.setdefault("tools_dir", str(TOOLS_DIR))
    started_at = time.perf_counter()

    if _is_debug_logging_enabled():
        _print_runtime_event(
            "Tool starting: "
            f"server={server_definition['id']}, "
            f"tool={tool_definition['id']}, "
            f"alias={tool_definition['alias']}, "
            f"context={_summarize_tool_context(call_context)}, "
            f"args={_preview_jsonish(call_arguments, limit=180)}"
        )

    try:
        if server_definition["id"] == "sandbox":
            skills_config.sync_skills_to_sandbox()

        if server_definition.get("user_mcp"):
            entry = server_definition["user_mcp_entry"]
            mcp_tool_name = str(tool_definition.get("mcp_tool_name") or tool_definition["id"] or "").strip()
            if not mcp_tool_name:
                return "Tool execution failed: missing MCP tool name"
            result = user_mcp_client.call_user_mcp_tool(entry, mcp_tool_name, call_arguments)
            if _is_debug_logging_enabled():
                _print_runtime_event(
                    "Tool completed: "
                    f"server={server_definition['id']}, "
                    f"tool={tool_definition['id']}, "
                    f"status=ok, "
                    f"took={time.perf_counter() - started_at:.2f}s, "
                    f"result={_summarize_tool_result(result)}"
                )
            return result

        if server_definition.get("external"):
            worker_context = json.loads(json.dumps(call_context, ensure_ascii=False, default=str))
            worker_payload = {
                "tool_id": tool_definition["id"],
                "arguments": call_arguments,
                "context": worker_context,
            }
            server_file = Path(server_definition["server_file"])
            try:
                result = _run_worker(
                    server_file,
                    "call",
                    worker_payload,
                    persistent=True,
                )
            except RuntimeError as worker_exc:
                if "Tool worker stopped" not in str(worker_exc):
                    raise
                logger.warning(
                    "Persistent tool worker stopped for %s; retrying call in one-shot mode.",
                    server_file,
                )
                result = _run_worker(
                    server_file,
                    "call",
                    worker_payload,
                    persistent=False,
                )
        else:
            handler = server_definition["tool_handlers"].get(tool_definition["id"])
            if handler is None:
                handler = server_definition["tool_handlers"].get(tool_definition["alias"])

            # Prefer a dedicated handler when present, then fall back to the
            # generic dispatcher exported by the server module.
            if handler is not None:
                signature = inspect.signature(handler)
                if len(signature.parameters) <= 1:
                    result = _execute_callable(handler, call_arguments)
                else:
                    result = _execute_callable(handler, call_arguments, call_context)
            elif server_definition["server_callable"] is not None:
                result = _dispatch_server_callable(
                    server_definition["server_callable"],
                    tool_definition["id"],
                    call_arguments,
                    call_context,
                )
            else:
                return f"Tool execution failed: no handler registered for {tool_definition['id']}"

        # Image payloads stay structured so multimodal adapters can feed them
        # back to the model without flattening them into plain text.
        image_payload = _extract_inline_image_payload(result)
        if image_payload is not None:
            if _is_debug_logging_enabled():
                _print_runtime_event(
                    "Tool completed: "
                    f"server={server_definition['id']}, "
                    f"tool={tool_definition['id']}, "
                    f"status=ok, "
                    f"took={time.perf_counter() - started_at:.2f}s, "
                    f"result={_summarize_tool_result(image_payload)}"
                )
            return image_payload

        if _is_debug_logging_enabled():
            _print_runtime_event(
                "Tool completed: "
                f"server={server_definition['id']}, "
                f"tool={tool_definition['id']}, "
                f"status=ok, "
                f"took={time.perf_counter() - started_at:.2f}s, "
                f"result={_summarize_tool_result(result)}"
            )
        structured_result = _extract_structured_tool_result(_coerce_tool_result_object(result))
        if structured_result is not None:
            return {
                "_tool_result_content": _serialize_tool_result(result),
                "_tool_result_structured": structured_result,
            }
        return _serialize_tool_result(result)
    except Exception as exc:
        logger.exception("Tool execution failed for %s.%s", server_definition["id"], tool_definition["id"])
        _print_runtime_event(
            "Tool failed: "
            f"server={server_definition['id']}, "
            f"tool={tool_definition['id']}, "
            f"status=error, "
            f"took={time.perf_counter() - started_at:.2f}s, "
            f"error={exc}"
        )
        return f"Tool execution failed: {exc}"
