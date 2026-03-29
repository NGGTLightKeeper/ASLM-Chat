# Copyright NGGT.LightKeeper. All Rights Reserved.

from __future__ import annotations

import logging
import os
import re
import shlex
import signal
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from Settings import settings

logger = logging.getLogger(__name__)

_ollama_process: subprocess.Popen | None = None
_log_stream_thread: threading.Thread | None = None
_log_stream_lock = threading.Lock()
PID_FILE = Path(__file__).resolve().parent.parent / "Settings" / "ollama-service.pid"
LOG_FILE = Path(__file__).resolve().parent.parent / "Settings" / "ollama-service.log"
ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
LOG_POLL_INTERVAL = 0.5
RECENT_LOG_LINE_COUNT = 80
MAX_CONSOLE_LINE_LENGTH = 220
SERVER_CONFIG_ENV_KEYS = (
    "OLLAMA_HOST",
    "OLLAMA_MODELS",
    "OLLAMA_KEEP_ALIVE",
    "OLLAMA_LOAD_TIMEOUT",
    "OLLAMA_NUM_PARALLEL",
    "OLLAMA_MAX_QUEUE",
    "OLLAMA_CONTEXT_LENGTH",
)


@dataclass(frozen=True)
class OllamaDesiredState:
    """Describe whether the managed Ollama runtime should currently be active."""

    requested_engine: str
    active_engine: str
    is_enabled: bool
    should_run: bool


# Read saved service PID
def _read_pid() -> int | None:
    """Return the saved Ollama PID when it exists."""

    try:
        raw_value = PID_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return None

    if not raw_value:
        return None

    try:
        return int(raw_value)
    except ValueError:
        return None


# Save service PID
def _write_pid(pid: int) -> None:
    """Persist the managed Ollama PID on disk."""

    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(pid), encoding="utf-8")


# Delete saved service PID
def _clear_pid() -> None:
    """Remove the saved Ollama PID file."""

    try:
        PID_FILE.unlink()
    except OSError:
        pass


# Check saved process state
def _is_pid_running(pid: int | None) -> bool:
    """Return whether the given PID still points to a live process."""

    if not pid:
        return False

    try:
        os.kill(pid, 0)
    except (OSError, SystemError):
        return False

    return True


# Read desired runtime state
def _get_desired_state(requested_engine: str | None = None) -> OllamaDesiredState:
    """Return whether the managed Ollama runtime should currently be running."""

    active_engine = settings.get_llm_engine()
    resolved_engine = settings.normalize_engine_name(requested_engine or active_engine)
    is_enabled = bool(settings.get("ollama-service", False))
    should_run = settings.is_ollama_engine(resolved_engine) and is_enabled
    return OllamaDesiredState(
        requested_engine=resolved_engine,
        active_engine=active_engine,
        is_enabled=is_enabled,
        should_run=should_run,
    )


# Build service environment
def _build_service_environment() -> tuple[dict[str, str], int]:
    """Return the environment variables used to launch the managed Ollama service."""

    ollama_models = settings.get("ollama-service_models")
    ollama_port = int(settings.get("ollama-service_port", 30002))

    env = os.environ.copy()
    env["OLLAMA_HOST"] = f"127.0.0.1:{ollama_port}"
    if ollama_models:
        env["OLLAMA_MODELS"] = str(ollama_models)
    else:
        env.pop("OLLAMA_MODELS", None)

    return env, ollama_port


# Sanitize one console line
def _sanitize_console_line(message: str) -> str:
    """Strip ANSI escapes and trailing line breaks for ASLM console rendering."""

    cleaned = ANSI_ESCAPE_RE.sub("", message)
    return cleaned.rstrip("\r\n")


def _truncate_console_line(message: str, limit: int = MAX_CONSOLE_LINE_LENGTH) -> str:
    """Trim long console lines so ASLM stays readable."""

    if settings.is_console_trace_enabled():
        limit = max(limit, 900)
    elif settings.is_console_debug_enabled():
        limit = max(limit, 420)

    if len(message) <= limit:
        return message
    return f"{message[:max(0, limit - 3)].rstrip()}..."


def _parse_structured_log_fields(message: str) -> dict[str, str]:
    """Parse Ollama's key=value log format into a dictionary."""

    try:
        tokens = shlex.split(message, posix=True)
    except ValueError:
        return {}

    fields: dict[str, str] = {}
    for token in tokens:
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        normalized_key = key.strip().strip('"')
        if not normalized_key:
            continue
        fields[normalized_key] = value

    return fields


