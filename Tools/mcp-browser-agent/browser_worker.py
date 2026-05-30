# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


SERVER_ROOT = Path(__file__).resolve().parent
MCP_SERVER_PATH = SERVER_ROOT / "mcp-server.py"
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))


# Load the MCP server module from the sibling mcp-server.py file.
def _load_mcp_server_module():
    spec = importlib.util.spec_from_file_location("browser_agent_worker_mcp_server", MCP_SERVER_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load {MCP_SERVER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MCP_SERVER_MODULE = _load_mcp_server_module()


# Build a normalized debug context dict from an incoming worker request.
def _debug_context(request: dict[str, Any] | None = None) -> dict[str, Any]:
    context = request.get("context") if isinstance(request, dict) and isinstance(request.get("context"), dict) else {}
    return {
        "module_dir": str(context.get("module_dir") or MCP_SERVER_MODULE.PROJECT_ROOT),
        "project_dir": str(context.get("project_dir") or MCP_SERVER_MODULE.PROJECT_ROOT),
        **context,
    }


# Emit a debug event (intentionally disabled; kept for call-site compatibility).
def _debug_event(request: dict[str, Any] | None, event: str, **fields: Any) -> None:
    return None


# Close the shared browser state and stop the dedicated browser event loop.
async def _close_browser_state() -> None:
    try:
        from browser import close_browser_runtime, run_in_browser_loop, state

        try:
            await run_in_browser_loop(state.close())
        finally:
            close_browser_runtime()
    except Exception:
        pass


# Dispatch one JSON-line worker request to a browser tool or shutdown command.
async def _handle_request(request: dict[str, Any]) -> dict[str, Any]:
    request_id = str(request.get("id") or "")
    _debug_event(
        request,
        "browser_worker_request_received",
        request_id=request_id,
        command=request.get("command"),
        tool=request.get("tool"),
        arguments=request.get("arguments") if isinstance(request.get("arguments"), dict) else {},
    )
    if request.get("command") == "shutdown":
        await _close_browser_state()
        _debug_event(request, "browser_worker_shutdown_command_done", request_id=request_id)
        return {"id": request_id, "ok": True, "result": "shutdown"}

    tool_name = str(request.get("tool") or "")
    arguments = request.get("arguments") if isinstance(request.get("arguments"), dict) else {}
    context = request.get("context") if isinstance(request.get("context"), dict) else {}
    try:
        result = await MCP_SERVER_MODULE._execute_browser_tool_local(tool_name, arguments, context)
        _debug_event(
            request,
            "browser_worker_tool_done",
            request_id=request_id,
            tool=tool_name,
            result_type=type(result).__name__,
        )
        return {"id": request_id, "ok": True, "result": result}
    except Exception as exc:
        _debug_event(
            request,
            "browser_worker_tool_error",
            request_id=request_id,
            tool=tool_name,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        return {"id": request_id, "ok": False, "error": f"{type(exc).__name__}: {exc}"}


# Write one JSON response line to stdout for the parent process.
def _write_response(response: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(response, ensure_ascii=False, default=str) + "\n")
    sys.stdout.flush()


# Read JSON requests from stdin until a shutdown command ends the worker loop.
def main() -> None:
    _debug_event(None, "browser_worker_main_started", argv=sys.argv)
    for line in sys.stdin:
        try:
            request = json.loads(line)
        except ValueError as exc:
            _write_response({"id": "", "ok": False, "error": f"Invalid JSON request: {exc}"})
            continue
        response = asyncio.run(_handle_request(request if isinstance(request, dict) else {}))
        _write_response(response)
        if request.get("command") == "shutdown":
            break
    _debug_event(None, "browser_worker_main_exiting")


if __name__ == "__main__":
    main()
