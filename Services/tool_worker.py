# Copyright NGGT.LightKeeper. All Rights Reserved.

from __future__ import annotations

import asyncio
import contextlib
import importlib.util
import inspect
import json
import re
import sys
import threading
from pathlib import Path
from types import ModuleType
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

SERVER_DISPATCHER_NAMES = ("call_tool", "run_tool", "execute_tool", "execute")
SERVER_METADATA_NAMES = ("MCP_SERVER", "SERVER")
TOOL_HANDLER_NAMES = ("TOOL_HANDLERS", "TOOL_EXECUTORS")


class AsyncCallableRunner:
    """Run async tool handlers on one persistent event loop."""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._lock = threading.Lock()

    def _thread_main(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._ready.set()
        try:
            loop.run_forever()
        finally:
            loop.close()

    def ensure_started(self) -> None:
        if self._thread is not None and self._thread.is_alive() and self._loop is not None:
            return

        with self._lock:
            if self._thread is not None and self._thread.is_alive() and self._loop is not None:
                return

            self._ready.clear()
            self._thread = threading.Thread(
                target=self._thread_main,
                name="aslm-tool-worker-async-runner",
                daemon=True,
            )
            self._thread.start()
            self._ready.wait()

    def run(self, coro: Any) -> Any:
        self.ensure_started()
        assert self._loop is not None
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()

    def close(self) -> None:
        loop = self._loop
        thread = self._thread
        self._loop = None
        self._thread = None
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(loop.stop)
        if thread is not None and thread.is_alive():
            thread.join(timeout=3)


_ASYNC_CALLABLE_RUNNER = AsyncCallableRunner()


# Normalize public identifiers.
def _slugify(value: str) -> str:
    """Return a stable lower-case identifier."""

    normalized = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")
    return normalized or "tool"


# Load one server module from disk.
def _load_module(server_file: Path) -> ModuleType:
    """Load one tool server module."""

    server_root = server_file.parent
    if str(server_root) not in sys.path:
        sys.path.insert(0, str(server_root))

    module_name = f"aslm_chat_worker_{_slugify(server_root.name)}"
    spec = importlib.util.spec_from_file_location(module_name, server_file)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load MCP server module from {server_file}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Return one exported metadata dictionary.
def _server_metadata(module: ModuleType, folder_name: str) -> dict[str, Any]:
    """Return normalized server metadata."""

    raw_server: Any = {}
    for attr_name in SERVER_METADATA_NAMES:
        raw_server = getattr(module, attr_name, None)
        if raw_server is not None:
            break

    if raw_server is None:
        raw_server = {}
    if not isinstance(raw_server, dict):
        raise ValueError("MCP server module must expose an MCP_SERVER dictionary")

    return {
        "id": _slugify(str(raw_server.get("id") or folder_name)),
        "name": str(raw_server.get("name") or folder_name).strip() or folder_name,
        "description": str(raw_server.get("description") or "").strip(),
    }


# Normalize one tool schema.
def _normalize_schema(schema: Any) -> dict[str, Any]:
    """Return a JSON-schema-like mapping."""

    if not isinstance(schema, dict):
        return {"type": "object", "properties": {}}

    normalized = dict(schema)
    normalized.setdefault("type", "object")
    normalized.setdefault("properties", {})
    if not isinstance(normalized.get("properties"), dict):
        normalized["properties"] = {}
    return normalized


# Return normalized tool definitions.
def _server_tools(module: ModuleType, server_id: str) -> list[dict[str, Any]]:
    """Return normalized tools exported by one server module."""

    raw_tools = getattr(module, "TOOLS", None)
    if raw_tools is None:
        legacy_tool = getattr(module, "TOOL", None)
        raw_tools = [legacy_tool] if isinstance(legacy_tool, dict) else None

    if not isinstance(raw_tools, list) or not raw_tools:
        raise ValueError("MCP server module must expose a non-empty TOOLS list")

    tools: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw_tool in enumerate(raw_tools, start=1):
        if not isinstance(raw_tool, dict):
            continue

        tool_id = _slugify(str(raw_tool.get("id") or f"tool_{index}"))
        if tool_id in seen_ids:
            continue

        seen_ids.add(tool_id)
        tools.append(
            {
                "id": tool_id,
                "alias": f"{server_id}__{tool_id}",
                "name": str(raw_tool.get("name") or tool_id).strip() or tool_id,
                "description": str(raw_tool.get("description") or "").strip(),
                "parameters": _normalize_schema(raw_tool.get("parameters")),
            }
        )

    return tools


# Return per-tool handlers.
def _tool_handlers(module: ModuleType) -> dict[str, Any]:
    """Return explicit tool handlers exported by one module."""

    raw_handlers: Any = None
    for attr_name in TOOL_HANDLER_NAMES:
        raw_handlers = getattr(module, attr_name, None)
        if raw_handlers is not None:
            break

    if not isinstance(raw_handlers, dict):
        return {}

    return {
        _slugify(str(raw_key or "")): raw_value
        for raw_key, raw_value in raw_handlers.items()
        if callable(raw_value)
    }


# Return a generic dispatcher when available.
def _server_callable(module: ModuleType):
    """Return the generic tool dispatcher exported by one module."""

    for attr_name in SERVER_DISPATCHER_NAMES:
        candidate = getattr(module, attr_name, None)
        if callable(candidate):
            return candidate
    return None


# Run one callable.
def _execute_callable(callable_fn, *args: Any) -> Any:
    """Execute sync and async callables."""

    if inspect.iscoroutinefunction(callable_fn):
        return _ASYNC_CALLABLE_RUNNER.run(callable_fn(*args))
    return callable_fn(*args)


# Dispatch a generic server callable.
def _dispatch_server_callable(callable_fn, tool_id: str, arguments: dict[str, Any], context: dict[str, Any]) -> Any:
    """Call a generic dispatcher with a tolerant signature strategy."""

    parameter_names = list(inspect.signature(callable_fn).parameters)
    if len(parameter_names) <= 1:
        return _execute_callable(callable_fn, arguments)
    if len(parameter_names) == 2:
        first_name = parameter_names[0].lower()
        if first_name in {"tool_id", "tool", "name", "tool_name"}:
            return _execute_callable(callable_fn, tool_id, arguments)
        return _execute_callable(callable_fn, arguments, context)
    return _execute_callable(callable_fn, tool_id, arguments, context)


# Convert arbitrary values to JSON-compatible data.
def _to_jsonable(value: Any) -> Any:
    """Return a JSON-compatible representation."""

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _to_jsonable(child) for key, child in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_jsonable(child) for child in value]

    text = getattr(value, "text", None)
    if text is not None:
        return str(text)

    return str(value)