def _extract_env_value(env_blob: str, env_key: str) -> str:
    """Extract one environment variable value from Ollama's server-config dump."""

    match = re.search(rf"{re.escape(env_key)}:([^ ]+)", env_blob)
    if not match:
        return ""
    return match.group(1).strip()


def _collect_remaining_field_details(
    fields: dict[str, str],
    *,
    excluded_keys: set[str] | None = None,
    max_items: int | None = None,
) -> list[str]:
    """Return extra structured-log fields formatted as key=value details."""

    excluded = {"time", "level", "source", "msg"}
    if excluded_keys:
        excluded |= set(excluded_keys)

    details: list[str] = []
    for key in sorted(fields, key=str.casefold):
        if key in excluded:
            continue
        value = str(fields.get(key, "") or "").strip()
        if not value:
            continue
        details.append(f"{key}={value}")
        if max_items is not None and len(details) >= max_items:
            break

    return details


def _summarize_load_request(request_blob: str) -> list[str]:
    """Extract useful runner load-request fields from Ollama trace lines."""

    details: list[str] = []
    patterns = {
        "operation": r"Operation:([A-Za-z0-9_]+)",
        "parallel": r"Parallel:([0-9]+)",
        "batch": r"BatchSize:([0-9]+)",
        "flash": r"FlashAttention:([A-Za-z]+)",
        "kv": r"KvSize:([0-9]+)",
        "threads": r"NumThreads:([0-9]+)",
        "gpu_layers": r"GPULayers:([^ ]+)",
    }
    for label, pattern in patterns.items():
        match = re.search(pattern, request_blob)
        if match:
            details.append(f"{label}={match.group(1)}")

    return details


def _format_gin_line(message: str) -> str | None:
    """Convert GIN access logs into a compact summary."""

    match = re.search(
        r'\[GIN\]\s+\S+\s+-\s+\S+\s+\|\s+(\d+)\s+\|\s+([^|]+?)\s+\|\s+([^|]+?)\s+\|\s+([A-Z]+)\s+"([^"]+)"',
        message,
    )
    if not match:
        return None

    status_code, duration, client_ip, method, path = (
        match.group(1),
        match.group(2).strip(),
        match.group(3).strip(),
        match.group(4).strip(),
        match.group(5).strip(),
    )
    return _truncate_console_line(
        f"[Ollama][HTTP] {method} {path} -> {status_code} in {duration} from {client_ip}"
    )


def _format_backend_line(message: str) -> str:
    """Convert backend loader logs into a shorter, more useful summary."""

    backend_path = message.partition(" from ")[2].strip()
    if backend_path:
        backend_name = Path(backend_path).name
        return _truncate_console_line(f"[Ollama][Backend] {message.partition(': ')[2].split(' from ')[0]} ({backend_name})")
    return _truncate_console_line(f"[Ollama][Backend] {message}")


