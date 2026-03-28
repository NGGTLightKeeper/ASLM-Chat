"""Sandbox v2 tool API.

Public tool surface for the model: bash, write, edit.
All shell commands issued through bash pass through a supervisor that routes
inspection and filesystem commands to internal structured tools transparently.
Execution, builds, git, and compound commands go to real bash.
"""

from __future__ import annotations

import logging
import re
import shlex
from typing import Any, Callable

from sandbox.config import (
    DEFAULT_TIMEOUT,
    MAX_FIND_RESULTS,
    MAX_GREP_RESULTS,
    MAX_LS_ENTRIES,
    MAX_READ_BYTES,
)
from sandbox.container import exec_bash
from sandbox.responses import error_response, exception_response, success_response
from sandbox.workspace import delete, edit, find, grep, ls, mkdir, move, read, write

logger = logging.getLogger(__name__)

MCP_SERVER = {
    "id": "sandbox",
    "name": "Sandbox",
    "description": (
        "Linux sandbox with shared workspace. "
        "bash is the primary interface — use it for everything: "
        "navigation, inspection, search, execution, builds, installs, tests, "
        "and filesystem operations. "
        "write and edit are for creating/modifying files."
    ),
}

# ── Public tool definitions (visible to the model) ──────────────────

CORE_TOOLS = [
    {
        "id": "bash",
        "name": "Run Bash",
        "description": (
            "Run a shell command inside the Linux container. Use this for everything: "
            "file inspection (cat, head, tail, less), search (grep, find, fd, rg, glob patterns), "
            "navigation (ls, tree, pwd, du, stat, file), "
            "filesystem operations (mkdir, mv, cp, rm, touch, chmod), "
            "execution, tests, builds, installs, git, curl, and any CLI tools. "
            "Returns exit_code, stdout, stderr, elapsed_ms, and cwd."
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
        return content

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
        if not matches:
            return "(no matches)"
        lines = []
        for m in matches:
            lines.append(f"{m['path']}:{m['line_number']}:{m['line']}")
        return "\n".join(lines)

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

def _try_route_cat(match: re.Match, args_str: str) -> dict[str, Any] | None:
    """Route: cat <file> [with optional flags like -n]."""
    parts = _safe_split(args_str)
    files = [p for p in parts if not p.startswith("-")]
    flags = [p for p in parts if p.startswith("-")]
    if not files or len(files) > 1:
        return None  # multi-file cat or no file → real bash
    path = files[0]
    result = read(path=path, max_bytes=MAX_READ_BYTES)
    content = _format_structured_as_shell("read", result)
    if "-n" in flags:
        numbered = "\n".join(
            f"{i:>6}\t{line}" for i, line in enumerate(content.split("\n"), 1)
        )
        content = numbered
    return _bash_success(content, warnings=result.get("warnings", []))


def _try_route_head(match: re.Match, args_str: str) -> dict[str, Any] | None:
    """Route: head [-n N] <file>."""
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
            return None
        else:
            files.append(parts[i])
            i += 1
    if len(files) != 1:
        return None
    result = read(path=files[0], start_line=1, end_line=n_lines, max_bytes=MAX_READ_BYTES)
    content = _format_structured_as_shell("read", result)
    return _bash_success(content, warnings=result.get("warnings", []))


def _try_route_tail(match: re.Match, args_str: str) -> dict[str, Any] | None:
    """Route: tail [-n N] <file>."""
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
            return None
        else:
            files.append(parts[i])
            i += 1
    if len(files) != 1:
        return None
    full = read(path=files[0], max_bytes=MAX_READ_BYTES)
    total = full.get("result", {}).get("total_lines", 0)
    if total == 0:
        return _bash_success("")
    start = max(1, total - n_lines + 1)
    result = read(path=files[0], start_line=start, end_line=total, max_bytes=MAX_READ_BYTES)
    content = _format_structured_as_shell("read", result)
    return _bash_success(content, warnings=result.get("warnings", []))


def _try_route_ls(match: re.Match, args_str: str) -> dict[str, Any] | None:
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
    result = ls(path=path, depth=1, max_entries=MAX_LS_ENTRIES, include_hidden=include_hidden)
    content = _format_structured_as_shell("ls", result)
    return _bash_success(content, warnings=result.get("warnings", []))


def _try_route_tree(match: re.Match, args_str: str) -> dict[str, Any] | None:
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
    result = ls(path=path, depth=depth, max_entries=MAX_LS_ENTRIES, include_hidden=include_hidden)
    entries = result.get("result", {}).get("entries", [])
    if not entries:
        return _bash_success(f"{path}\n\n0 directories, 0 files")
    # Build tree-like output
    lines = [path]
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
    return _bash_success("\n".join(lines), warnings=result.get("warnings", []))


def _try_route_find(match: re.Match, args_str: str) -> dict[str, Any] | None:
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
        path=path,
        name_pattern=name_pattern,
        type=find_type,
        max_depth=max_depth,
        max_results=MAX_FIND_RESULTS,
    )
    content = _format_structured_as_shell("find", result)
    return _bash_success(content, warnings=result.get("warnings", []))


def _try_route_grep(match: re.Match, args_str: str) -> dict[str, Any] | None:
    """Route: grep [-r] [-i] [-n] [-C N] [-A N] [-B N] <pattern> [path]."""
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
        elif p.startswith("-"):
            return None
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
        path=path,
        glob=glob_pattern,
        case_sensitive=case_sensitive,
        context_before=context_before,
        context_after=context_after,
        max_results=MAX_GREP_RESULTS,
    )
    content = _format_structured_as_shell("grep", result)
    return _bash_success(content, warnings=result.get("warnings", []))


def _try_route_sed_read(match: re.Match, args_str: str) -> dict[str, Any] | None:
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
    result = read(path=file_path, start_line=start, end_line=end, max_bytes=MAX_READ_BYTES)
    content = _format_structured_as_shell("read", result)
    return _bash_success(content, warnings=result.get("warnings", []))


def _try_route_wc(match: re.Match, args_str: str) -> dict[str, Any] | None:
    """Route: wc [-l] <file> → read metadata."""
    parts = _safe_split(args_str)
    files = [p for p in parts if not p.startswith("-")]
    if len(files) != 1:
        return None
    result = read(path=files[0], max_bytes=MAX_READ_BYTES)
    inner = result.get("result", {})
    total_lines = inner.get("total_lines", 0)
    size_bytes = inner.get("size_bytes", 0)
    content_text = inner.get("content", "")
    word_count = len(content_text.split()) if content_text else 0
    flags = [p for p in parts if p.startswith("-")]
    if "-l" in flags:
        output = f"{total_lines} {files[0]}"
    else:
        output = f"  {total_lines}  {word_count}  {size_bytes} {files[0]}"
    return _bash_success(output)


def _try_route_mkdir(match: re.Match, args_str: str) -> dict[str, Any] | None:
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
    result = mkdir(path=dirs[0], parents=parents)
    content = _format_structured_as_shell("mkdir", result)
    return _bash_success(content, warnings=result.get("warnings", []))


def _try_route_touch(match: re.Match, args_str: str) -> dict[str, Any] | None:
    """Route: touch <file> → create empty file if it doesn't exist."""
    parts = _safe_split(args_str)
    files = [p for p in parts if not p.startswith("-")]
    if len(files) != 1:
        return None
    path = files[0]
    # Check if file exists via read; if not, create it
    try:
        read(path=path, max_bytes=1)
        return _bash_success("")  # file exists, touch is no-op
    except FileNotFoundError:
        result = write(path=path, content="")
        return _bash_success("", warnings=result.get("warnings", []))


def _try_route_mv(match: re.Match, args_str: str) -> dict[str, Any] | None:
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
    result = move(src=paths[0], dst=paths[1], overwrite=overwrite)
    content = _format_structured_as_shell("move", result)
    return _bash_success(content, warnings=result.get("warnings", []))


def _try_route_cp(match: re.Match, args_str: str) -> dict[str, Any] | None:
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
        source = read(path=paths[0], max_bytes=MAX_READ_BYTES)
        inner = source.get("result", {})
        if inner.get("kind") != "text":
            return None  # binary/image copy → real bash
        content = inner.get("content", "")
        result = write(path=paths[1], content=content)
        return _bash_success("", warnings=result.get("warnings", []))
    except Exception:
        return None


def _try_route_rm(match: re.Match, args_str: str) -> dict[str, Any] | None:
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
    result = delete(path=paths[0], recursive=recursive)
    content = _format_structured_as_shell("delete", result)
    return _bash_success(content, warnings=result.get("warnings", []))


def _try_route_pwd(match: re.Match, args_str: str) -> dict[str, Any] | None:
    """Route: pwd → return task root."""
    return _bash_success("/workspace/task")


def _try_route_file(match: re.Match, args_str: str) -> dict[str, Any] | None:
    """Route: file <path> → read metadata."""
    parts = _safe_split(args_str)
    files = [p for p in parts if not p.startswith("-")]
    if len(files) != 1:
        return None
    result = read(path=files[0], max_bytes=1)
    inner = result.get("result", {})
    kind = inner.get("kind", "unknown")
    mime = inner.get("mime", "application/octet-stream")
    size = inner.get("size_bytes", 0)
    return _bash_success(f"{files[0]}: {mime} ({kind}, {size} bytes)")


def _try_route_stat(match: re.Match, args_str: str) -> dict[str, Any] | None:
    """Route: stat <path> → file metadata."""
    parts = _safe_split(args_str)
    files = [p for p in parts if not p.startswith("-")]
    if len(files) != 1:
        return None
    result = read(path=files[0], max_bytes=1)
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
    return _bash_success("\n".join(lines))


def _safe_split(s: str) -> list[str]:
    """Split a string into shell tokens, falling back to plain split."""
    try:
        return shlex.split(s)
    except ValueError:
        return s.split()


def _bash_success(
    stdout: str,
    stderr: str = "",
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Build a bash-shaped success envelope from routed output."""
    return success_response(
        "bash",
        {
            "exit_code": 0,
            "stdout": stdout,
            "stderr": stderr,
            "elapsed_ms": 0,
            "cwd": ".",
            "routed": True,
        },
        warnings=warnings,
    )


def _bash_error(
    message: str,
    stderr: str = "",
    exit_code: int = 1,
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
            "cwd": ".",
            "routed": True,
        },
    )


# Ordered list of (command name, router-function).
# Only simple single-command patterns are matched; pipes, chains, and
# subshells are intentionally NOT intercepted and go to real bash.
_SIMPLE_COMMAND_RE = re.compile(
    r"^\s*(?:cd\s+\S+\s*[;&]\s*)?(?P<cmd>[a-z]+)\s*(?P<args>.*?)\s*$",
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

# Commands that involve pipes, semicolons, &&, ||, backticks, or $() are
# considered compound and should NOT be intercepted — they go to real bash.
_COMPOUND_PATTERN = re.compile(r"[|;`]|\$\(|&&|\|\|")


def _try_supervise(command: str) -> dict[str, Any] | None:
    """Try to route a shell command to an internal structured tool.

    Returns a bash-shaped response dict if the command was handled,
    or None if it should go to real bash.
    """
    if _COMPOUND_PATTERN.search(command):
        return None

    m = _SIMPLE_COMMAND_RE.match(command)
    if not m:
        return None

    cmd = m.group("cmd")
    args_str = m.group("args")

    router = _ROUTE_MAP.get(cmd)
    if router is None:
        return None

    try:
        return router(m, args_str)
    except FileNotFoundError as exc:
        return _bash_error(str(exc), exit_code=1)
    except NotADirectoryError as exc:
        return _bash_error(str(exc), exit_code=1)
    except Exception as exc:
        logger.debug("Supervisor routing failed for '%s': %s", cmd, exc)
        return None


# ── Tool handlers ────────────────────────────────────────────────────

def _handle_bash(
    arguments: dict[str, Any],
    _context: dict[str, Any] | None = None,
    *,
    progress_callback: Callable[[float, str], None] | None = None,
) -> dict[str, Any]:
    command = str(arguments.get("command", ""))

    # Try supervisor routing first.
    routed = _try_supervise(command)
    if routed is not None:
        return routed

    # Real bash execution.
    execution = exec_bash(
        command=command,
        cwd=str(arguments.get("cwd", ".")),
        timeout_s=int(arguments.get("timeout_s", DEFAULT_TIMEOUT)),
        stdin=arguments.get("stdin"),
        on_progress=progress_callback,
    )
    result = {
        "command": command,
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