# Describe one tool server.
def describe(server_file: Path) -> dict[str, Any]:
    """Return public metadata for one tool server."""

    module = _load_module(server_file)
    metadata = _server_metadata(module, server_file.parent.name)
    metadata["tools"] = _server_tools(module, metadata["id"])
    return metadata


# Check whether one tool server supports the current runtime.
def supports(server_file: Path, payload: dict[str, Any]) -> bool:
    """Return whether the server supports one engine/model pair."""

    module = _load_module(server_file)
    supports_fn = getattr(module, "supports", None)
    if not callable(supports_fn):
        return True

    engine = payload.get("engine")
    model_name = payload.get("model_name")
    try:
        return bool(supports_fn(engine=engine, model_name=model_name))
    except TypeError:
        return bool(supports_fn(engine, model_name))


# Call one tool.
def call(server_file: Path, payload: dict[str, Any]) -> Any:
    """Execute one tool call."""

    module = _load_module(server_file)
    tool_id = _slugify(str(payload.get("tool_id") or ""))
    arguments = payload.get("arguments") if isinstance(payload.get("arguments"), dict) else {}
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}

    handlers = _tool_handlers(module)
    handler = handlers.get(tool_id)
    if handler is not None:
        signature = inspect.signature(handler)
        if len(signature.parameters) <= 1:
            return _execute_callable(handler, arguments)
        return _execute_callable(handler, arguments, context)

    dispatcher = _server_callable(module)
    if dispatcher is None:
        raise ValueError(f"No handler registered for tool '{tool_id}'.")

    return _dispatch_server_callable(dispatcher, tool_id, arguments, context)


# Print one JSON response.
def _print_response(ok: bool, payload: Any, *, output=sys.stdout) -> int:
    """Print a JSON worker envelope."""

    key = "result" if ok else "error"
    print(json.dumps({"ok": ok, key: _to_jsonable(payload)}, ensure_ascii=False), file=output)
    output.flush()
    return 0 if ok else 1


# Execute one request for persistent worker mode.
def _execute_request(operation: str, server_file: Path, payload: dict[str, Any]) -> tuple[bool, Any]:
    """Return one worker envelope payload without printing it."""

    try:
        if operation == "describe":
            return True, describe(server_file)
        if operation == "supports":
            return True, supports(server_file, payload)
        if operation == "call":
            return True, call(server_file, payload)
        return False, f"Unknown worker operation: {operation}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


# Serve newline-delimited worker requests until stdin closes.
def serve(server_file: Path) -> int:
    """Run a persistent worker process for stateful tool servers."""

    output = sys.stdout
    try:
        for raw_line in sys.stdin:
            raw_line = raw_line.strip()
            if not raw_line:
                continue

            try:
                request = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                ok, payload = False, f"JSONDecodeError: {exc}"
            else:
                if not isinstance(request, dict):
                    ok, payload = False, "Worker request must be a JSON object."
                else:
                    operation = str(request.get("operation") or "").strip().lower()
                    request_payload = request.get("payload")
                    if not isinstance(request_payload, dict):
                        request_payload = {}
                    with contextlib.redirect_stdout(sys.stderr):
                        ok, payload = _execute_request(operation, server_file, request_payload)

            key = "result" if ok else "error"
            print(json.dumps({"ok": ok, key: _to_jsonable(payload)}, ensure_ascii=False), file=output, flush=True)
    finally:
        _ASYNC_CALLABLE_RUNNER.close()

    return 0


# CLI entry point.
def main() -> int:
    """Run the tool worker command."""

    if len(sys.argv) < 3:
        return _print_response(False, "Usage: tool_worker.py <describe|supports|call> <server_file>")

    operation = sys.argv[1].strip().lower()
    server_file = Path(sys.argv[2]).resolve()
    if operation == "serve":
        return serve(server_file)

    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    try:
        output = sys.stdout
        with contextlib.redirect_stdout(sys.stderr):
            ok, response_payload = _execute_request(operation, server_file, payload)
        return _print_response(ok, response_payload, output=output)
    except Exception as exc:
        return _print_response(False, f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
