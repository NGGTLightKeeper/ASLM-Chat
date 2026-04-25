# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Sandbox tool API.

Public tool surface for the model: bash, write, edit.
All shell commands issued through bash pass through a supervisor that routes
inspection and filesystem commands to internal structured tools transparently.
Execution, builds, git, and compound commands go to real bash.
"""

from __future__ import annotations

import logging
import json
import re
import shlex
import time
from typing import Any, Callable

from sandbox.config import (
    CONTAINER_WORKSPACE,
    DEFAULT_TASK_DIR,
    MAX_CAT_FILE_BYTES,
    MAX_CAT_LINE_THRESHOLD,
    DEFAULT_TIMEOUT,
    MAX_FIND_RESULTS,
    MAX_GREP_RESULTS,
    MAX_LS_ENTRIES,
    MAX_OUTPUT_CHARS,
    MAX_READ_BYTES,
    MODEL_WORKSPACE_CONTAINER,
    RG_TYPE_TO_GLOB,
)
from sandbox.container import exec_bash
from sandbox.container import (
    foreground_background_job,
    kill_background_job,
    list_background_jobs,
)
from sandbox.presenters import (
    present_auto_preview,
    present_grep_results,
    present_read_slice,
)
from sandbox.controller import dispatch as controller_dispatch
from sandbox.session_state import get_session_state
from sandbox.responses import (
    SandboxToolError,
    error_response,
    exception_response,
    success_response,
)
from sandbox.workspace import (
    delete,
    describe,
    edit,
    edit_lines,
    find,
    get_secure_task_path,
    grep,
    ls,
    mkdir,
    move,
    normalize_model_relative_path,
    read,
    resolve_model_path,
    write,
)

logger = logging.getLogger(__name__)

MCP_SERVER = {
    "id": "sandbox",
    "name": "Sandbox",
    "description": (
        "Linux sandbox with shared workspace. "
        "bash for execution, builds, tests, git, and system commands. "
        "File inspection and search return structured previews "
        "with navigation aids automatically. "
        "write and edit for creating/modifying files."
    ),
}

# ── Public tool definitions (visible to the model) ──────────────────

CORE_TOOLS = [
    {
        "id": "bash",
        "name": "Run Bash",
        "description": (
            "Run a shell command inside the Linux container. "
            "Best for: execution, builds, tests, installs, git, curl, and system commands. "
            "File reads and searches are automatically enhanced with structured previews, "
            "metadata headers, and navigation aids. "
            "Returns exit_code, stdout, stderr, elapsed_ms, and cwd. "
            "SCOPE: bash has full access to the entire container filesystem — "
            "use absolute paths like /etc, /usr, /tmp freely when needed. "
            "The default working directory '.' is the sandbox workspace root (/workspace/_sandbox/). "
            "write and edit are restricted to the workspace root only. "
            "PATHS: workspace files use plain relative paths ('script.py', 'subdir/file.py') — "
            "never prefix with '_sandbox/', 'workspace/', '/workspace/', or '/workspace/_sandbox/'; "
            "system/container files use absolute paths ('/etc/hosts', '/tmp/out.txt', '/opt/app/config.py'). "
            "FILES OWNERSHIP: files created by write or edit are owned by root. "
            "To modify them via bash use sudo (e.g. 'sudo sed -i ...' or 'echo text | sudo tee -a file'). "
            "sudo is available without a password. "
            "IMPORTANT: For package managers (apt-get, pip, npm, cargo, etc.), container builds (docker build), "
            "compilation (make, cmake, gcc, rustc, go build), and any long-running install/build commands "
            "always set timeout_s to at least 300. Default timeout of 60s is only for quick commands. "
            "Never use a short timeout for apt-get install, apt-get update, or any build/compile steps."
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
            "PATHS: use plain relative paths for workspace files ('script.py', 'subdir/file.py') — "
            "never prefix with '_sandbox/' or '/workspace/_sandbox/'; "
            "absolute Linux paths ('/opt/app/config.py', '/tmp/out.txt') resolve inside the container. "
            "Windows-style paths are rejected. "
            "Files are created as root — to modify them later via bash use sudo "
            "(e.g. 'sudo sed -i ...' or 'echo text | sudo tee -a file'); "
            "or use the edit tool which also runs as root. "
            "Use write for new files and full rewrites. Returns bytes_written plus "
            "created/overwrote flags. Do not use it for small surgical edits when edit fits better."
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
            "match mode (default): use old_str+new_str for exact literal replacement; fails on missing or ambiguous matches. "
            "lines mode: use range+content to replace a line range; range is 1-based e.g. '12:18' or '12' for one line, '12:11' inserts before line 12. "
            "Lines mode is inferred when range is provided. "
            "Note: content is for lines mode, new_str is for match mode — do not mix them. "
            "PATHS: same as write — plain relative for workspace, absolute for container system files. "
            "Windows-style paths are rejected. "
            "Result keys — both modes: p=file path, cx=context lines array (prefix +LN=changed line, "
            " LN=unchanged neighbor), cxr=context range 'first:last', cxt=context was truncated, "
            "ud=unified diff. "
            "Match mode only: m=total matches found, rep=matches replaced, all=replace_all was set. "
            "Lines mode only: r=applied range 'start:end', rm=lines removed, add=lines added, "
            "n=total lines after edit, d=line count delta."
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
                    "description": "Line range as '3:4', '3', or [3, 4] when mode='lines'.",
                },
                "content": {"type": "string"},
                "anchor": {"type": "string"},
            },
            "required": ["path"],
        },
    },
]

TOOLS = list(CORE_TOOLS)


# ── Internal helpers ─────────────────────────────────────────────────

def _wrap_workspace_payload(tool: str, payload: dict[str, Any]) -> dict[str, Any]:
    return success_response(
        tool,
        payload.get("result"),
        warnings=payload.get("warnings"),
        truncated=bool(payload.get("truncated", False)),
    )


def _format_structured_as_shell(tool_name: str, result: dict[str, Any]) -> str:
    """Render an internal structured-tool result as shell-like text output,
    so the model sees familiar stdout-style output."""

    inner = result.get("result", {})

    if tool_name == "read":
        content = inner.get("content", "")
        if inner.get("kind") == "binary":
            return f"[binary file: {inner.get('mime', '?')}, {inner.get('size_bytes', 0)} bytes]"
        if inner.get("kind") == "image":
            return f"[image: {inner.get('mime', '?')}, {inner.get('size_bytes', 0)} bytes]"
        return present_read_slice(
            path=inner.get("path", "?"),
            content=content,
            start_line=inner.get("start_line", 1),
            end_line=inner.get("end_line", 1),
            total_lines=inner.get("total_lines", 0),
            size_bytes=inner.get("size_bytes", 0),
        )

    if tool_name == "ls":
        entries = inner.get("entries", [])
        lines = []
        for e in entries:
            if e.get("type") == "directory":
                lines.append(f"{e['name']}/")
            else:
                size = e.get("size_bytes")
                if size is not None:
                    lines.append(f"{e['name']}  ({size} bytes)")
                else:
                    lines.append(e["name"])
        return "\n".join(lines) if lines else "(empty directory)"

    if tool_name == "find":
        matches = inner.get("matches", [])
        return "\n".join(m["path"] for m in matches) if matches else "(no matches)"

    if tool_name == "grep":
        matches = inner.get("matches", [])
        return present_grep_results(
            matches=matches,
            pattern=inner.get("pattern", "?"),
            path=inner.get("path", "."),
        )

    if tool_name == "mkdir":
        created = inner.get("created", False)
        path = inner.get("path", "")
        if created:
            return f"created: {path}"
        return f"already exists: {path}"

    if tool_name == "move":
        return f"{inner.get('src', '?')} -> {inner.get('dst', '?')}"

    if tool_name == "delete":
        return f"deleted {inner.get('type', 'path')}: {inner.get('path', '?')}"

    return str(inner)


# ── Bash supervisor: shell command → internal tool router ────────────

# Each route handler receives the regex match and args string, returns a
# bash-shaped response dict if handled, or None to fall through to real bash.

def _build_large_file_preview(path: str, meta: dict[str, Any]) -> str:
    """Build a structured preview for a large file.

    Replaces the dead-end refusal.  The model gets a navigable map
    (structure + head + tail + next-step anchors) instead of a wall.
    """

    # Read content up to MAX_READ_BYTES (for structure extraction + head).
    head_result = read(path=path, max_bytes=MAX_READ_BYTES)
    head_inner = head_result.get("result", {})
    content = head_inner.get("content", "")
    total_lines = head_inner.get("total_lines", 0)
    size_bytes = head_inner.get("size_bytes", meta.get("size_bytes", 0))
    mime = head_inner.get("mime", meta.get("mime", "text/plain"))
    head_lines = content.split("\n") if content else []

    # Read the tail separately (the main read may have been truncated).
    tail_lines: list[str] = []
    tail_start_line = 0
    if total_lines > 45:
        tail_start = max(1, total_lines - 15)
        tail_result = read(
            path=path, start_line=tail_start, end_line=total_lines,
            max_bytes=MAX_READ_BYTES,
        )
        tail_content = tail_result.get("result", {}).get("content", "")
        tail_lines = tail_content.split("\n") if tail_content else []
        tail_start_line = tail_start

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


def _try_route_cat(match: re.Match, args_str: str, cwd: str = ".") -> dict[str, Any] | None:
    """Route: cat [flags] <file>... — supports multi-file and unknown flags."""
    parts = _safe_split(args_str)
    files = [p for p in parts if not p.startswith("-")]
    flags = [p for p in parts if p.startswith("-")]
    if not files:
        return None  # no file → real bash (stdin cat)
    show_numbers = "-n" in flags
    resolved_files = [resolve_model_path(path, cwd) for path in files]
    all_warnings: list[str] = []
    chunks: list[str] = []
    per_file_budget = max(MAX_READ_BYTES // len(files), 4096)
    for path in resolved_files:
        metadata = describe(path)
        meta_inner = metadata.get("result", {})
        size = int(meta_inner.get("size_bytes", 0))
        kind = meta_inner.get("kind", "text")
        if kind == "text" and size > MAX_CAT_FILE_BYTES:
            # Auto-preview for large files instead of dead-end refusal.
            preview = _build_large_file_preview(path, meta_inner)
            all_warnings.append(
                f"Large file ({size} bytes): showing structured preview with navigation aids."
            )
            chunks.append(preview)
        else:
            result = read(path=path, max_bytes=per_file_budget)
            all_warnings.extend(result.get("warnings", []))
            inner = result.get("result", {})
            total_lines = inner.get("total_lines", 0)
            if kind == "text" and total_lines > MAX_CAT_LINE_THRESHOLD:
                # File is small in bytes but long in lines — still show file_map.
                preview = _build_large_file_preview(path, meta_inner)
                all_warnings.append(
                    f"Long file ({total_lines} lines): showing structured preview with navigation aids."
                )
                chunks.append(preview)
            else:
                chunks.append(_format_structured_as_shell("read", result))
    content = "\n".join(chunks)
    if len(content.encode("utf-8", errors="replace")) > MAX_OUTPUT_CHARS:
        content = content.encode("utf-8", errors="replace")[:MAX_OUTPUT_CHARS].decode("utf-8", errors="ignore")
        all_warnings.append("Combined cat output truncated to MAX_OUTPUT_CHARS.")
    if show_numbers:
        content = "\n".join(
            f"{i:>6}\t{line}" for i, line in enumerate(content.split("\n"), 1)
        )
    return _bash_success(content, warnings=all_warnings, cwd=cwd)


def _try_route_head(match: re.Match, args_str: str, cwd: str = ".") -> dict[str, Any] | None:
    """Route: head [-n N] <file>..."""
    parts = _safe_split(args_str)
    n_lines = 10
    files = []
    i = 0
    while i < len(parts):
        if parts[i] == "-n" and i + 1 < len(parts):
            try:
                n_lines = int(parts[i + 1])
            except ValueError:
                return None
            i += 2
        elif parts[i].startswith("-n") and len(parts[i]) > 2:
            try:
                n_lines = int(parts[i][2:])
            except ValueError:
                return None
            i += 1
        elif parts[i].startswith("-") and parts[i] != "-":
            i += 1  # skip unknown flags instead of falling through
        else:
            files.append(parts[i])
            i += 1
    if not files:
        return None
    all_warnings: list[str] = []
    chunks: list[str] = []
    for f in files:
        result = read(
            path=resolve_model_path(f, cwd),
            start_line=1,
            end_line=n_lines,
            max_bytes=MAX_READ_BYTES,
        )
        all_warnings.extend(result.get("warnings", []))
        chunks.append(_format_structured_as_shell("read", result))
    content = "\n".join(chunks)
    return _bash_success(content, warnings=all_warnings, cwd=cwd)


def _try_route_tail(match: re.Match, args_str: str, cwd: str = ".") -> dict[str, Any] | None:
    """Route: tail [-n N] <file>..."""
    parts = _safe_split(args_str)
    n_lines = 10
    files = []
    i = 0
    while i < len(parts):
        if parts[i] == "-n" and i + 1 < len(parts):
            try:
                n_lines = int(parts[i + 1])
            except ValueError:
                return None
            i += 2
        elif parts[i].startswith("-n") and len(parts[i]) > 2:
            try:
                n_lines = int(parts[i][2:])
            except ValueError:
                return None
            i += 1
        elif parts[i].startswith("-") and parts[i] != "-":
            i += 1  # skip unknown flags instead of falling through
        else:
            files.append(parts[i])
            i += 1
    if not files:
        return None
    all_warnings: list[str] = []
    chunks: list[str] = []
    for f in files:
        target = resolve_model_path(f, cwd)
        full = read(path=target, max_bytes=MAX_READ_BYTES)
        total = full.get("result", {}).get("total_lines", 0)
        if total == 0:
            chunks.append("")
            continue
        start = max(1, total - n_lines + 1)
        result = read(path=target, start_line=start, end_line=total, max_bytes=MAX_READ_BYTES)
        all_warnings.extend(result.get("warnings", []))
        chunks.append(_format_structured_as_shell("read", result))
    content = "\n".join(chunks)
    return _bash_success(content, warnings=all_warnings, cwd=cwd)


def _try_route_ls(match: re.Match, args_str: str, cwd: str = ".") -> dict[str, Any] | None:
    """Route: ls [flags] [path]."""
    parts = _safe_split(args_str)
    path = "."
    include_hidden = False
    for p in parts:
        if p.startswith("-"):
            if "a" in p:
                include_hidden = True
        else:
            path = p
    result = ls(
        path=resolve_model_path(path, cwd),
        depth=1,
        max_entries=MAX_LS_ENTRIES,
        include_hidden=include_hidden,
    )
    content = _format_structured_as_shell("ls", result)
    return _bash_success(content, warnings=result.get("warnings", []), cwd=cwd)


def _try_route_tree(match: re.Match, args_str: str, cwd: str = ".") -> dict[str, Any] | None:
    """Route: tree [path] [-L depth]."""
    parts = _safe_split(args_str)
    path = "."
    depth = 3
    include_hidden = False
    i = 0
    while i < len(parts):
        p = parts[i]
        if p == "-L" and i + 1 < len(parts):
            try:
                depth = int(parts[i + 1])
            except ValueError:
                return None
            i += 2
        elif p == "-a":
            include_hidden = True
            i += 1
        elif p.startswith("-"):
            i += 1  # skip unknown flags silently
        else:
            path = p
            i += 1
    resolved_path = resolve_model_path(path, cwd)
    result = ls(path=resolved_path, depth=depth, max_entries=MAX_LS_ENTRIES, include_hidden=include_hidden)
    entries = result.get("result", {}).get("entries", [])
    if not entries:
        return _bash_success(f"{resolved_path}\n\n0 directories, 0 files", cwd=cwd)
    # Build tree-like output
    lines = [resolved_path]
    dirs = 0
    files_count = 0
    for e in entries:
        indent = "  " * e.get("depth", 1)
        name = e["name"]
        if e.get("type") == "directory":
            lines.append(f"{indent}{name}/")
            dirs += 1
        else:
            lines.append(f"{indent}{name}")
            files_count += 1
    lines.append(f"\n{dirs} directories, {files_count} files")
    return _bash_success("\n".join(lines), warnings=result.get("warnings", []), cwd=cwd)


def _try_route_find(match: re.Match, args_str: str, cwd: str = ".") -> dict[str, Any] | None:
    """Route: find <path> [-name pattern] [-type f|d] [-maxdepth N]."""
    parts = _safe_split(args_str)
    path = "."
    name_pattern = None
    find_type = None
    max_depth = 8
    i = 0
    positional_done = False
    while i < len(parts):
        p = parts[i]
        if p == "-name" and i + 1 < len(parts):
            name_pattern = parts[i + 1]
            positional_done = True
            i += 2
        elif p == "-type" and i + 1 < len(parts):
            t = parts[i + 1]
            if t == "f":
                find_type = "file"
            elif t == "d":
                find_type = "directory"
            positional_done = True
            i += 2
        elif p == "-maxdepth" and i + 1 < len(parts):
            try:
                max_depth = int(parts[i + 1])
            except ValueError:
                return None
            positional_done = True
            i += 2
        elif p.startswith("-"):
            # Unknown flag (e.g. -exec, -regex) → real bash
            return None
        elif not positional_done:
            path = p
            positional_done = True
            i += 1
        else:
            return None
    result = find(
        path=resolve_model_path(path, cwd),
        name_pattern=name_pattern,
        type_filter=find_type,
        max_depth=max_depth,
        max_results=MAX_FIND_RESULTS,
    )
    content = _format_structured_as_shell("find", result)
    return _bash_success(content, warnings=result.get("warnings", []), cwd=cwd)


_RG_TYPE_TO_GLOB = RG_TYPE_TO_GLOB


def _try_route_grep(match: re.Match, args_str: str, cwd: str = ".") -> dict[str, Any] | None:
    """Route: grep/rg [-r] [-i] [-n] [-C N] [-A N] [-B N] [--type T] <pattern> [path]."""
    parts = _safe_split(args_str)
    pattern = None
    path = "."
    case_sensitive = True
    context_before = 0
    context_after = 0
    glob_pattern = None
    i = 0
    while i < len(parts):
        p = parts[i]
        if p in ("-r", "-R", "--recursive", "-rn", "-nr"):
            if "i" in p:
                case_sensitive = False
            i += 1
        elif p in ("-i", "--ignore-case", "-ri", "-ir", "-rin", "-rni", "-rni"):
            case_sensitive = False
            i += 1
        elif p in ("-n", "--line-number"):
            i += 1
        elif p in ("-l", "--files-with-matches"):
            i += 1
        elif p == "--include" and i + 1 < len(parts):
            glob_pattern = parts[i + 1]
            i += 2
        elif p in ("-g", "--glob") and i + 1 < len(parts):
            glob_pattern = parts[i + 1]
            i += 2
        elif p in ("-t", "--type") and i + 1 < len(parts):
            type_name = parts[i + 1].lower()
            mapped = _RG_TYPE_TO_GLOB.get(type_name)
            if mapped:
                glob_pattern = mapped
            i += 2
        elif p.startswith("--type="):
            type_name = p.split("=", 1)[1].lower()
            mapped = _RG_TYPE_TO_GLOB.get(type_name)
            if mapped:
                glob_pattern = mapped
            i += 1
        elif p in ("-C", "--context") and i + 1 < len(parts):
            try:
                context_before = context_after = int(parts[i + 1])
            except ValueError:
                return None
            i += 2
        elif p in ("-A", "--after-context") and i + 1 < len(parts):
            try:
                context_after = int(parts[i + 1])
            except ValueError:
                return None
            i += 2
        elif p in ("-B", "--before-context") and i + 1 < len(parts):
            try:
                context_before = int(parts[i + 1])
            except ValueError:
                return None
            i += 2
        elif p in ("-e", "--regexp") and i + 1 < len(parts):
            # -e <pattern> is a standard grep flag; treat it as the pattern.
            if pattern is None:
                pattern = parts[i + 1]
            i += 2
        elif p.startswith("-"):
            # Unknown flags — skip rather than falling to real bash.
            # If the flag takes a value argument, try to skip it too.
            if i + 1 < len(parts) and not parts[i + 1].startswith("-"):
                i += 2
            else:
                i += 1
        elif pattern is None:
            pattern = p
            i += 1
        else:
            path = p
            i += 1
    if not pattern:
        return None
    result = grep(
        pattern=pattern,
        path=resolve_model_path(path, cwd),
        glob=glob_pattern,
        case_sensitive=case_sensitive,
        context_before=context_before,
        context_after=context_after,
        max_results=MAX_GREP_RESULTS,
    )
    content = _format_structured_as_shell("grep", result)
    return _bash_success(content, warnings=result.get("warnings", []), cwd=cwd)


def _try_route_sed_read(match: re.Match, args_str: str, cwd: str = ".") -> dict[str, Any] | None:
    """Route: sed -n '<start>,<end>p' <file> → read with line range."""
    parts = _safe_split(args_str)
    if len(parts) < 2:
        return None
    range_expr = None
    file_path = None
    i = 0
    while i < len(parts):
        p = parts[i]
        if p == "-n":
            i += 1
        elif range_expr is None and re.match(r"^['\"]?\d+,\d+p['\"]?$", p):
            range_expr = p.strip("'\"")
            i += 1
        elif range_expr is None and re.match(r"^['\"]?\d+p['\"]?$", p):
            range_expr = p.strip("'\"")
            i += 1
        elif not p.startswith("-"):
            file_path = p
            i += 1
        else:
            return None
    if not range_expr or not file_path:
        return None
    range_match = re.match(r"(\d+)(?:,(\d+))?p", range_expr)
    if not range_match:
        return None
    start = int(range_match.group(1))
    end = int(range_match.group(2)) if range_match.group(2) else start
    result = read(
        path=resolve_model_path(file_path, cwd),
        start_line=start,
        end_line=end,
        max_bytes=MAX_READ_BYTES,
    )
    content = _format_structured_as_shell("read", result)
    return _bash_success(content, warnings=result.get("warnings", []), cwd=cwd)


def _try_route_wc(match: re.Match, args_str: str, cwd: str = ".") -> dict[str, Any] | None:
    """Route: wc [-l] <file> → read metadata."""
    parts = _safe_split(args_str)
    files = [p for p in parts if not p.startswith("-")]
    if len(files) != 1:
        return None
    target = resolve_model_path(files[0], cwd)
    result = read(path=target, max_bytes=MAX_READ_BYTES)
    inner = result.get("result", {})
    # If the file is binary or was truncated, let real bash give accurate counts.
    if inner.get("kind") != "text" or result.get("truncated"):
        return None
    total_lines = inner.get("total_lines", 0)
    size_bytes = inner.get("size_bytes", 0)
    content_text = inner.get("content", "")
    word_count = len(content_text.split()) if content_text else 0
    flags = [p for p in parts if p.startswith("-")]
    if "-l" in flags:
        output = f"{total_lines} {target}"
    else:
        output = f"  {total_lines}  {word_count}  {size_bytes} {target}"
    return _bash_success(output, cwd=cwd)


def _try_route_mkdir(match: re.Match, args_str: str, cwd: str = ".") -> dict[str, Any] | None:
    """Route: mkdir [-p] <path>."""
    parts = _safe_split(args_str)
    parents = False
    dirs = []
    for p in parts:
        if p in ("-p", "--parents"):
            parents = True
        elif p.startswith("-"):
            return None
        else:
            dirs.append(p)
    if len(dirs) != 1:
        return None
    result = mkdir(path=resolve_model_path(dirs[0], cwd), parents=parents)
    get_session_state().invalidate_survey_cache()
    # time.sleep(0.05)  # removed wsl2 workaround
    content = _format_structured_as_shell("mkdir", result)
    return _bash_success(content, warnings=result.get("warnings", []), cwd=cwd)


def _try_route_touch(match: re.Match, args_str: str, cwd: str = ".") -> dict[str, Any] | None:
    """Route: touch <file> → create empty file if it doesn't exist."""
    parts = _safe_split(args_str)
    files = [p for p in parts if not p.startswith("-")]
    if len(files) != 1:
        return None
    path = resolve_model_path(files[0], cwd)
    try:
        target = get_secure_task_path(path)
    except (SandboxToolError, ValueError):
        return None
    if target.is_dir():
        return None  # touch on existing dir is a no-op; let real bash handle it
    if target.exists():
        return _bash_success("", cwd=cwd)  # file exists, touch is a no-op
    result = write(path=path, content="")
    get_session_state().invalidate_survey_cache()
    return _bash_success("", warnings=result.get("warnings", []), cwd=cwd)


