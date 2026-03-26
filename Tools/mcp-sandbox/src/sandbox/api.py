from __future__ import annotations

from typing import Any, Callable

from sandbox.config import (
    ADVANCED_TOOLS_ENABLED,
    DEFAULT_TIMEOUT,
    MAX_FIND_RESULTS,
    MAX_GREP_RESULTS,
    MAX_LS_ENTRIES,
    MAX_READ_BYTES,
)
from sandbox.container import exec_bash
from sandbox.responses import error_response, exception_response, success_response
from sandbox.workspace import delete, edit, find, grep, ls, mkdir, move, read, write

MCP_SERVER = {
    "id": "sandbox",
    "name": "Sandbox",
    "description": (
        "Linux sandbox with shared workspace. Use specialized file tools first and "
        "bash only when execution or shell-native work is required."
    ),
}


CORE_TOOLS = [
    {
        "id": "ls",
        "name": "List Directory",
        "description": (
            "List files and directories in the workspace with depth and entry limits. "
            "Use this before read, edit, or write when you need to understand the layout "
            "or confirm exact paths. Returns structured entries with path, type, depth, "
            "and file metadata when available."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "default": "."},
                "depth": {"type": "integer", "default": 1},
                "max_entries": {"type": "integer", "default": MAX_LS_ENTRIES},
                "include_hidden": {"type": "boolean", "default": False},
            },
        },
    },
    {
        "id": "read",
        "name": "Read File",
        "description": (
            "Read a file from the workspace. For text files it returns content plus line "
            "metadata; for binary files it returns metadata only; for images it returns "
            "metadata plus inline preview payload when possible. Use this before edit, and "
            "prefer it over bash for file inspection."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "start_line": {"type": "integer"},
                "end_line": {"type": "integer"},
                "max_bytes": {"type": "integer", "default": MAX_READ_BYTES},
            },
            "required": ["path"],
        },
    },
    {
        "id": "write",
        "name": "Write File",
        "description": (
            "Create a new UTF-8 text file or fully overwrite an existing one in the "
            "workspace. Use this for new files and full rewrites. Returns bytes_written "
            "plus created/overwrote flags. Do not use it for small surgical edits when edit fits better."
        ),
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
        "id": "edit",
        "name": "Edit File",
        "description": (
            "Replace exact literal text inside a file. Use this for surgical edits after "
            "reading the current file and copying exact context. By default it fails when "
            "the match is missing or ambiguous; set replace_all=true only when every match "
            "should be updated. Returns match statistics and previews/diff metadata."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old_str": {"type": "string"},
                "new_str": {"type": "string"},
                "replace_all": {"type": "boolean", "default": False},
            },
            "required": ["path", "old_str", "new_str"],
        },
    },
    {
        "id": "find",
        "name": "Find Paths",
        "description": (
            "Find files or directories by name pattern within the workspace. Use this when "
            "you know part of a filename but not its exact location. Returns structured "
            "matches with relative paths, type, and depth."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "default": "."},
                "name_pattern": {"type": "string"},
                "type": {
                    "type": "string",
                    "enum": ["any", "file", "directory"],
                    "default": "any",
                },
                "max_depth": {"type": "integer", "default": 8},
                "max_results": {"type": "integer", "default": MAX_FIND_RESULTS},
            },
        },
    },
    {
        "id": "grep",
        "name": "Search Text",
        "description": (
            "Search workspace text files with a regular expression. Use this before shell "
            "grep when you need code or text lookup. Returns structured matches with line "
            "numbers and optional surrounding context, instead of raw shell output."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "path": {"type": "string", "default": "."},
                "glob": {"type": "string"},
                "case_sensitive": {"type": "boolean", "default": False},
                "context_before": {"type": "integer", "default": 0},
                "context_after": {"type": "integer", "default": 0},
                "max_results": {"type": "integer", "default": MAX_GREP_RESULTS},
            },
            "required": ["pattern"],
        },
    },
    {
        "id": "bash",
        "name": "Run Bash",
        "description": (
            "Run a shell command inside the Linux container. Use this for execution, tests, "
            "builds, installs, OCR, and CLI tools. Prefer specialized tools like ls, read, "
            "find, grep, write, and edit for workspace inspection and editing. Returns "
            "exit_code, stdout, stderr, elapsed_ms, and cwd."
        ),
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
]


