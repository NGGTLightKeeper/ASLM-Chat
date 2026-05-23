"""MCP server: Python execution + shared sandbox file bridge."""
from __future__ import annotations

import asyncio
import json

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from sandbox_mcp import daemon_client
from sandbox_mcp.files import (
    FileBridgeError,
)
from sandbox_mcp.runner import max_concurrent, parse_run_request, run_sandbox, share_sandbox_file

TOOL_SANDBOX = "sandbox"
TOOL_PYTHON = "oda_python"
TOOL_SHARE_FILE = "oda_share_file"

PYTHON_TOOL = types.Tool(
    name=TOOL_PYTHON,
    description=(
        "Run Python code in the data-analysis sandbox. "
        "Write normal Python in `code`; it runs as a script in /mnt/data/work. "
        "Read and write user-visible files only under /mnt/data/_sandbox. "
        "Use /mnt/data/work for private scratch files. "
        "After creating a file the user should receive, call oda_share_file with its path "
        "inside /mnt/data/_sandbox. "
        "The sandbox has Python, pip, common build tools, Chromium/Chromedriver, ffmpeg, "
        "PDF/image/OCR tools, and network access for pip installs. "
        "Prefer this tool for analysis, calculations, file conversion, charts, and generated artifacts."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": (
                    "Python source code to execute. Use print() for textual results. "
                    "Read/write shared files in /mnt/data/_sandbox. "
                    "Use subprocess.run(...) inside Python only when a system command is needed."
                ),
            },
        },
        "required": ["code"],
        "additionalProperties": False,
    },
)

SANDBOX_TOOL = types.Tool(
    name=TOOL_SANDBOX,
    description=(
        "Low-level escape hatch: run argv in the Python sandbox. "
        "Prefer oda_python unless raw argv execution is specifically needed. "
        "Paths: shared files in /mnt/data/_sandbox, scratch in /mnt/data/work/."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "cmd": {
                "type": "array",
                "items": {"type": "string"},
                "description": "argv for subprocess.run inside the container",
            },
        },
        "required": ["cmd"],
        "additionalProperties": False,
    },
)

SHARE_FILE_TOOL = types.Tool(
    name=TOOL_SHARE_FILE,
    description=(
        "Present an existing file from the shared sandbox folder to the user. "
        "Use this after creating or updating a file the user should receive. "
        "The path must point to a regular file inside /mnt/data/_sandbox."
    ),
    inputSchema={
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
)

app = Server("sandbox")
_run_semaphore = asyncio.Semaphore(max_concurrent())


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [PYTHON_TOOL, SHARE_FILE_TOOL]


def _text(content: str) -> list[types.TextContent]:
    return [types.TextContent(type="text", text=content)]


def _use_daemon() -> bool:
    return daemon_client.daemon_url() is not None


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    try:
        if name == TOOL_SANDBOX:
            if _use_daemon():
                text = await asyncio.to_thread(daemon_client.run, arguments)
            else:
                request = parse_run_request(arguments)
                async with _run_semaphore:
                    text = await asyncio.to_thread(run_sandbox, request)
            return _text(text)

        if name == TOOL_SHARE_FILE:
            if _use_daemon():
                meta = await asyncio.to_thread(
                    daemon_client.share,
                    arguments.get("path"),
                    arguments.get("filename"),
                )
            else:
                meta = await asyncio.to_thread(
                    share_sandbox_file,
                    arguments.get("path"),
                    arguments.get("filename"),
                )
            return _text(json.dumps(meta, ensure_ascii=False, indent=2))

        if name == TOOL_PYTHON:
            code = arguments.get("code")
            if not isinstance(code, str) or not code.strip():
                raise ValueError("code must be a non-empty string")
            if _use_daemon():
                text = await asyncio.to_thread(daemon_client.run_python, code)
            else:
                request = parse_run_request(
                    {
                        "cmd": ["python3", "-u", "-c", code],
                    }
                )
                async with _run_semaphore:
                    text = await asyncio.to_thread(run_sandbox, request)
            return _text(text)

    except (ValueError, FileBridgeError, KeyError, daemon_client.SandboxDaemonError) as exc:
        return _text(f"exit_code: error\n\nstderr:\n{exc}")

    raise ValueError(f"unknown tool: {name}")


def main() -> None:
    async def _run() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await app.run(read_stream, write_stream, app.create_initialization_options())

    asyncio.run(_run())


if __name__ == "__main__":
    main()