def _try_route_mv(match: re.Match, args_str: str, cwd: str = ".") -> dict[str, Any] | None:
    """Route: mv [-f] <src> <dst>."""
    parts = _safe_split(args_str)
    overwrite = False
    paths = []
    for p in parts:
        if p in ("-f", "--force"):
            overwrite = True
        elif p.startswith("-"):
            return None
        else:
            paths.append(p)
    if len(paths) != 2:
        return None
    result = move(
        src=resolve_model_path(paths[0], cwd),
        dst=resolve_model_path(paths[1], cwd),
        overwrite=overwrite,
    )
    get_session_state().invalidate_survey_cache()
    # time.sleep(0.05)  # removed wsl2 workaround
    content = _format_structured_as_shell("move", result)
    return _bash_success(content, warnings=result.get("warnings", []), cwd=cwd)


def _try_route_cp(match: re.Match, args_str: str, cwd: str = ".") -> dict[str, Any] | None:
    """Route: cp <src> <dst> — single-file copy only, complex cp goes to real bash."""
    parts = _safe_split(args_str)
    paths = []
    for p in parts:
        if p in ("-r", "-R", "--recursive", "-a"):
            # Recursive copy → real bash (we don't have internal recursive copy)
            return None
        elif p.startswith("-"):
            return None
        else:
            paths.append(p)
    if len(paths) != 2:
        return None
    # Single-file copy: read then write
    try:
        source = read(path=resolve_model_path(paths[0], cwd), max_bytes=MAX_READ_BYTES)
        inner = source.get("result", {})
        if inner.get("kind") != "text":
            return None  # binary/image copy → real bash
        content = inner.get("content", "")
        result = write(path=resolve_model_path(paths[1], cwd), content=content)
        get_session_state().invalidate_survey_cache()
        # time.sleep(0.05)  # removed wsl2 workaround
        return _bash_success("", warnings=result.get("warnings", []), cwd=cwd)
    except Exception:
        return None