ADVANCED_TOOLS = [
    {
        "id": "mkdir",
        "name": "Make Directory",
        "description": (
            "Create a directory inside the workspace. This is an advanced convenience tool "
            "that avoids using shell mkdir for simple path setup. Returns created/already_exists flags."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "parents": {"type": "boolean", "default": True},
            },
            "required": ["path"],
        },
    },
    {
        "id": "move",
        "name": "Move Path",
        "description": (
            "Move or rename a file or directory inside the workspace. This is an advanced "
            "convenience tool for controlled path changes without falling back to shell mv. "
            "Returns source, destination, and overwrite information."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "src": {"type": "string"},
                "dst": {"type": "string"},
                "overwrite": {"type": "boolean", "default": False},
            },
            "required": ["src", "dst"],
        },
    },
    {
        "id": "delete",
        "name": "Delete Path",
        "description": (
            "Delete a file or directory inside the workspace. This is an advanced "
            "convenience tool for controlled deletion without shell rm. Directory removal "
            "requires recursive=true. Returns the deleted path and type."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "recursive": {"type": "boolean", "default": False},
            },
            "required": ["path"],
        },
    },
]


def get_public_tools() -> list[dict[str, Any]]:
    """Return the public sandbox v2 tool definitions."""

    tools = list(CORE_TOOLS)
    if ADVANCED_TOOLS_ENABLED:
        tools.extend(ADVANCED_TOOLS)
    return tools


TOOLS = get_public_tools()


def _wrap_workspace_payload(tool: str, payload: dict[str, Any]) -> dict[str, Any]:
    return success_response(
        tool,
        payload.get("result"),
        warnings=payload.get("warnings"),
        truncated=bool(payload.get("truncated", False)),
    )


def _handle_ls(arguments: dict[str, Any], _context: dict[str, Any] | None = None) -> dict[str, Any]:
    return _wrap_workspace_payload(
        "ls",
        ls(
            path=str(arguments.get("path", ".")),
            depth=int(arguments.get("depth", 1)),
            max_entries=int(arguments.get("max_entries", MAX_LS_ENTRIES)),
            include_hidden=bool(arguments.get("include_hidden", False)),
        ),
    )


def _handle_read(arguments: dict[str, Any], _context: dict[str, Any] | None = None) -> dict[str, Any]:
    return _wrap_workspace_payload(
        "read",
        read(
            path=str(arguments.get("path", "")),
            start_line=arguments.get("start_line"),
            end_line=arguments.get("end_line"),
            max_bytes=int(arguments.get("max_bytes", MAX_READ_BYTES)),
        ),
    )


def _handle_write(arguments: dict[str, Any], _context: dict[str, Any] | None = None) -> dict[str, Any]:
    return _wrap_workspace_payload(
        "write",
        write(
            path=str(arguments.get("path", "")),
            content=str(arguments.get("content", "")),
        ),
    )


def _handle_edit(arguments: dict[str, Any], _context: dict[str, Any] | None = None) -> dict[str, Any]:
    return _wrap_workspace_payload(
        "edit",
        edit(
            path=str(arguments.get("path", "")),
            old_str=str(arguments.get("old_str", "")),
            new_str=str(arguments.get("new_str", "")),
            replace_all=bool(arguments.get("replace_all", False)),
        ),
    )


def _handle_find(arguments: dict[str, Any], _context: dict[str, Any] | None = None) -> dict[str, Any]:
    return _wrap_workspace_payload(
        "find",
        find(
            path=str(arguments.get("path", ".")),
            name_pattern=arguments.get("name_pattern"),
            type=arguments.get("type"),
            max_depth=int(arguments.get("max_depth", 8)),
            max_results=int(arguments.get("max_results", MAX_FIND_RESULTS)),
        ),
    )


