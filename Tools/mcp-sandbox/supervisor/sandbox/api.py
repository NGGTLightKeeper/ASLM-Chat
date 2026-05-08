# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Sandbox tool API.

The public surface is intentionally small: bash, write, edit, view_image,
share_file.

Most shell commands run as real bash. The supervisor only intercepts the small
set of commands where plain stdout truncation can mislead the model:
``cat/less/more <single-file>``. Large files are shown as structured previews;
all other process output is capped by the execution layer.
"""

from __future__ import annotations

import json
import logging
import re
import shlex
import csv
from pathlib import Path
from typing import Any, Callable

from sandbox.config import (
    DEFAULT_TASK_DIR,
    DEFAULT_TIMEOUT,
    MAX_CAT_FILE_BYTES,
    MAX_CAT_LINE_THRESHOLD,
    MAX_IMAGE_PREVIEW_BYTES,
    MAX_READ_BYTES,
    MODEL_WORKSPACE_CONTAINER,
)
from sandbox.container import (
    exec_bash,
    foreground_background_job,
    kill_background_job,
    list_background_jobs,
)
from sandbox.exec import _truncate
from sandbox.presenters import present_auto_preview
from sandbox.responses import (
    SandboxToolError,
    error_response,
    exception_response,
    success_response,
)
from sandbox.workspace import (
    describe,
    edit,
    edit_lines,
    normalize_model_relative_path,
    read,
    read_image,
    resolve_model_path,
    write,
)

logger = logging.getLogger(__name__)
MODEL_RUNTIME_METADATA_PATH = Path(__file__).resolve().parents[3] / "model_runtime_metadata.json"

MCP_SERVER = {
    "id": "sandbox",
    "name": "Sandbox",
    "description": (
        "Linux sandbox with shared workspace. "
        "Use bash for real shell commands, builds, tests, git, installs, and system inspection. "
        "Very large stdout/stderr is capped with an inline truncation marker. "
        "Plain cat/less/more of a single file may return a structured preview to protect context. "
        "Use write and edit for creating or changing files."
    ),
}


CORE_TOOLS = [
    {
        "id": "bash",
        "name": "Run Bash",
        "description": (
            "Run a shell command inside the Linux container. "
            "Best for: execution, builds, tests, installs, git, curl, search, and system commands. "
            "Most commands run as real bash. Plain cat/less/more of one file may be enhanced with "
            "a structured preview when the file is too large for safe raw output. "
            "Long stdout and stderr are capped independently and include an inline truncation marker. "
            "Returns exit_code, stdout, stderr, elapsed_ms, and cwd. "
            f"The default working directory '.' is the sandbox workspace root ({MODEL_WORKSPACE_CONTAINER}/). "
            "write and edit are restricted to the workspace root only. "
            "PATHS: workspace files use plain relative paths ('script.py', 'subdir/file.py'); "
            "system/container files use absolute paths ('/etc/hosts', '/tmp/out.txt'). "
            "IMPORTANT: For package managers and long-running build/test commands, set timeout_s "
            "to at least 300. Default timeout of 60s is only for quick commands."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "cwd": {"type": "string", "default": "."},
                "timeout_s": {"type": "integer", "default": DEFAULT_TIMEOUT},
                "stdin": {"type": "string"},
                "background": {"type": "string", "enum": ["auto", "always", "never"], "default": "auto"},
            },
            "required": ["command"],
        },
    },
    {
        "id": "write",
        "name": "Write File",
        "description": (
            "Create a new UTF-8 text file or fully overwrite an existing one. "
            f"Use plain relative paths for workspace files under {MODEL_WORKSPACE_CONTAINER}; "
            "absolute Linux paths resolve inside the container, and Windows-style paths are rejected. "
            "Use write for new files and full rewrites; "
            "use edit for small surgical changes."
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
            "Edit a UTF-8 text file. "
            "match mode replaces exact old_str with new_str and fails on missing or ambiguous matches. "
            "lines mode replaces a 1-based line range such as '12:18' or inserts with '12:11'. "
            f"Use paths under {MODEL_WORKSPACE_CONTAINER}; absolute Linux paths resolve inside the container."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "mode": {"type": "string", "enum": ["match", "lines"], "default": "match"},
                "old_str": {"type": "string"},
                "new_str": {"type": "string"},
                "replace_all": {"type": "boolean", "default": False},
                "range": {
                    "oneOf": [
                        {"type": "string"},
                        {
                            "type": "array",
                            "items": {"type": "integer"},
                            "minItems": 2,
                            "maxItems": 2,
                        },
                    ],
                },
                "content": {"type": "string"},
                "anchor": {"type": "string"},
            },
            "required": ["path"],
        },
    },
    {
        "id": "view_image",
        "name": "View Image",
        "description": (
            "Inspect an image file in the sandbox workspace. "
            "Returns path, mime type, byte size, detected width/height when available, "
            "and an inline base64 preview when include_preview=true and the file fits max_preview_bytes. "
            f"Use paths under {MODEL_WORKSPACE_CONTAINER}; absolute Linux paths resolve inside the container."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "include_preview": {"type": "boolean", "default": True},
                "max_preview_bytes": {"type": "integer", "default": MAX_IMAGE_PREVIEW_BYTES},
            },
            "required": ["path"],
        },
    },
    {
        "id": "share_file",
        "name": "Share File",
        "description": (
            "Present an existing sandbox workspace file to the user as a downloadable file card. "
            "Use this after creating or exporting a file the user should receive. "
            f"Use paths under {MODEL_WORKSPACE_CONTAINER}; absolute Linux paths resolve inside the container. "
            "Returns kind='shared_file', path, filename, mime_type, size_bytes, a short model_context, "
            "and an optional render block for rich preview (images/SVG/GIF and tabular text files)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "filename": {"type": "string"},
            },
            "required": ["path"],
        },
    },
]

TOOLS = list(CORE_TOOLS)


def _wrap_workspace_payload(tool: str, payload: dict[str, Any]) -> dict[str, Any]:
    return success_response(
        tool,
        payload.get("result"),
        warnings=payload.get("warnings"),
        truncated=bool(payload.get("truncated", False)),
    )


def _safe_split(command: str) -> list[str] | None:
    try:
        return shlex.split(command)
    except ValueError:
        return None


def _normalize_cwd_argument(raw_cwd: Any) -> str:
    if raw_cwd is None:
        return "."
    cwd = str(raw_cwd).strip()
    if not cwd or cwd.lower() == "none":
        return "."
    return cwd


def _read_text_for_cat(path: str) -> tuple[str, list[str], bool, dict[str, Any]]:
    result = read(path=path, max_bytes=MAX_READ_BYTES)
    inner = result.get("result", {})
    content = str(inner.get("content", ""))
    warnings = list(result.get("warnings", []))
    return content, warnings, bool(result.get("truncated", False)), inner


def _build_large_file_preview(path: str, meta: dict[str, Any]) -> str:
    head_result = read(path=path, max_bytes=MAX_READ_BYTES)
    head_inner = head_result.get("result", {})
    content = str(head_inner.get("content", ""))
    total_lines = int(head_inner.get("total_lines", 0) or 0)
    size_bytes = int(head_inner.get("size_bytes", meta.get("size_bytes", 0)) or 0)
    mime = str(head_inner.get("mime", meta.get("mime", "text/plain")))
    head_lines = content.split("\n") if content else []

    tail_lines: list[str] = []
    tail_start_line = 0
    if total_lines > 45:
        tail_start_line = max(1, total_lines - 15)
        tail_result = read(
            path=path,
            start_line=tail_start_line,
            end_line=total_lines,
            max_bytes=MAX_READ_BYTES,
        )
        tail_content = str(tail_result.get("result", {}).get("content", ""))
        tail_lines = tail_content.split("\n") if tail_content else []

    return present_auto_preview(
        path=head_inner.get("path", normalize_model_relative_path(path)),
        head_lines=head_lines,
        total_lines=total_lines,
        size_bytes=size_bytes,
        mime=mime,
        kind="text",
        tail_lines=tail_lines or None,
        tail_start_line=tail_start_line,
    )


def _bash_success(
    stdout: str,
    stderr: str = "",
    warnings: list[str] | None = None,
    cwd: str = ".",
) -> dict[str, Any]:
    stdout, trunc_out = _truncate(stdout)
    stderr, trunc_err = _truncate(stderr)
    all_warnings = list(warnings or [])
    if trunc_out or trunc_err:
        all_warnings.append("Command output was truncated.")
    return success_response(
        "bash",
        {
            "exit_code": 0,
            "stdout": stdout,
            "stderr": stderr,
            "elapsed_ms": 0,
            "cwd": normalize_model_relative_path(cwd),
            "routed": True,
        },
        warnings=all_warnings,
        truncated=trunc_out or trunc_err,
    )


def _bash_routed_error(error_type: str, message: str, cwd: str = ".") -> dict[str, Any]:
    return error_response(
        "bash",
        error_type,
        message,
        result={
            "exit_code": 1,
            "stdout": "",
            "stderr": message,
            "elapsed_ms": 0,
            "cwd": normalize_model_relative_path(cwd),
            "routed": True,
        },
    )


def _try_file_preview_command(command: str, cwd: str) -> dict[str, Any] | None:
    parts = _safe_split(command)
    if not parts:
        return None
    cmd, args = parts[0], parts[1:]
    if cmd not in {"cat", "less", "more"}:
        return None
    if len(args) != 1 or args[0].startswith("-"):
        return None

    path = resolve_model_path(args[0], cwd)
    meta = describe(path).get("result", {})
    kind = str(meta.get("kind", "text"))
    mime = str(meta.get("mime", "?"))
    size = int(meta.get("size_bytes", 0) or 0)

    if kind == "image":
        return _bash_success(f"[image file: {mime}, {size} bytes]\n", cwd=cwd)
    if kind == "binary":
        return _bash_success(f"[binary file: {mime}, {size} bytes]\n", cwd=cwd)

    if size > MAX_CAT_FILE_BYTES:
        preview = _build_large_file_preview(path, meta)
        return _bash_success(
            preview,
            warnings=[f"Large file ({size} bytes): showing structured preview."],
            cwd=cwd,
        )

    content, warnings, truncated, inner = _read_text_for_cat(path)
    total_lines = int(inner.get("total_lines", 0) or 0)
    if truncated or total_lines > MAX_CAT_LINE_THRESHOLD:
        preview = _build_large_file_preview(path, meta)
        reason = "Read limit reached" if truncated else f"Long file ({total_lines} lines)"
        return _bash_success(
            preview,
            warnings=[f"{reason}: showing structured preview."],
            cwd=cwd,
        )

    return _bash_success(content, warnings=warnings, cwd=cwd)


_JOB_ID_RE = re.compile(r"^bg_[0-9a-f]{8}$")


def _try_job_command(command: str, cwd: str) -> dict[str, Any] | None:
    parts = _safe_split(command)
    if not parts:
        return None
    cmd, args = parts[0], parts[1:]

    if cmd == "jobs" and not args:
        return _bash_success(json.dumps(list_background_jobs(), ensure_ascii=False, indent=2), cwd=cwd)

    if cmd == "fg" and len(args) == 1 and _JOB_ID_RE.match(args[0]):
        try:
            result = foreground_background_job(args[0])
        except SandboxToolError as exc:
            return _bash_routed_error(exc.error_type, exc.message, cwd=cwd)
        return _bash_success(json.dumps(result, ensure_ascii=False, indent=2), cwd=cwd)

    if cmd == "kill" and len(args) == 1 and _JOB_ID_RE.match(args[0]):
        try:
            result = kill_background_job(args[0])
        except SandboxToolError as exc:
            return _bash_routed_error(exc.error_type, exc.message, cwd=cwd)
        return _bash_success(json.dumps(result, ensure_ascii=False, indent=2), cwd=cwd)

    return None


_SHELL_STRUCTURE_RE = re.compile(r"&&|\|\||;|`|\$\(|>>?|<|\|")


def _try_supervise(command: str, cwd: str = ".") -> dict[str, Any] | None:
    """Handle only supervisor-owned commands; everything else runs as bash."""

    if _SHELL_STRUCTURE_RE.search(command):
        return None

    routed = _try_job_command(command, cwd)
    if routed is not None:
        return routed

    try:
        return _try_file_preview_command(command, cwd)
    except Exception as exc:
        logger.debug("File preview supervision skipped for %r: %s", command, exc)
        return None


def _handle_bash(
    arguments: dict[str, Any],
    _context: dict[str, Any] | None = None,
    *,
    progress_callback: Callable[[float, str], None] | None = None,
) -> dict[str, Any]:
    command = str(arguments.get("command", ""))
    cwd = _normalize_cwd_argument(arguments.get("cwd", "."))

    routed = _try_supervise(command, cwd=cwd)
    if routed is not None:
        return routed

    execution = exec_bash(
        command=command,
        cwd=cwd,
        timeout_s=int(arguments.get("timeout_s", DEFAULT_TIMEOUT)),
        stdin=arguments.get("stdin"),
        on_progress=progress_callback,
        background=arguments.get("background", "auto"),
    )

    result = {
        "command": command,
        "cwd": execution.get("cwd", "."),
        "exit_code": execution.get("exit_code"),
        "stdout": execution.get("stdout", ""),
        "stderr": execution.get("stderr", ""),
        "elapsed_ms": execution.get("elapsed_ms", 0),
    }
    if "job_id" in execution:
        result["job_id"] = execution.get("job_id")

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
    if execution.get("error_type"):
        error_type = str(execution.get("error_type"))
    if execution.get("error") and "timed out" in str(execution["error"]).lower():
        error_type = "timeout"

    return error_response(
        "bash",
        error_type,
        execution.get("error") or "Command failed.",
        result=result,
        warnings=warnings,
        truncated=bool(execution.get("truncated", False)),
    )


def _handle_write(arguments: dict[str, Any], _context: dict[str, Any] | None = None) -> dict[str, Any]:
    return _wrap_workspace_payload(
        "write",
        write(
            path=str(arguments.get("path", "")),
            content=str(arguments.get("content", "")),
        ),
    )


def _handle_share_file(arguments: dict[str, Any], _context: dict[str, Any] | None = None) -> dict[str, Any]:
    raw_path = str(arguments.get("path", "")).strip()
    raw_filename = str(arguments.get("filename", "") or "").strip()
    meta_payload = describe(raw_path)
    meta = meta_payload.get("result", {})
    path = str(meta.get("path") or normalize_model_relative_path(raw_path))
    filename = Path(raw_filename or path).name or "download"
    result = {
        "kind": "shared_file",
        "path": path,
        "filename": filename,
        "mime_type": str(meta.get("mime") or "application/octet-stream"),
        "size_bytes": int(meta.get("size_bytes", 0) or 0),
        "model_context": f"Shared file ready for download: {filename}",
    }
    render, render_warnings = _build_share_render_preview(raw_path, meta)
    if render is not None:
        result["render"] = render
    return success_response("share_file", result, warnings=render_warnings)


def _build_share_render_preview(raw_path: str, meta: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    mime_type = str(meta.get("mime") or "application/octet-stream")
    file_kind = str(meta.get("kind") or "")
    warnings: list[str] = []

    if mime_type.startswith("image/") or file_kind == "image":
        image_payload = read_image(raw_path, include_preview=True, max_preview_bytes=MAX_IMAGE_PREVIEW_BYTES)
        image_result = image_payload.get("result", {}) if isinstance(image_payload, dict) else {}
        render: dict[str, Any] = {
            "type": "image",
            "mime_type": mime_type,
            "preview": image_result.get("preview"),
        }
        if "width" in image_result:
            render["width"] = image_result.get("width")
        if "height" in image_result:
            render["height"] = image_result.get("height")
        warnings.extend(image_payload.get("warnings", []) if isinstance(image_payload, dict) else [])
        return render, warnings

    lower_path = str(meta.get("path") or raw_path).lower()
    if mime_type in {"text/csv", "text/tab-separated-values"} or lower_path.endswith((".csv", ".tsv")):
        table_payload = read(raw_path, max_bytes=min(MAX_READ_BYTES, 131072))
        table_result = table_payload.get("result", {}) if isinstance(table_payload, dict) else {}
        if table_result.get("kind") != "text":
            return None, warnings
        delimiter = "\t" if mime_type == "text/tab-separated-values" or lower_path.endswith(".tsv") else ","
        content = str(table_result.get("content") or "")
        rows = list(csv.reader(content.splitlines(), delimiter=delimiter))
        if not rows:
            return {"type": "table", "format": "csv", "columns": [], "sample_rows": []}, warnings
        header = rows[0]
        sample_rows = rows[1:11]
        return {
            "type": "table",
            "format": "tsv" if delimiter == "\t" else "csv",
            "columns": header,
            "sample_rows": sample_rows,
            "sample_row_count": len(sample_rows),
            "truncated": bool(table_payload.get("truncated", False)),
        }, warnings

    return None, warnings


def _has_argument_value(arguments: dict[str, Any], key: str) -> bool:
    if key not in arguments:
        return False
    value = arguments.get(key)
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _is_lines_edit_arguments(arguments: dict[str, Any]) -> bool:
    mode = str(arguments.get("mode", "") or "").strip().lower()
    if mode == "lines":
        return True
    return _has_argument_value(arguments, "range")


def _line_range_argument(arguments: dict[str, Any]) -> Any:
    return arguments.get("range", "")


def _handle_edit(arguments: dict[str, Any], _context: dict[str, Any] | None = None) -> dict[str, Any]:
    mode = str(arguments.get("mode", "match") or "match").strip().lower()
    if mode == "line":
        mode = "lines"
    if mode not in {"match", "lines"}:
        return error_response("edit", "invalid_arguments", "mode must be 'match' or 'lines'.")
    if mode == "match" and _is_lines_edit_arguments(arguments):
        mode = "lines"

    if mode == "lines":
        range_arg = _line_range_argument(arguments)
        if not str(range_arg or "").strip() and not isinstance(range_arg, (list, tuple)):
            return error_response(
                "edit",
                "invalid_arguments",
                "range is required for mode='lines'.",
            )
        content = arguments.get("content")
        if content is None:
            return error_response(
                "edit",
                "invalid_arguments",
                "content is required for mode='lines'.",
            )
        return _wrap_workspace_payload(
            "edit",
            edit_lines(
                path=str(arguments.get("path", "")),
                range_str=range_arg,
                content=str(content),
                anchor=None if arguments.get("anchor") is None else str(arguments.get("anchor")),
            ),
        )

    if "old_str" not in arguments or "new_str" not in arguments:
        return error_response(
            "edit",
            "invalid_arguments",
            "old_str and new_str are required for mode='match'.",
        )

    return _wrap_workspace_payload(
        "edit",
        edit(
            path=str(arguments.get("path", "")),
            old_str=str(arguments.get("old_str", "")),
            new_str=str(arguments.get("new_str", "")),
            replace_all=bool(arguments.get("replace_all", False)),
        ),
    )


def _load_model_runtime_metadata() -> dict[str, Any]:
    try:
        with MODEL_RUNTIME_METADATA_PATH.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _resolve_active_model_record(context: dict[str, Any] | None) -> tuple[dict[str, Any], str]:
    payload = _load_model_runtime_metadata()
    if not payload:
        return {}, "missing_metadata"

    active = payload.get("active", {})
    if not isinstance(active, dict):
        active = {}

    engine = str((context or {}).get("engine") or active.get("engine") or "").strip()
    model_name = str((context or {}).get("model_name") or active.get("model") or "").strip()
    models = payload.get("models", {})
    if not isinstance(models, dict):
        return {}, "missing_models"

    if engine and model_name:
        model_record = models.get(f"{engine}:{model_name}")
        if isinstance(model_record, dict):
            return model_record, "matched_context"

    active_engine = str(active.get("engine") or "").strip()
    active_model = str(active.get("model") or "").strip()
    if active_engine and active_model:
        model_record = models.get(f"{active_engine}:{active_model}")
        if isinstance(model_record, dict):
            return model_record, "matched_active"

    return {}, "missing_model_record"


def _model_supports_vision(context: dict[str, Any] | None) -> tuple[bool, dict[str, Any], str]:
    model_record, source = _resolve_active_model_record(context)
    capabilities = model_record.get("capabilities", {}) if isinstance(model_record, dict) else {}
    if not isinstance(capabilities, dict):
        capabilities = {}
    return bool(capabilities.get("vision", False)), model_record, source


def _view_image_without_visual_preview(
    image_payload: dict[str, Any],
    model_record: dict[str, Any],
    source: str,
) -> dict[str, Any]:
    result = dict(image_payload)
    result.pop("preview", None)
    result["preview"] = {
        "type": "text_placeholder",
        "message": (
            "Visual preview was withheld because the active model metadata says "
            "this model does not support vision."
        ),
    }
    result["vision_gate"] = {
        "allowed": False,
        "metadata_path": str(MODEL_RUNTIME_METADATA_PATH),
        "metadata_source": source,
        "engine": model_record.get("engine", ""),
        "model": model_record.get("model", ""),
    }
    return result


def _handle_view_image(arguments: dict[str, Any], _context: dict[str, Any] | None = None) -> dict[str, Any]:
    if "path" not in arguments:
        return error_response(
            "view_image",
            "invalid_arguments",
            "path is required.",
        )

    image_payload = read_image(
        path=str(arguments.get("path", "")),
        include_preview=bool(arguments.get("include_preview", True)),
        max_preview_bytes=int(arguments.get("max_preview_bytes", MAX_IMAGE_PREVIEW_BYTES)),
    )
    supports_vision, model_record, metadata_source = _model_supports_vision(_context)
    if not supports_vision and bool(arguments.get("include_preview", True)):
        image_payload = {
            "result": _view_image_without_visual_preview(
                image_payload.get("result", {}),
                model_record,
                metadata_source,
            ),
            "warnings": [
                "Image preview withheld: active model metadata reports supports_vision=false."
            ],
            "truncated": False,
        }

    return _wrap_workspace_payload(
        "view_image",
        image_payload,
    )


BASE_TOOL_HANDLERS: dict[str, Callable[..., dict[str, Any]]] = {
    "bash": _handle_bash,
    "write": _handle_write,
    "edit": _handle_edit,
    "view_image": _handle_view_image,
    "share_file": _handle_share_file,
}


def handle_tool(
    tool_id: str,
    arguments: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
    *,
    progress_callback: Callable[[float, str], None] | None = None,
) -> dict[str, Any]:
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
