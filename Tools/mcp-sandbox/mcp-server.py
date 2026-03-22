# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import base64
import mimetypes
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SRC_ROOT = Path(__file__).resolve().parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from sandbox.config import (
    DEFAULT_TASK_DIR,
    DEFAULT_TIMEOUT,
    HTTP_HOST,
    HTTP_PORT,
    TOKEN_TTL_SECONDS,
)
from sandbox.container import (
    exec_bash,
    get_status,
    reset_container,
    restore_container,
    snapshot_container,
)
from sandbox.token_registry import _register_token
from sandbox.workspace import (
    clear_workspace,
    copy_into_workspace,
    get_secure_task_path,
    list_directory as list_workspace_directory,
    normalize_relative_path,
    read_file as read_workspace_file,
    str_replace as replace_in_workspace_file,
    write_file as write_workspace_file,
)

MCP_SERVER = {
    "id": "sandbox",
    "name": "Sandbox",
    "description": "Linux sandbox with shared workspace. Use bash to run commands, write_file/read_file/str_replace to manage files, share to create download links. All paths are relative to the workspace root.",
}

TOOLS = [
    {
        "id": "status",
        "name": "Sandbox Status",
        "description": "Check Docker availability and container state. Call this first if unsure whether the sandbox is ready.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "id": "list_directory",
        "name": "List Directory",
        "description": "List files and directories in the workspace. Use path='.' for root, recursive=True to see all nested files. Call before reading or editing to understand the layout.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "default": "."},
                "recursive": {"type": "boolean", "default": False},
                "max_depth": {"type": "integer", "default": 3},
            },
        },
    },
    {
        "id": "read_file",
        "name": "Read File",
        "description": "Read a text file from the workspace. Use start_line/end_line to read a specific range. Always read before str_replace to get exact context.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "start_line": {"type": "integer"},
                "end_line": {"type": "integer"},
            },
            "required": ["path"],
        },
    },
    {
        "id": "write_file",
        "name": "Write File",
        "description": "Create or fully overwrite a file in the workspace. Use for new files or complete rewrites. For surgical edits use str_replace instead.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "id": "str_replace",
        "name": "String Replace",
        "description": "Replace one exact unique text fragment in a file. old_str must match exactly as it appears in the file. Read the file first to copy the exact context.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old_str": {"type": "string"},
                "new_str": {"type": "string"},
            },
            "required": ["path", "old_str", "new_str"],
        },
    },
    {
        "id": "bash",
        "name": "Run Bash",
        "description": "Run a shell command inside the Linux container. Use for Python execution, package installs, git, grep, find, OCR, builds, and any CLI work. For non-trivial code prefer write_file then bash to run it.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "cwd": {"type": "string", "default": "."},
                "timeout_s": {"type": "integer", "default": DEFAULT_TIMEOUT},
                "stdin": {"type": "string"},
            },
            "required": ["command"],
        },
    },
    {
        "id": "show_image",
        "name": "Show Image",
        "description": "Load an image from the workspace for visual inspection. Use after generating charts, screenshots, or any image artifact.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
            },
            "required": ["path"],
        },
    },
    {
        "id": "share",
        "name": "Share Artifact",
        "description": "Create a localhost download link for a file, or a preview link for an HTML app directory. Call after generating an artifact to deliver it.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
            },
            "required": ["path"],
        },
    },
    {
        "id": "import_from_host",
        "name": "Import From Host",
        "description": "Copy a file from the host machine into the workspace so bash and file tools can access it.",
        "parameters": {
            "type": "object",
            "properties": {
                "host_path": {"type": "string"},
                "dest_path": {"type": "string"},
            },
            "required": ["host_path"],
        },
    },
    {
        "id": "reset",
        "name": "Reset Sandbox",
        "description": "Recreate the container from the base image. Use when the environment is broken. Set preserve_workspace=False to also wipe workspace files.",
        "parameters": {
            "type": "object",
            "properties": {
                "preserve_workspace": {"type": "boolean", "default": True},
            },
        },
    },
    {
        "id": "snapshot",
        "name": "Snapshot Sandbox",
        "description": "Save the current container state as a named snapshot for later restore.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "default": "stable"},
            },
        },
    },
    {
        "id": "restore",
        "name": "Restore Sandbox",
        "description": "Restore the container from a previously saved snapshot.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "default": "stable"},
                "preserve_workspace": {"type": "boolean", "default": True},
            },
        },
    },
]


