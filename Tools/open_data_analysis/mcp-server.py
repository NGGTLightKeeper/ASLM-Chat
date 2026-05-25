# Copyright NGGT.LightKeeper. All Rights Reserved.

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any


SERVER_ROOT = Path(__file__).resolve().parent
MCP_SERVER_ROOT = SERVER_ROOT / "mcp_server"
if str(MCP_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(MCP_SERVER_ROOT))

# Enable daemon + raise timeout defaults if not already overridden by env/mcp.json.
# These must be set before sandbox_mcp.config is imported.
import os as _os
_os.environ.setdefault("SANDBOX_USE_DAEMON", "1")
_os.environ.setdefault("SANDBOX_DAEMON_AUTOSTART", "1")
_os.environ.setdefault("SANDBOX_TIMEOUT", "300")
_os.environ.setdefault("SANDBOX_MCP_SERVER_ROOT", str(MCP_SERVER_ROOT))
_os.environ.setdefault("SANDBOX_PYTHON", sys.executable)

from sandbox_mcp import daemon_client
from sandbox_mcp.files import FileBridgeError, read_shared_image
from sandbox_mcp.runner import max_concurrent, parse_run_request, run_sandbox, share_sandbox_file


MCP_SERVER = {
    "id": "oda",
    "name": "Data Analysis",
    "description": "Run Python code in the data-analysis sandbox and share generated files.",
}

TOOLS = [
    {
        "id": "oda_python",
        "name": "Python",
        "description": (
            "Run Python code in the data-analysis sandbox. "
            "Write normal Python in `code`; it runs as a script in /mnt/data/work. "
            "Read and write user-visible files only under /mnt/data/_sandbox. "
            "Use /mnt/data/work for private scratch files. "
            "If needed packages are missing, install them from inside the code before importing "
            "them, for example with subprocess.run([sys.executable, '-m', 'pip', 'install', "
            "'package'], check=True). "
            "After creating a file the user should receive, call oda_share_file with its path "
            "inside /mnt/data/_sandbox."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                "type": "string",
                    "description": (
                        "Python source code to execute. Use print() for textual results. "
                        "Install missing third-party packages with pip when necessary."
                    ),
                },
            },
            "required": ["code"],
            "additionalProperties": False,
        },
    },
    {
        "id": "oda_share_file",
        "name": "Share File",
        "description": (
            "Present an existing file from the shared sandbox folder to the user. "
            "Use this after creating or updating a file the user should receive."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path inside /mnt/data/_sandbox, e.g. /mnt/data/_sandbox/report.csv or report.csv.",
                },
                "filename": {
                    "type": "string",
                    "description": "Optional display/download filename.",
                },
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    {
        "id": "oda_view_image",
        "name": "View Image",
        "description": (
            "Inspect an image file from the shared sandbox folder. "
            "Returns image metadata and an inline preview when the file is small enough."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path inside /mnt/data/_sandbox, e.g. /mnt/data/_sandbox/chart.png or chart.png.",
                },
                "include_preview": {"type": "boolean", "default": True},
                "max_preview_bytes": {"type": "integer"},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
]

_RUN_SEMAPHORE = asyncio.Semaphore(max_concurrent())


def supports(engine: str | None = None, model_name: str | None = None) -> bool:
    return engine in ("ollama-service", "lms", "openai", "google-genai")


def _use_daemon() -> bool:
    return daemon_client.daemon_url() is not None


def _scope_from_context(context: dict[str, Any] | None) -> str | None:
    """Extract chat_id from tool context to use as container scope."""
    if not context:
        return None
    chat_id = context.get("chat_id")
    if isinstance(chat_id, str) and chat_id.strip():
        return chat_id.strip()
    return None


async def _run_python(
    code: object,
    *,
    scope: str | None = None,
    timeout_s: int | None = None,
) -> str:
    if not isinstance(code, str) or not code.strip():
        raise ValueError("code must be a non-empty string")

    if _use_daemon():
        return await asyncio.to_thread(
            daemon_client.run_python, code, scope=scope, timeout_s=timeout_s
        )

    request = parse_run_request({"cmd": ["python3", "-u", "-c", code]})
    async with _RUN_SEMAPHORE:
        return await asyncio.to_thread(run_sandbox, request)


async def _share_file(path: object, filename: object | None = None) -> dict[str, Any]:
    if _use_daemon():
        meta = await asyncio.to_thread(daemon_client.share, path, filename)
    else:
        meta = await asyncio.to_thread(share_sandbox_file, path, filename)
    return meta


def _view_image(arguments: dict[str, Any]) -> dict[str, Any]:
    return read_shared_image(
        arguments.get("path"),
        include_preview=bool(arguments.get("include_preview", True)),
        max_preview_bytes=arguments.get("max_preview_bytes"),
    )


async def call_tool(
    tool_id: str,
    arguments: dict[str, Any] | None,
    context: dict[str, Any] | None = None,
) -> str:
    args = dict(arguments or {})
    scope = _scope_from_context(context)

    try:
        if tool_id in ("oda_python", "sandbox_python"):
            return await _run_python(
                args.get("code"),
                scope=scope,
                timeout_s=args.get("timeout_s") if isinstance(args.get("timeout_s"), int) else None,
            )

        if tool_id in ("oda_share_file", "share_file"):
            return await _share_file(args.get("path"), args.get("filename"))

        if tool_id in ("oda_view_image", "view_image"):
            return _view_image(args)

    except (ValueError, FileBridgeError, KeyError, daemon_client.SandboxDaemonError) as exc:
        return f"exit_code: error\n\nstderr:\n{exc}"

    raise ValueError(f"Unknown data-analysis tool: {tool_id}")