def _try_route_rm(match: re.Match, args_str: str, cwd: str = ".") -> dict[str, Any] | None:
    """Route: rm [-r] [-f] <path>."""
    parts = _safe_split(args_str)
    recursive = False
    paths = []
    for p in parts:
        if p in ("-r", "-R", "--recursive", "-rf", "-fr"):
            recursive = True
        elif p in ("-f", "--force"):
            pass  # force is implicit in our delete
        elif p.startswith("-"):
            return None
        else:
            paths.append(p)
    if len(paths) != 1:
        return None
    result = delete(path=resolve_model_path(paths[0], cwd), recursive=recursive)
    get_session_state().invalidate_survey_cache()
    # time.sleep(0.05)  # removed wsl2 workaround
    content = _format_structured_as_shell("delete", result)
    return _bash_success(content, warnings=result.get("warnings", []), cwd=cwd)


def _try_route_pwd(match: re.Match, args_str: str, cwd: str = ".") -> dict[str, Any] | None:
    """Route: pwd for simple commands without asking real bash."""

    normalized_cwd = normalize_model_relative_path(cwd)
    if normalized_cwd in ("", "."):
        return _bash_success(f"{MODEL_WORKSPACE_CONTAINER}\n", cwd=cwd)
    return _bash_success(f"{MODEL_WORKSPACE_CONTAINER}/{normalized_cwd}\n", cwd=cwd)