def supports(engine: str | None = None, model_name: str | None = None) -> bool:
    """Expose this tool server only for Ollama tool-calling flows."""

    return engine == "ollama-service"


def _share_file(path: Path) -> dict[str, Any]:
    """Build share metadata for a downloadable file."""

    token = _register_token(str(path), "file")
    filename = path.name
    url = f"http://{HTTP_HOST}:{HTTP_PORT}/dl/{token}"
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=TOKEN_TTL_SECONDS)

    return {
        "ok": True,
        "kind": "file",
        "url": url,
        "markdown": f"[Download {filename}]({url})",
        "filename": filename,
        "expires_in_seconds": TOKEN_TTL_SECONDS,
        "expires_at": expires_at.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }


def _share_app(directory: Path, entry_file: str) -> dict[str, Any]:
    """Build share metadata for a previewable web app."""

    token = _register_token(str(directory), "dir")
    url = f"http://{HTTP_HOST}:{HTTP_PORT}/app/{token}/{entry_file}"
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=TOKEN_TTL_SECONDS)

    return {
        "ok": True,
        "kind": "web_app",
        "url": url,
        "markdown": f"[Open {entry_file}]({url})",
        "entry_file": entry_file,
        "expires_in_seconds": TOKEN_TTL_SECONDS,
        "expires_at": expires_at.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }


