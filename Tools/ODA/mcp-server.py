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

from sandbox_mcp import daemon_client
from sandbox_mcp.files import FileBridgeError
from sandbox_mcp.runner import max_concurrent, parse_run_request, run_sandbox, share_sandbox_file


MCP_SERVER = {
    "id": "oda",
    "name": "ODA",
    "description": "Run Python code in the ODA sandbox and share generated files.",
}

TOOLS = [
    {
        "id": "oda_python",
        "name": "ODA Python",
        "description": (
            "Run Python code in the ODA data-analysis sandbox. "
            "Write normal Python in `code`; it runs as a script in /mnt/data/work. "
            "Read and write user-visible files only under /mnt/data/_sandbox. "
            "Use /mnt/data/work for private scratch files. "
            "After creating a file the user should receive, call oda_share_file with its path "
            "inside /mnt/data/_sandbox."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python source code to execute. Use print() for textual results.",
                },
            },
            "required": ["code"],
            "additionalProperties": False,
        },
    },
    {
        "id": "oda_share_file",
        "name": "ODA Share File",
        "description": (
            "Present an existing file from the shared ODA sandbox folder to the user. "
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
]

_RUN_SEMAPHORE = asyncio.Semaphore(max_concurrent())


def supports(engine: str | None = None, model_name: str | None = None) -> bool:
    return engine in ("ollama-service", "lms", "openai", "google-genai")


def _use_daemon() -> bool:
    return daemon_client.daemon_url() is not None


async def _run_python(code: object) -> str:
    if not isinstance(code, str) or not code.strip():
        raise ValueError("code must be a non-empty string")

    if _use_daemon():
        return await asyncio.to_thread(daemon_client.run_python, code)

    request = parse_run_request({"cmd": ["python3", "-u", "-c", code]})
    async with _RUN_SEMAPHORE:
        return await asyncio.to_thread(run_sandbox, request)


async def _share_file(path: object, filename: object | None = None) -> dict[str, Any]:
    if _use_daemon():
        meta = await asyncio.to_thread(daemon_client.share, path, filename)
    else:
        meta = await asyncio.to_thread(share_sandbox_file, path, filename)
    return meta


async def call_tool(
    tool_id: str,
    arguments: dict[str, Any] | None,
    context: dict[str, Any] | None = None,
) -> str:
    args = dict(arguments or {})

    try:
        if tool_id in ("oda_python", "sandbox_python"):
            return await _run_python(args.get("code"))

        if tool_id in ("oda_share_file", "share_file"):
            return await _share_file(args.get("path"), args.get("filename"))

    except (ValueError, FileBridgeError, KeyError, daemon_client.SandboxDaemonError) as exc:
        return f"exit_code: error\n\nstderr:\n{exc}"

    raise ValueError(f"Unknown ODA tool: {tool_id}")