def _try_route_file(match: re.Match, args_str: str, cwd: str = ".") -> dict[str, Any] | None:
    """Route: file <path> → read metadata."""
    parts = _safe_split(args_str)
    files = [p for p in parts if not p.startswith("-")]
    if len(files) != 1:
        return None
    target = resolve_model_path(files[0], cwd)
    result = describe(path=target)
    inner = result.get("result", {})
    kind = inner.get("kind", "unknown")
    mime = inner.get("mime", "application/octet-stream")
    size = inner.get("size_bytes", 0)
    return _bash_success(f"{target}: {mime} ({kind}, {size} bytes)", cwd=cwd)


def _try_route_stat(match: re.Match, args_str: str, cwd: str = ".") -> dict[str, Any] | None:
    """Route: stat <path> → file metadata."""
    parts = _safe_split(args_str)
    files = [p for p in parts if not p.startswith("-")]
    if len(files) != 1:
        return None
    result = describe(path=resolve_model_path(files[0], cwd))
    inner = result.get("result", {})
    path = inner.get("path", files[0])
    size = inner.get("size_bytes", 0)
    kind = inner.get("kind", "unknown")
    mime = inner.get("mime", "?")
    lines = [
        f"  File: {path}",
        f"  Size: {size} bytes",
        f"  Type: {kind}",
        f"  MIME: {mime}",
    ]
    if inner.get("total_lines"):
        lines.append(f" Lines: {inner['total_lines']}")
    return _bash_success("\n".join(lines), cwd=cwd)