def _status(arguments: dict[str, Any] | None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return current sandbox status."""

    return get_status()


def _list_directory(arguments: dict[str, Any] | None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """List files and directories inside the task workspace."""

    args = arguments or {}
    try:
        return list_workspace_directory(
            path=str(args.get("path", ".")),
            recursive=bool(args.get("recursive", False)),
            max_depth=int(args.get("max_depth", 3)),
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _read_file(arguments: dict[str, Any] | None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Read a text file from the task workspace."""

    args = arguments or {}
    try:
        return read_workspace_file(
            str(args.get("path", "")),
            start_line=args.get("start_line"),
            end_line=args.get("end_line"),
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _write_file(arguments: dict[str, Any] | None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Overwrite a workspace file."""

    args = arguments or {}
    try:
        return write_workspace_file(str(args.get("path", "")), str(args.get("content", "")))
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _str_replace(arguments: dict[str, Any] | None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Replace one exact fragment in a workspace file."""

    args = arguments or {}
    try:
        return replace_in_workspace_file(
            str(args.get("path", "")),
            str(args.get("old_str", "")),
            str(args.get("new_str", "")),
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _bash(arguments: dict[str, Any] | None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run a bash command inside the sandbox container."""

    args = arguments or {}
    try:
        return exec_bash(
            command=str(args.get("command", "")),
            cwd=str(args.get("cwd", ".")),
            timeout_s=int(args.get("timeout_s", DEFAULT_TIMEOUT)),
            stdin=args.get("stdin"),
        )
    except Exception as exc:
        return {
            "ok": False,
            "exit_code": None,
            "stdout": "",
            "stderr": "",
            "error": str(exc),
            "elapsed_ms": 0,
            "truncated": False,
        }


def _show_image(arguments: dict[str, Any] | None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Load an image from the workspace into a serializable payload."""

    args = arguments or {}
    try:
        target = get_secure_task_path(str(args.get("path", "")))
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    if not target.is_file():
        return {"ok": False, "error": f"File not found: {normalize_relative_path(str(args.get('path', '')))}"}

    mime_type, _ = mimetypes.guess_type(str(target))
    if not mime_type or not mime_type.startswith("image/"):
        return {"ok": False, "error": f"File is not an image: {normalize_relative_path(str(args.get('path', '')))}"}

    try:
        with open(target, "rb") as file_handle:
            b64_data = base64.b64encode(file_handle.read()).decode("utf-8")

        return {
            "ok": True,
            "path": normalize_relative_path(str(args.get("path", ""))),
            "mime_type": mime_type,
            "data_base64": b64_data,
        }
    except Exception as exc:
        return {"ok": False, "error": f"Error reading image: {exc}"}



def _share(arguments: dict[str, Any] | None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create a share link for a file or HTML app."""

    args = arguments or {}
    try:
        target = get_secure_task_path(str(args.get("path", "")))
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    if not target.exists():
        return {"ok": False, "error": f"Path not found: {normalize_relative_path(str(args.get('path', '')))}"}

    if target.is_file():
        if target.suffix.lower() == ".html":
            return _share_app(target.parent, target.name)
        return _share_file(target)

    index_html = target / "index.html"
    if index_html.is_file():
        return _share_app(target, "index.html")

    return {
        "ok": False,
        "error": f"Directory has no index.html: {normalize_relative_path(str(args.get('path', '')))}",
    }


def _import_from_host(arguments: dict[str, Any] | None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Copy an allowed host path into the task workspace."""

    args = arguments or {}
    try:
        result = copy_into_workspace(
            host_path=str(args.get("host_path", "")),
            dest_path=args.get("dest_path"),
        )
        if args.get("dest_path") is None:
            result["default_task_dir"] = "."
            result["model_workspace_root"] = DEFAULT_TASK_DIR

        return result
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _reset(arguments: dict[str, Any] | None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Reset the sandbox container."""

    args = arguments or {}
    try:
        preserve_workspace = bool(args.get("preserve_workspace", True))
        result = reset_container(preserve_workspace=preserve_workspace)
        if result.get("ok") and not preserve_workspace:
            result["workspace_cleanup"] = clear_workspace()
        return result
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _snapshot(arguments: dict[str, Any] | None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create a named sandbox snapshot."""

    args = arguments or {}
    try:
        return snapshot_container(name=str(args.get("name", "stable")))
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _restore(arguments: dict[str, Any] | None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Restore the sandbox from a named snapshot."""

    args = arguments or {}
    try:
        preserve_workspace = bool(args.get("preserve_workspace", True))
        result = restore_container(
            name=str(args.get("name", "stable")),
            preserve_workspace=preserve_workspace,
        )
        if result.get("ok") and not preserve_workspace:
            result["workspace_cleanup"] = clear_workspace()
        return result
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


TOOL_HANDLERS = {
    "status": _status,
    "list_directory": _list_directory,
    "read_file": _read_file,
    "write_file": _write_file,
    "str_replace": _str_replace,
    "bash": _bash,
    "show_image": _show_image,
    "share": _share,
    "import_from_host": _import_from_host,
    "reset": _reset,
    "snapshot": _snapshot,
    "restore": _restore,
}


def register_tools(mcp) -> None:
    """Register sandbox tools on a FastMCP instance."""

    @mcp.tool(name="status")
    def status() -> dict[str, Any]:
        return _status({}, {})

    @mcp.tool(name="list_directory")
    def list_directory(path: str = ".", recursive: bool = False, max_depth: int = 3) -> dict[str, Any]:
        return _list_directory(
            {"path": path, "recursive": recursive, "max_depth": max_depth},
            {},
        )

    @mcp.tool(name="read_file")
    def read_file(path: str, start_line: int | None = None, end_line: int | None = None) -> dict[str, Any]:
        return _read_file(
            {"path": path, "start_line": start_line, "end_line": end_line},
            {},
        )

    @mcp.tool(name="write_file")
    def write_file(path: str, content: str) -> dict[str, Any]:
        return _write_file({"path": path, "content": content}, {})

    @mcp.tool(name="str_replace")
    def str_replace(path: str, old_str: str, new_str: str) -> dict[str, Any]:
        return _str_replace(
            {"path": path, "old_str": old_str, "new_str": new_str},
            {},
        )

    @mcp.tool(name="bash")
    def bash(
        command: str,
        cwd: str = ".",
        timeout_s: int = DEFAULT_TIMEOUT,
        stdin: str | None = None,
    ) -> dict[str, Any]:
        return _bash(
            {"command": command, "cwd": cwd, "timeout_s": timeout_s, "stdin": stdin},
            {},
        )

    @mcp.tool(name="show_image")
    def show_image(path: str) -> dict[str, Any]:
        return _show_image({"path": path}, {})

    @mcp.tool(name="share")
    def share(path: str) -> dict[str, Any]:
        return _share({"path": path}, {})

    @mcp.tool(name="import_from_host")
    def import_from_host(host_path: str, dest_path: str | None = None) -> dict[str, Any]:
        return _import_from_host({"host_path": host_path, "dest_path": dest_path}, {})

    @mcp.tool(name="reset")
    def reset(preserve_workspace: bool = True) -> dict[str, Any]:
        return _reset({"preserve_workspace": preserve_workspace}, {})

    @mcp.tool(name="snapshot")
    def snapshot(name: str = "stable") -> dict[str, Any]:
        return _snapshot({"name": name}, {})

    @mcp.tool(name="restore")
    def restore(name: str = "stable", preserve_workspace: bool = True) -> dict[str, Any]:
        return _restore({"name": name, "preserve_workspace": preserve_workspace}, {})