def _format_structured_ollama_line(message: str) -> str | None:
    """Convert Ollama structured logs into concise console lines."""

    fields = _parse_structured_log_fields(message)
    if not fields:
        return None

    level = fields.get("level", "INFO").upper()
    source = fields.get("source", "")
    raw_message = fields.get("msg", "").strip()
    trace_enabled = settings.is_console_trace_enabled()
    if not raw_message and not trace_enabled:
        source_key = source.casefold()
        if "cpu_windows.go" in source_key:
            raw_message = "CPU topology"
        elif "ggml.go:136" in source_key:
            raw_message = "Model metadata"
        elif "ggml.go:104" in source_key:
            raw_message = "System capabilities"
        elif "runner.go:1284" in source_key:
            raw_message = "Load request"
        elif "types.go:42" in source_key:
            raw_message = "Inference compute"
        else:
            return None
    elif not raw_message:
        raw_message = "Trace event"

    summary = raw_message
    details: list[str] = []

    if raw_message == "server config":
        env_blob = fields.get("env", "")
        for env_key in SERVER_CONFIG_ENV_KEYS:
            env_value = _extract_env_value(env_blob, env_key)
            if env_value:
                details.append(f"{env_key.removeprefix('OLLAMA_').lower()}={env_value}")
        summary = "Server config"
    elif raw_message == "starting runner":
        command = fields.get("cmd", "")
        port_match = re.search(r"--port\s+(\d+)", command)
        model_match = re.search(r"--model\s+([^\s]+)", command)
        if port_match:
            details.append(f"port={port_match.group(1)}")
        if model_match:
            details.append(f"model={Path(model_match.group(1)).name}")
        elif command:
            details.append("runner=bootstrap")
        summary = "Starting runner"
    elif raw_message == "discovering available GPUs...":
        summary = "Discovering available GPUs"
    elif raw_message == "inference compute":
        gpu_name = fields.get("name") or fields.get("description")
        if gpu_name:
            details.append(f"gpu={gpu_name}")
        if fields.get("library"):
            details.append(f"backend={fields['library']}")
        if fields.get("available"):
            details.append(f"vram_free={fields['available']}")
        if fields.get("total"):
            details.append(f"vram_total={fields['total']}")
        summary = "Inference compute"
    elif raw_message == "vram-based default context":
        if fields.get("default_num_ctx"):
            details.append(f"default_ctx={fields['default_num_ctx']}")
        if fields.get("total_vram"):
            details.append(f"total_vram={fields['total_vram']}")
        summary = "VRAM-based default context"
    elif raw_message == "gpu memory":
        for key, label in (("available", "available"), ("free", "free"), ("minimum", "minimum"), ("id", "gpu")):
            value = fields.get(key)
            if value:
                details.append(f"{label}={value}")
        summary = "GPU memory"
    elif raw_message == "system memory":
        for key in ("total", "free", "free_swap"):
            value = fields.get(key)
            if value:
                details.append(f"{key}={value}")
        summary = "System memory"
    elif raw_message == "loading model":
        if fields.get("model layers"):
            details.append(f"layers={fields['model layers']}")
        if fields.get("requested"):
            details.append(f"requested={fields['requested']}")
        summary = "Loading model"
    elif raw_message == "Load request" or (source == "runner.go:1284" and fields.get("request")):
        details.extend(_summarize_load_request(fields.get("request", "")))
        summary = "Load request"
    elif raw_message == "Model metadata" or source == "ggml.go:136":
        for key in ("architecture", "file_type", "num_tensors", "num_key_values"):
            value = fields.get(key)
            if value:
                details.append(f"{key}={value}")
        summary = "Model metadata"
    elif raw_message == "System capabilities" or source == "ggml.go:104":
        compiler = fields.get("compiler")
        if compiler:
            details.append(f"compiler={compiler}")
        cpu_flags = []
        for candidate in ("CPU.0.AVX2", "CPU.0.AVX512", "CPU.0.FMA", "CPU.0.F16C"):
            if fields.get(candidate) == "1":
                cpu_flags.append(candidate.split(".")[-1])
        if cpu_flags:
            details.append(f"cpu_flags={','.join(cpu_flags)}")
        cuda_archs = fields.get("CUDA.0.ARCHS")
        if cuda_archs:
            details.append(f"cuda_archs={cuda_archs}")
        summary = "System capabilities"
    elif raw_message == "CPU topology" or source == "cpu_windows.go:195":
        for key in ("package", "cores", "efficiency", "threads"):
            value = fields.get(key)
            if value:
                details.append(f"{key}={value}")
        summary = "CPU topology"
    elif raw_message == "waiting for server to become available":
        if fields.get("status"):
            details.append(f"status={fields['status']}")
        summary = "Waiting for model runner"
    elif raw_message == "waiting for llama runner to start responding":
        summary = "Waiting for llama runner"
    elif raw_message == "loaded runners":
        if fields.get("count"):
            details.append(f"count={fields['count']}")
        summary = "Loaded runners"
    elif raw_message == "invalid option provided":
        if fields.get("option"):
            details.append(f"option={fields['option']}")
        summary = "Invalid option ignored"
    elif raw_message == "Listening on 127.0.0.1:30002 (version 0.18.3)":
        summary = raw_message
    else:
        for key, label in (
            ("status", "status"),
            ("count", "count"),
            ("size", "size"),
            ("device", "device"),
            ("available", "available"),
            ("total", "total"),
        ):
            value = fields.get(key)
            if value:
                details.append(f"{label}={value}")

    if trace_enabled:
        trace_details = _collect_remaining_field_details(
            fields,
            excluded_keys={"env"} | {detail.split("=", 1)[0] for detail in details if "=" in detail},
            max_items=10,
        )
        for item in trace_details:
            if item not in details:
                details.append(item)

    source_suffix = f"[{source}]" if source else ""
    rendered = f"[Ollama][{level}]{source_suffix} {summary}"
    if details:
        rendered = f"{rendered} | {', '.join(details)}"

    return _truncate_console_line(rendered)