_JOB_ID_RE = re.compile(r"^bg_[0-9a-f]{8}$")


def _try_route_jobs(match: re.Match, args_str: str, cwd: str = ".") -> dict[str, Any] | None:
    """Route: jobs → list sandbox background jobs."""

    if args_str.strip():
        return None
    result = list_background_jobs()
    return _bash_success(json.dumps(result, ensure_ascii=False, indent=2), cwd=cwd)


def _try_route_fg(match: re.Match, args_str: str, cwd: str = ".") -> dict[str, Any] | None:
    """Route: fg bg_<id> → poll a sandbox background job."""

    parts = _safe_split(args_str)
    if len(parts) != 1 or not _JOB_ID_RE.match(parts[0]):
        return None
    try:
        result = foreground_background_job(parts[0])
    except SandboxToolError as exc:
        return _bash_routed_error(exc.error_type, exc.message, cwd=cwd)
    return _bash_success(json.dumps(result, ensure_ascii=False, indent=2), cwd=cwd)


def _try_route_kill_job(match: re.Match, args_str: str, cwd: str = ".") -> dict[str, Any] | None:
    """Route: kill bg_<id> → kill a sandbox background job."""

    parts = _safe_split(args_str)
    if len(parts) != 1 or not _JOB_ID_RE.match(parts[0]):
        return None
    try:
        result = kill_background_job(parts[0])
    except SandboxToolError as exc:
        return _bash_routed_error(exc.error_type, exc.message, cwd=cwd)
    return _bash_success(json.dumps(result, ensure_ascii=False, indent=2), cwd=cwd)


