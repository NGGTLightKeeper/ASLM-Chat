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
from pathlib import Path
from types import ModuleType
from typing import Any

from Settings import settings as runtime_settings

logger = logging.getLogger(__name__)

TOOLS_DIR = Path(__file__).resolve().parent.parent / "Tools"
SERVER_FILENAME = "mcp-server.py"
WORKER_FILE = Path(__file__).resolve().parent.parent / "Services" / "tool_worker.py"
SERVER_DISPATCHER_NAMES = ("call_tool", "run_tool", "execute_tool", "execute")
SERVER_METADATA_NAMES = ("MCP_SERVER", "SERVER")
TOOL_HANDLER_NAMES = ("TOOL_HANDLERS", "TOOL_EXECUTORS")

_SERVER_CACHE_SIGNATURE: tuple[tuple[str, int], ...] | None = None
_SERVER_CACHE: dict[str, dict[str, Any]] = {}
_WORKER_SESSION_LOCK = threading.Lock()
_WORKER_SESSIONS: dict[str, "ExternalWorkerSession"] = {}


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


# Persistent external tool worker.
class ExternalWorkerSession:
    """Keep one isolated tool worker process alive for stateful servers."""

    def __init__(self, server_file: Path, python_path: Path) -> None:
        self.server_file = server_file
        self.python_path = python_path
        self.process: subprocess.Popen[str] | None = None
        self.lock = threading.Lock()

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

    def request(self, operation: str, payload: dict[str, Any] | None = None) -> Any:
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
                    raw_response = self.process.stdout.readline()
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

    def close(self) -> None:
        """Stop the worker process if it is running."""

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



# Manage the server discovery cache.
# Clear the cached registry.
def reset_cache() -> None:
    """Clear cached discovery so local edits are picked up immediately."""

    global _SERVER_CACHE_SIGNATURE, _SERVER_CACHE

    _SERVER_CACHE_SIGNATURE = None
    _SERVER_CACHE = {}


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
        return _get_worker_session(server_file).request(operation, payload)

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



# Expose the server registry.
# Refresh the server registry.
def _ensure_registry_loaded() -> dict[str, dict[str, Any]]:
    """Discover and cache valid local MCP-style server modules."""

    global _SERVER_CACHE_SIGNATURE, _SERVER_CACHE

    signature = _server_signature()
    # The cache is keyed by file mtimes so local edits become visible without
    # forcing a full rediscovery on every call.
    if signature == _SERVER_CACHE_SIGNATURE:
        return _SERVER_CACHE

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
    return {
        "id": server_definition["id"],
        "name": server_definition["name"],
        "description": server_definition["description"],
        "tool_count": len(tools),
        "tools": tools,
    }

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
        return asyncio.run(_run_async_callable(callable_fn, *args))

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

    if isinstance(result, dict) and isinstance(result.get("model_context"), str):
        return result["model_context"]

    if isinstance(result, (dict, list, tuple, int, float, bool)):
        return json.dumps(result, ensure_ascii=False, indent=2)

    return str(result)


def _extract_structured_tool_result(result: Any) -> dict[str, Any] | None:
    """Return frontend metadata for rich structured tool results."""

    if not isinstance(result, dict):
        return None
    if not isinstance(result.get("model_context"), str):
        return None
    if not isinstance(result.get("ui"), dict) and not isinstance(result.get("sources"), list):
        return None
    return result


def split_tool_result_payload(content: Any) -> tuple[str, dict[str, Any]]:
    """Split one tool result into model-visible text and UI-only metadata."""

    if isinstance(content, dict) and "_image_b64" in content:
        return f"[Image: {content.get('_path', 'image')}]", {}

    if isinstance(content, dict) and "_tool_result_content" in content:
        extras: dict[str, Any] = {}
        structured = content.get("_tool_result_structured")
        if isinstance(structured, dict):
            extras["structured_content"] = structured
            ui_payload = structured.get("ui")
            if isinstance(ui_payload, dict):
                extras["tool_ui"] = ui_payload
        return str(content.get("_tool_result_content") or ""), extras

    return _serialize_tool_result(content), {}


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
        structured_result = _extract_structured_tool_result(result)
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