def _format_console_log_line(message: str) -> str | None:
    """Convert raw Ollama output into a readable console line."""

    if not message:
        return None

    if message.startswith("[GIN]"):
        return _format_gin_line(message) or _truncate_console_line(f"[Ollama] {message}")
    if message.startswith("load_backend:"):
        return _format_backend_line(message)
    if message.startswith("ggml_cuda_init:"):
        return _truncate_console_line(f"[Ollama][CUDA] {message.partition(': ')[2] or message}")
    if message.startswith("Device "):
        return _truncate_console_line(f"[Ollama][CUDA] {message}")

    formatted = _format_structured_ollama_line(message)
    if formatted:
        return formatted

    return _truncate_console_line(f"[Ollama] {message}")


# Print watcher status
def _print_status(message: str) -> None:
    """Emit one watcher status line."""

    print(f"[ASLM-Chat] {message}", flush=True)


# Read recent service log lines
def _read_recent_log_lines(limit: int = RECENT_LOG_LINE_COUNT) -> list[str]:
    """Return the latest non-empty log lines from the managed Ollama log file."""

    if not LOG_FILE.exists():
        return []

    recent_lines: deque[str] = deque(maxlen=max(1, limit))

    try:
        with LOG_FILE.open("r", encoding="utf-8", errors="replace") as file:
            for raw_line in file:
                line = _sanitize_console_line(raw_line)
                if line:
                    recent_lines.append(line)
    except OSError:
        return []

    return list(recent_lines)


# Stream new log lines
def _stream_new_log_lines(position: int) -> int:
    """Print all new managed Ollama log lines since the given file offset."""

    if not LOG_FILE.exists():
        return 0

    try:
        file_size = LOG_FILE.stat().st_size
    except OSError:
        return position

    if file_size < position:
        position = 0

    try:
        with LOG_FILE.open("r", encoding="utf-8", errors="replace") as file:
            file.seek(position)
            while True:
                raw_line = file.readline()
                if raw_line == "":
                    break

                line = _sanitize_console_line(raw_line)
                rendered_line = _format_console_log_line(line)
                if rendered_line:
                    print(rendered_line, flush=True)

            return file.tell()
    except OSError:
        return position


# Stream log file in the background
def _stream_log_file_forever() -> None:
    """Mirror managed Ollama log lines into the current process stdout."""

    last_pid: int | None = None
    log_position = 0

    while True:
        tracked_pid = _read_pid()
        is_running = _is_pid_running(tracked_pid)

        if is_running and tracked_pid:
            if tracked_pid != last_pid:
                recent_lines = _read_recent_log_lines()
                _print_status(f"Streaming Ollama logs for PID {tracked_pid}...")
                for line in recent_lines:
                    rendered_line = _format_console_log_line(line)
                    if rendered_line:
                        print(rendered_line, flush=True)
                try:
                    log_position = LOG_FILE.stat().st_size
                except OSError:
                    log_position = 0
                last_pid = tracked_pid

            log_position = _stream_new_log_lines(log_position)
        else:
            if last_pid is not None:
                log_position = _stream_new_log_lines(log_position)
                _print_status(f"Managed Ollama service stopped (last PID: {last_pid}).")
                last_pid = None
                log_position = 0

        time.sleep(LOG_POLL_INTERVAL)


# Ensure background log streaming
def _ensure_log_streaming() -> None:
    """Start a single background thread that forwards Ollama logs to stdout."""

    global _log_stream_thread

    with _log_stream_lock:
        if _log_stream_thread is not None and _log_stream_thread.is_alive():
            return

        _log_stream_thread = threading.Thread(
            target=_stream_log_file_forever,
            name="aslm-chat-ollama-log-stream",
            daemon=True,
        )
        _log_stream_thread.start()


# Wait for HTTP readiness
def _wait_until_ready(timeout_seconds: float = 15.0) -> bool:
    """Wait until the local Ollama HTTP endpoint starts responding."""

    deadline = time.time() + timeout_seconds
    host = settings.get_engine_url("ollama-service")
    version_url = f"{host.rstrip('/')}/api/version"

    while time.time() < deadline:
        try:
            with urlopen(version_url, timeout=1.5) as response:
                if response.status < 500:
                    return True
        except (OSError, URLError):
            time.sleep(0.25)

    return False


def _wait_for_existing_runtime(timeout_seconds: float = 2.0) -> bool:
    """Give a separately launched Ollama runtime a short chance to appear."""

    deadline = time.time() + max(0.0, timeout_seconds)
    while time.time() < deadline:
        tracked_pid = _read_pid()
        if tracked_pid and _is_pid_running(tracked_pid):
            return True
        if _wait_until_ready(timeout_seconds=0.25):
            return True
        time.sleep(0.1)

    return False


def _is_running_inside_aslm() -> bool:
    """Return whether the current process is launched by ASLM module infrastructure."""

    return bool(os.environ.get("ASLM_MODULE_ID") or os.environ.get("ASLM_MODULE_DIR"))