def _safe_split(s: str) -> list[str]:
    """Split a string into shell tokens, falling back to plain split."""
    try:
        return shlex.split(s)
    except ValueError:
        return s.split()


def _normalize_cwd_argument(raw_cwd: Any) -> str:
    """Normalize a bash cwd argument and treat null-like values as root."""

    if raw_cwd is None:
        return "."
    cwd = str(raw_cwd).strip()
    if not cwd or cwd.lower() == "none":
        return "."
    return cwd


def _extract_target_path(args_str: str, cwd: str = ".", skip_first: bool = False) -> str | None:
    """Extract the primary file/directory target from command arguments.

    Used by session state to track what the model is looking at.
    skip_first=True skips the first non-flag argument (for grep/rg where
    the first non-flag arg is the pattern, not the path).
    Returns the resolved path, or None.
    """

    parts = _safe_split(args_str)
    skipped = 0
    for p in parts:
        if not p.startswith("-"):
            if skip_first and skipped == 0:
                skipped += 1
                continue
            return resolve_model_path(p, cwd)
    return None


def _bash_success(
    stdout: str,
    stderr: str = "",
    warnings: list[str] | None = None,
    cwd: str = ".",
) -> dict[str, Any]:
    """Build a bash-shaped success envelope from routed output."""
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
        warnings=warnings,
    )