def _handle_grep(arguments: dict[str, Any], _context: dict[str, Any] | None = None) -> dict[str, Any]:
    return _wrap_workspace_payload(
        "grep",
        grep(
            pattern=str(arguments.get("pattern", "")),
            path=str(arguments.get("path", ".")),
            glob=arguments.get("glob"),
            case_sensitive=bool(arguments.get("case_sensitive", False)),
            context_before=int(arguments.get("context_before", 0)),
            context_after=int(arguments.get("context_after", 0)),
            max_results=int(arguments.get("max_results", MAX_GREP_RESULTS)),
        ),
    )


def _handle_bash(
    arguments: dict[str, Any],
    _context: dict[str, Any] | None = None,
    *,
    progress_callback: Callable[[float, str], None] | None = None,
) -> dict[str, Any]:
    execution = exec_bash(
        command=str(arguments.get("command", "")),
        cwd=str(arguments.get("cwd", ".")),
        timeout_s=int(arguments.get("timeout_s", DEFAULT_TIMEOUT)),
        stdin=arguments.get("stdin"),
        on_progress=progress_callback,
    )
    result = {
        "command": str(arguments.get("command", "")),
        "cwd": execution.get("cwd", "."),
        "exit_code": execution.get("exit_code"),
        "stdout": execution.get("stdout", ""),
        "stderr": execution.get("stderr", ""),
        "elapsed_ms": execution.get("elapsed_ms", 0),
    }
    warnings = []
    if execution.get("truncated"):
        warnings.append("Command output was truncated.")

    if execution.get("error") is None and execution.get("exit_code") == 0:
        return success_response(
            "bash",
            result,
            warnings=warnings,
            truncated=bool(execution.get("truncated", False)),
        )

    error_type = "process_error"
    if execution.get("exit_code") is None and execution.get("error"):
        error_type = "execution_failed"
    if execution.get("error") and "timed out" in execution["error"].lower():
        error_type = "timeout"

    return error_response(
        "bash",
        error_type,
        execution.get("error") or "Command failed.",
        result=result,
        warnings=warnings,
        truncated=bool(execution.get("truncated", False)),
    )


def _handle_mkdir(arguments: dict[str, Any], _context: dict[str, Any] | None = None) -> dict[str, Any]:
    return _wrap_workspace_payload(
        "mkdir",
        mkdir(
            path=str(arguments.get("path", "")),
            parents=bool(arguments.get("parents", True)),
        ),
    )


def _handle_move(arguments: dict[str, Any], _context: dict[str, Any] | None = None) -> dict[str, Any]:
    return _wrap_workspace_payload(
        "move",
        move(
            src=str(arguments.get("src", "")),
            dst=str(arguments.get("dst", "")),
            overwrite=bool(arguments.get("overwrite", False)),
        ),
    )


def _handle_delete(arguments: dict[str, Any], _context: dict[str, Any] | None = None) -> dict[str, Any]:
    return _wrap_workspace_payload(
        "delete",
        delete(
            path=str(arguments.get("path", "")),
            recursive=bool(arguments.get("recursive", False)),
        ),
    )


BASE_TOOL_HANDLERS: dict[str, Callable[..., dict[str, Any]]] = {
    "ls": _handle_ls,
    "read": _handle_read,
    "write": _handle_write,
    "edit": _handle_edit,
    "find": _handle_find,
    "grep": _handle_grep,
    "bash": _handle_bash,
}

if ADVANCED_TOOLS_ENABLED:
    BASE_TOOL_HANDLERS.update(
        {
            "mkdir": _handle_mkdir,
            "move": _handle_move,
            "delete": _handle_delete,
        }
    )


def handle_tool(
    tool_id: str,
    arguments: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
    *,
    progress_callback: Callable[[float, str], None] | None = None,
) -> dict[str, Any]:
    """Execute one public sandbox v2 tool."""

    handler = BASE_TOOL_HANDLERS.get(tool_id)
    if handler is None:
        return error_response("sandbox", "unknown_tool", f"Unknown sandbox tool: {tool_id}")

    try:
        if tool_id == "bash":
            return handler(arguments or {}, context, progress_callback=progress_callback)
        return handler(arguments or {}, context)
    except Exception as exc:
        return exception_response(tool_id, exc)


TOOL_HANDLERS = {
    tool["id"]: (lambda tool_id: (lambda arguments, context=None: handle_tool(tool_id, arguments, context)))(tool["id"])
    for tool in TOOLS
}