# Start managed service
def start_ollama(engine: str | None = None) -> bool:
    """Start the local Ollama service when the active engine requires it."""

    global _ollama_process

    desired_state = _get_desired_state(engine)
    if not desired_state.should_run:
        return False

    if _wait_for_existing_runtime(timeout_seconds=1.5):
        tracked_pid = _read_pid()
        if tracked_pid and _is_pid_running(tracked_pid):
            logger.info("Ollama service is already running (PID: %s)", tracked_pid)
        else:
            logger.info("Ollama service is already reachable on the configured port.")
        return True

    if _is_running_inside_aslm():
        logger.info("Waiting for dedicated Ollama runtime process to become ready inside ASLM.")
        if _wait_until_ready(timeout_seconds=8.0):
            logger.info("Dedicated Ollama runtime became reachable on the configured port.")
            return True

        _print_status("Dedicated Ollama runtime is not ready yet. Starting fallback local Ollama process...")

    tracked_pid = _read_pid()
    if tracked_pid and _is_pid_running(tracked_pid):
        logger.info("Ollama service is already running (PID: %s)", tracked_pid)
        return True

    ollama_path = settings.get("ollama-service_path")
    if not ollama_path or not os.path.exists(ollama_path):
        _print_status(f"Ollama service is enabled but not found at: {ollama_path}")
        return False

    env, ollama_port = _build_service_environment()
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    _ensure_log_streaming()

    _print_status(f"Starting local Ollama service on port {ollama_port}...")
    _print_status(
        "Ollama runtime configured: "
        f"host={env.get('OLLAMA_HOST', f'127.0.0.1:{ollama_port}')}, "
        f"models={env.get('OLLAMA_MODELS', '(default)')}"
    )

    try:
        if os.name == "nt":
            creationflags = (
                getattr(subprocess, "CREATE_NO_WINDOW", 0)
                | getattr(subprocess, "DETACHED_PROCESS", 0)
            )
        else:
            creationflags = 0
        with LOG_FILE.open("w", encoding="utf-8", errors="replace") as log_handle:
            _ollama_process = subprocess.Popen(
                [ollama_path, "serve"],
                env=env,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                creationflags=creationflags,
            )

        _write_pid(_ollama_process.pid)

        if not _wait_until_ready():
            logger.warning("Ollama process started but the HTTP endpoint did not become ready in time.")
            _print_status(f"Ollama service started (PID: {_ollama_process.pid}) but did not become ready in time.")
        else:
            _print_status(f"Ollama service started successfully (PID: {_ollama_process.pid})")

        return True
    except Exception as exc:
        _ollama_process = None
        _clear_pid()
        _print_status(f"Failed to start Ollama service: {exc}")
        return False


def run_ollama_runtime(log: bool = False) -> int:
    """Replace the current process with ``ollama serve`` for a dedicated ASLM console session."""

    desired_state = _get_desired_state("ollama-service")
    if not desired_state.is_enabled:
        _print_status("Ollama runtime command skipped: ollama-service is not enabled.")
        return 0

    ollama_path = settings.get("ollama-service_path")
    if not ollama_path or not os.path.exists(ollama_path):
        _print_status(f"Ollama runtime command failed: executable not found at {ollama_path}")
        return 1

    env, ollama_port = _build_service_environment()
    _write_pid(os.getpid())

    if log:
        _print_status(f"Launching dedicated Ollama runtime on port {ollama_port}...")
    _print_status(
        "Ollama runtime configured: "
        f"host={env.get('OLLAMA_HOST', f'127.0.0.1:{ollama_port}')}, "
        f"models={env.get('OLLAMA_MODELS', '(default)')}"
    )

    try:
        os.execvpe(ollama_path, [ollama_path, "serve"], env)
    except Exception as exc:
        _clear_pid()
        _print_status(f"Failed to launch dedicated Ollama runtime: {exc}")
        return 1


# Stop managed service
def stop_ollama() -> None:
    """Stop the managed Ollama service when a tracked PID exists."""

    global _ollama_process

    pid = _read_pid()
    if not pid:
        _ollama_process = None
        return

    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            os.kill(pid, signal.SIGTERM)
    except OSError:
        logger.info("Managed Ollama process %s was already stopped.", pid)
    finally:
        _ollama_process = None
        _clear_pid()


# Watch managed service and stream logs
def run_ollama_console(log: bool = False) -> None:
    """Stream the managed Ollama log file into stdout."""

    del log  # Reserved for future verbosity controls.
    _print_status("Ollama log streaming is active.")
    _stream_log_file_forever()