def _bash_error(
    message: str,
    stderr: str = "",
    exit_code: int = 1,
    cwd: str = ".",
) -> dict[str, Any]:
    """Build a bash-shaped error envelope from a routed failure."""
    return error_response(
        "bash",
        "process_error",
        message,
        result={
            "exit_code": exit_code,
            "stdout": "",
            "stderr": stderr or message,
            "elapsed_ms": 0,
            "cwd": normalize_model_relative_path(cwd),
            "routed": True,
        },
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


def _is_path_resolution_error(exc: Exception) -> bool:
    """Return True when a supervisor failure should fall back to real bash."""

    message = str(exc)
    if isinstance(exc, (FileNotFoundError, NotADirectoryError)):
        return True
    if isinstance(exc, ValueError):
        path_markers = (
            "must be relative to the model workspace root",
            "Access denied:",
            "Path not found:",
            "File not found:",
            "Not a directory:",
        )
        return any(marker in message for marker in path_markers)
    return False


# Ordered list of (command name, router-function).
# Only simple single-command patterns are matched; pipes, chains, and
# subshells are intentionally NOT intercepted and go to real bash.
_SIMPLE_COMMAND_RE = re.compile(
    r"^\s*(?:cd\s+(?P<cd_target>\S+)\s*[;&]\s*)?(?P<cmd>[a-z]+)\s*(?P<args>.*?)\s*$",
    re.DOTALL,
)

_ROUTES: list[tuple[str, Callable[..., dict[str, Any] | None]]] = [
    # File reading
    ("cat", _try_route_cat),
    ("head", _try_route_head),
    ("tail", _try_route_tail),
    ("less", _try_route_cat),
    ("more", _try_route_cat),
    # Navigation & search
    ("ls", _try_route_ls),
    ("tree", _try_route_tree),
    ("pwd", _try_route_pwd),
    ("find", _try_route_find),
    ("fd", _try_route_find),
    ("grep", _try_route_grep),
    ("egrep", _try_route_grep),
    ("rg", _try_route_grep),
    # Line-range reading
    ("sed", _try_route_sed_read),
    # File metadata
    ("wc", _try_route_wc),
    ("file", _try_route_file),
    ("stat", _try_route_stat),
    # Background job pseudo-commands
    ("jobs", _try_route_jobs),
    ("fg", _try_route_fg),
    ("kill", _try_route_kill_job),
    # Filesystem mutations
    ("mkdir", _try_route_mkdir),
    ("touch", _try_route_touch),
    ("mv", _try_route_mv),
    ("cp", _try_route_cp),
    ("rm", _try_route_rm),
]

_ROUTE_MAP: dict[str, Callable[..., dict[str, Any] | None]] = {
    name: fn for name, fn in _ROUTES
}

# Only plain `|` pipelines between read-only commands go through
# the intent controller.  &&, ||, ;, subshells, and redirections
# still go directly to real bash.
_CHAIN_PATTERN = re.compile(r"&&|\|\||;|`|\$\(|>>?|<")

# Commands whose output is primarily file content — even when they fall
# through to real bash we enforce MAX_READ_BYTES on stdout.
_READ_LIKE_COMMANDS = frozenset({
    "cat", "head", "tail", "less", "more", "sed", "awk",
    "grep", "egrep", "rg", "ag", "strings", "xxd", "hexdump",
})


_READ_COMMANDS = frozenset({"cat", "head", "tail", "less", "more", "sed"})
_SEARCH_COMMANDS = frozenset({"grep", "egrep", "rg"})
_SURVEY_COMMANDS = frozenset({"ls", "tree", "find", "fd"})

# Commands fully owned by the intent controller.
# If controller_dispatch() returns None for these, they go straight to real
# bash — the legacy _ROUTE_MAP must not intercept them.  Without this guard
# the legacy parsers silently return wrong output for unsupported flags
# (e.g. grep -v, grep -F, tail -f, find -type l).
_INTENT_ONLY_COMMANDS = _READ_COMMANDS | _SEARCH_COMMANDS | _SURVEY_COMMANDS


def _try_supervise(command: str, cwd: str = ".") -> dict[str, Any] | None:
    """Try to route a shell command to an internal structured tool.

    Returns a bash-shaped response dict if the command was handled,
    or None if it should go to real bash.

    Routing order:
      1. Intent controller — handles OPEN/LOCATE/SURVEY including compound
         read-only pipelines (cat x | head, cat x | grep, etc.)
      2. _ROUTE_MAP — handles MUTATE commands (mkdir, mv, cp, rm, touch)
         and falls back for anything the controller doesn't cover
    """

    # Complex chains (&&, ||, ;, subshells, redirections) always go to
    # real bash — intent controller only handles plain `|` pipelines.
    if _CHAIN_PATTERN.search(command):
        return None

    state = get_session_state()

    # 1) Intent controller: OPEN / LOCATE / SURVEY (+ compound pipelines)
    try:
        routed = controller_dispatch(
            command=command,
            cwd=cwd,
            state=state,
            make_bash_success=_bash_success,
            make_bash_error=lambda msg, stderr="", cwd=cwd: _bash_error(
                msg, stderr=stderr, exit_code=1, cwd=cwd
            ),
        )
    except Exception as exc:
        if _is_path_resolution_error(exc):
            logger.debug(
                "Controller path resolution failed for %r; falling back to real bash: %s",
                command, exc,
            )
            return None
        logger.debug("Controller dispatch error for %r: %s", command, exc)
        return None

    if routed is not None:
        # Inject compact exploration context
        ctx = state.compact_context()
        if ctx and routed.get("ok"):
            stdout = routed.get("result", {}).get("stdout", "")
            if stdout:
                routed["result"]["stdout"] = f"{stdout}\n\n{ctx}"
        return routed

    # 2) No compound pipelines past this point for _ROUTE_MAP
    m = _SIMPLE_COMMAND_RE.match(command)
    if not m:
        return None

    cd_target = m.group("cd_target")
    if cd_target:
        try:
            cwd = resolve_model_path(cd_target, cwd)
            get_secure_task_path(cwd, kind="cwd")  # fail-fast on escape attempts
        except (SandboxToolError, ValueError):
            return None  # Let real bash handle invalid or out-of-sandbox paths in cd

    cmd = m.group("cmd")
    args_str = m.group("args")

    # Intent-only commands: controller already decided to fall through (returned
    # None), so the legacy router must not intercept them.  Intercepting would
    # silently return wrong output for unsupported flags (grep -v, tail -f, etc.)
    if cmd in _INTENT_ONLY_COMMANDS:
        return None

    router = _ROUTE_MAP.get(cmd)
    if router is None:
        return None

    try:
        result = router(m, args_str, cwd)
    except Exception as exc:
        if _is_path_resolution_error(exc):
            logger.debug(
                "Supervisor path resolution failed for '%s'; falling back: %s",
                cmd, exc,
            )
            return None
        logger.debug("Supervisor routing failed for '%s': %s", cmd, exc)
        return None

    if result is None:
        return None

    # Update session state for ROUTE_MAP-handled commands
    # For search commands (grep/rg) the first non-flag arg is the pattern,
    # not the path — skip it to get the actual target path.
    target_file = _extract_target_path(args_str, cwd, skip_first=(cmd in _SEARCH_COMMANDS))
    if cmd in _READ_COMMANDS:
        state.record_touch(target_file, "open")
    elif cmd in _SEARCH_COMMANDS:
        state.record_touch(target_file, "locate")
    elif cmd in _SURVEY_COMMANDS:
        state.record_touch(target_file, "survey")

    # Inject compact exploration context
    ctx = state.compact_context()
    if ctx and result.get("ok"):
        stdout = result.get("result", {}).get("stdout", "")
        if stdout:
            result["result"]["stdout"] = f"{stdout}\n\n{ctx}"

    return result


# ── Tool handlers ────────────────────────────────────────────────────

def _handle_bash(
    arguments: dict[str, Any],
    _context: dict[str, Any] | None = None,
    *,
    progress_callback: Callable[[float, str], None] | None = None,
) -> dict[str, Any]:
    command = str(arguments.get("command", ""))
    cwd = _normalize_cwd_argument(arguments.get("cwd", "."))

    # Try supervisor routing first.
    routed = _try_supervise(command, cwd=cwd)
    if routed is not None:
        return routed

    # Real bash execution.
    execution = exec_bash(
        command=command,
        cwd=cwd,
        timeout_s=int(arguments.get("timeout_s", DEFAULT_TIMEOUT)),
        stdin=arguments.get("stdin"),
        on_progress=progress_callback,
        background=arguments.get("background", "auto"),
    )

    # Extra guard: for read-like commands that slipped past the router
    # (e.g. compound pipes, exotic flags), cap stdout at MAX_READ_BYTES
    # so the model cannot receive an unbounded file dump.
    stdout = execution.get("stdout", "")
    read_like_truncated = False
    leading_cmd = command.strip().split()[0] if command.strip() else ""
    if leading_cmd in _READ_LIKE_COMMANDS and len(stdout.encode("utf-8", errors="replace")) > MAX_READ_BYTES:
        stdout = stdout.encode("utf-8", errors="replace")[:MAX_READ_BYTES].decode("utf-8", errors="ignore")
        read_like_truncated = True

    result = {
        "command": command,
        "cwd": execution.get("cwd", "."),
        "exit_code": execution.get("exit_code"),
        "stdout": stdout,
        "stderr": execution.get("stderr", ""),
        "elapsed_ms": execution.get("elapsed_ms", 0),
    }
    if "job_id" in execution:
        result["job_id"] = execution.get("job_id")
    warnings = []
    if execution.get("truncated") or read_like_truncated:
        warnings.append("Command output was truncated.")

    if execution.get("error") is None and execution.get("exit_code") == 0:
        get_session_state().invalidate_survey_cache()
        return success_response(
            "bash",
            result,
            warnings=warnings,
            truncated=bool(execution.get("truncated", False)),
        )

    error_type = "process_error"
    if execution.get("error_type"):
        error_type = str(execution.get("error_type"))
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


def _handle_write(arguments: dict[str, Any], _context: dict[str, Any] | None = None) -> dict[str, Any]:
    result = _wrap_workspace_payload(
        "write",
        write(
            path=str(arguments.get("path", "")),
            content=str(arguments.get("content", "")),
        ),
    )
    get_session_state().invalidate_survey_cache()
    # time.sleep(0.05)  # removed wsl2 workaround
    return result


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
                "content or new_str is required for mode='lines'.",
            )
        result = _wrap_workspace_payload(
            "edit",
            edit_lines(
                path=str(arguments.get("path", "")),
                range_str=range_arg,
                content=str(content),
                anchor=(
                    None
                    if arguments.get("anchor") is None
                    else str(arguments.get("anchor"))
                ),
            ),
        )
        get_session_state().invalidate_survey_cache()
        return result

    if "old_str" not in arguments or "new_str" not in arguments:
        return error_response(
            "edit",
            "invalid_arguments",
            "old_str and new_str are required for mode='match'.",
        )

    result = _wrap_workspace_payload(
        "edit",
        edit(
            path=str(arguments.get("path", "")),
            old_str=str(arguments.get("old_str", "")),
            new_str=str(arguments.get("new_str", "")),
            replace_all=bool(arguments.get("replace_all", False)),
        ),
    )
    get_session_state().invalidate_survey_cache()
    # time.sleep(0.05)  # removed wsl2 workaround
    return result


# ── Handler registry ─────────────────────────────────────────────────

BASE_TOOL_HANDLERS: dict[str, Callable[..., dict[str, Any]]] = {
    "bash": _handle_bash,
    "write": _handle_write,
    "edit": _handle_edit,
}


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
