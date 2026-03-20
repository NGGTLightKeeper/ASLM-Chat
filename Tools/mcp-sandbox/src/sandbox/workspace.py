# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import os
import shutil
from pathlib import Path

from sandbox.config import ALLOWED_IMPORT_ROOTS, DEFAULT_TASK_DIR, HOST_WORKSPACE

CONTEXT_LINES = 3


# Text decoding helpers.

def smart_decode(bytes_data: bytes) -> str:
    """Decode bytes with a small fallback chain."""

    if not bytes_data:
        return ""

    for encoding in ("utf-8", "cp866", "cp1251", "latin1"):
        try:
            return bytes_data.decode(encoding)
        except UnicodeDecodeError:
            continue

    return bytes_data.decode("utf-8", errors="replace")


def read_text_with_fallback(path: Path) -> str:
    """Read a text file with fallback decoding."""

    data = path.read_bytes()
    return smart_decode(data)


def detect_newline_style(text: str) -> str:
    """Detect the dominant newline style in text."""

    crlf = text.count("\r\n")
    normalized = text.replace("\r\n", "")
    cr = normalized.count("\r")
    lf = normalized.count("\n")

    if crlf >= lf and crlf >= cr and crlf > 0:
        return "\r\n"

    if cr > lf and cr > 0:
        return "\r"

    return "\n"


def normalize_newlines(text: str) -> str:
    """Normalize all newline variants to LF."""

    return text.replace("\r\n", "\n").replace("\r", "\n")


# Workspace roots.

def workspace_root() -> Path:
    """Return the resolved host workspace root."""

    return Path(HOST_WORKSPACE).resolve()


def task_root() -> Path:
    """Return the task directory exposed to the model."""

    return (workspace_root() / DEFAULT_TASK_DIR).resolve()


# Path normalization and validation.

def normalize_relative_path(path: str) -> str:
    """Normalize a workspace-relative path to POSIX form."""

    normalized = str(path or ".").replace("\\", "/").strip()
    if not normalized:
        normalized = "."

    if normalized == ".":
        return "."

    return normalized.lstrip("/")


def validate_model_path(rel_path: str, kind: str = "path") -> None:
    """Reject absolute and task-prefixed model paths."""

    raw = str(rel_path or ".").replace("\\", "/").strip()
    if not raw or raw == ".":
        return

    if "\x00" in raw:
        raise ValueError(f"{kind} must not contain null bytes.")

    drive, _tail = os.path.splitdrive(raw)
    if drive or raw.startswith("/"):
        raise ValueError(
            f"{kind} must be relative to the model workspace root "
            f"'{DEFAULT_TASK_DIR}/'. Use '.' or a relative path like "
            f"'script.py', never '{raw}'."
        )

    normalized = normalize_relative_path(raw)
    if normalized == DEFAULT_TASK_DIR or normalized.startswith(f"{DEFAULT_TASK_DIR}/"):
        suggestion = (
            "."
            if normalized == DEFAULT_TASK_DIR
            else normalized[len(DEFAULT_TASK_DIR) + 1 :]
        )
        raise ValueError(
            f"{kind} is already inside '{DEFAULT_TASK_DIR}/'. "
            f"Do not prefix paths with '{DEFAULT_TASK_DIR}/'. "
            f"Use '{suggestion}' instead."
        )


def to_workspace_posix(path: Path) -> str:
    """Convert an absolute workspace path to a POSIX relative path."""

    rel_path = path.resolve().relative_to(workspace_root())
    return rel_path.as_posix() or "."


def get_secure_path(rel_path: str) -> Path:
    """Resolve a path inside the workspace root."""

    normalized = normalize_relative_path(rel_path)
    full_path = (workspace_root() / normalized).resolve()

    if not full_path.is_relative_to(workspace_root()):
        raise ValueError(f"Access denied: {rel_path} is outside workspace.")

    return full_path


def is_workspace_root_path(rel_path: str) -> bool:
    """Return True for top-level workspace-root items."""

    normalized = normalize_relative_path(rel_path)
    if normalized in {"", "."}:
        return False

    return "/" not in normalized


def is_outside_task_dir(rel_path: str) -> bool:
    """Return True when the path does not live under task/."""

    normalized = normalize_relative_path(rel_path)
    if normalized in {"", "."}:
        return True

    parts = normalized.split("/")
    return parts[0] != DEFAULT_TASK_DIR


def task_write_error(rel_path: str) -> ValueError:
    """Build the standard write-outside-task error."""

    normalized = normalize_relative_path(rel_path)
    name = Path(normalized).name
    suggested = f"{DEFAULT_TASK_DIR}/{name}"
    return ValueError(
        f"Refusing to write outside task directory: '{normalized}'. "
        f"All files must go inside '{DEFAULT_TASK_DIR}/'. "
        f"Use '{suggested}' instead."
    )


def root_write_error(rel_path: str) -> ValueError:
    """Build the standard workspace-root write error."""

    normalized = normalize_relative_path(rel_path)
    suggested = f"{DEFAULT_TASK_DIR}/{Path(normalized).name}"
    return ValueError(
        f"Refusing to write into the workspace root: {normalized}. "
        f"Use a task subfolder such as '{suggested}' instead."
    )


def get_secure_task_path(rel_path: str, kind: str = "path") -> Path:
    """Resolve a path confined to the task directory."""

    validate_model_path(rel_path, kind=kind)
    normalized = normalize_relative_path(rel_path)

    if normalized == ".":
        return task_root()

    full_path = (task_root() / normalized).resolve()
    if not full_path.is_relative_to(task_root()):
        raise ValueError(f"Access denied: {rel_path} is outside task directory.")

    return full_path


def is_within(path: Path, root: Path) -> bool:
    """Return True when path is inside root."""

    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def is_allowed_host_import(source: Path) -> bool:
    """Return True when a host path is allowed for import."""

    resolved = source.resolve()
    if is_within(resolved, task_root()):
        return True

    for root in ALLOWED_IMPORT_ROOTS:
        if is_within(resolved, Path(root)):
            return True

    return False


# Match preview helpers.

def render_numbered_context(text: str, start_line: int, end_line: int) -> str:
    """Render a numbered text excerpt with context lines."""

    lines = text.split("\n")
    total_lines = len(lines)
    context_start = max(1, start_line - CONTEXT_LINES)
    context_end = min(total_lines, end_line + CONTEXT_LINES)

    return "\n".join(
        f"{line_no:>4} | {lines[line_no - 1]}"
        for line_no in range(context_start, context_end + 1)
    )


def build_match_preview(text: str, start_index: int, needle_len: int) -> dict:
    """Build preview metadata for one text match."""

    start_line = text[:start_index].count("\n") + 1
    end_line = start_line + text[start_index : start_index + needle_len].count("\n")
    return {
        "line_start": start_line,
        "line_end": end_line,
        "context": render_numbered_context(text, start_line, end_line),
    }


# Directory and file operations.

def list_directory(path: str = ".", recursive: bool = False, max_depth: int = 3) -> dict:
    """List files and directories inside the task workspace."""

    target = get_secure_task_path(path)
    if not target.exists():
        raise FileNotFoundError(f"Path not found: {normalize_relative_path(path)}")

    if not target.is_dir():
        raise NotADirectoryError(f"Not a directory: {normalize_relative_path(path)}")

    entries: list[dict] = []
    base_depth = len(target.relative_to(task_root()).parts)

    if recursive:
        for child in sorted(target.rglob("*")):
            depth = len(child.relative_to(task_root()).parts) - base_depth
            if depth > max_depth:
                continue

            entries.append(
                {
                    "path": child.relative_to(task_root()).as_posix(),
                    "name": child.name,
                    "type": "directory" if child.is_dir() else "file",
                    "depth": depth,
                }
            )
    else:
        for child in sorted(
            target.iterdir(),
            key=lambda item: (not item.is_dir(), item.name.lower()),
        ):
            entries.append(
                {
                    "path": child.relative_to(task_root()).as_posix(),
                    "name": child.name,
                    "type": "directory" if child.is_dir() else "file",
                    "depth": 1,
                }
            )

    return {
        "ok": True,
        "path": normalize_relative_path(path),
        "recursive": recursive,
        "max_depth": max_depth,
        "entries": entries,
    }


def read_file(path: str, start_line: int | None = None, end_line: int | None = None) -> dict:
    """Read a text file from the task workspace."""

    target = get_secure_task_path(path)
    if not target.is_file():
        raise FileNotFoundError(f"File not found: {normalize_relative_path(path)}")

    content = read_text_with_fallback(target)
    normalized = normalize_newlines(content)
    lines = normalized.split("\n")
    total_lines = len(lines)

    if start_line is not None or end_line is not None:
        start = max(1, start_line or 1)
        end = min(total_lines, end_line or total_lines)
        content_out = "\n".join(
            f"{line_no:>4} | {lines[line_no - 1]}"
            for line_no in range(start, end + 1)
        )
    else:
        start = 1
        end = total_lines
        content_out = content

    return {
        "ok": True,
        "path": normalize_relative_path(path),
        "content": content_out,
        "line_start": start,
        "line_end": end,
        "total_lines": total_lines,
    }


def write_file(path: str, content: str) -> dict:
    """Write a UTF-8 text file inside the task workspace."""

    target = get_secure_task_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="")

    return {
        "ok": True,
        "path": normalize_relative_path(path),
        "bytes_written": target.stat().st_size,
    }


def str_replace(path: str, old_str: str, new_str: str) -> dict:
    """Replace one exact unique match in a text file."""

    target = get_secure_task_path(path)
    if not target.is_file():
        raise FileNotFoundError(f"File not found: {normalize_relative_path(path)}")

    if old_str == "":
        raise ValueError("old_str must not be empty.")

    original = read_text_with_fallback(target)
    if "\x00" in original:
        raise ValueError("str_replace only supports text files.")

    newline_style = detect_newline_style(original)
    normalized_content = normalize_newlines(original)
    normalized_old = normalize_newlines(old_str)
    normalized_new = normalize_newlines(new_str)
    match_count = normalized_content.count(normalized_old)

    if match_count == 0:
        return {
            "ok": False,
            "path": normalize_relative_path(path),
            "error": "old_str not found in file.",
            "match_count": 0,
        }

    if match_count > 1:
        previews = []
        start = 0

        while len(previews) < 3:
            match_index = normalized_content.find(normalized_old, start)
            if match_index < 0:
                break

            previews.append(
                build_match_preview(
                    normalized_content,
                    match_index,
                    len(normalized_old),
                )
            )
            start = match_index + len(normalized_old)

        return {
            "ok": False,
            "path": normalize_relative_path(path),
            "error": f"old_str found {match_count} times. Add more surrounding context.",
            "match_count": match_count,
            "matches": previews,
        }

    match_index = normalized_content.find(normalized_old)
    updated_normalized = normalized_content.replace(normalized_old, normalized_new, 1)
    changed_start_line = updated_normalized[:match_index].count("\n") + 1
    changed_end_line = changed_start_line + updated_normalized[
        match_index : match_index + len(normalized_new)
    ].count("\n")
    context = render_numbered_context(
        updated_normalized,
        changed_start_line,
        changed_end_line,
    )

    final_text = updated_normalized
    if newline_style != "\n":
        final_text = updated_normalized.replace("\n", newline_style)

    target.write_text(final_text, encoding="utf-8", newline="")

    return {
        "ok": True,
        "path": normalize_relative_path(path),
        "replaced_count": 1,
        "line_start": changed_start_line,
        "line_end": changed_end_line,
        "context": context,
    }


# Workspace import helpers.

def copy_into_workspace(host_path: str, dest_path: str | None = None) -> dict:
    """Copy a host file or directory into the task workspace."""

    source = Path(os.path.expanduser(host_path))
    if not source.is_absolute():
        source = (Path.cwd() / source).resolve()
    else:
        source = source.resolve()

    if not source.exists():
        raise FileNotFoundError(f"Host path not found: {source}")

    if not is_allowed_host_import(source):
        raise ValueError(
            "Import denied. Path must be inside the workspace or one of the "
            "allowed import roots."
        )

    if dest_path:
        destination = get_secure_task_path(dest_path, kind="dest_path")
    else:
        destination = get_secure_task_path(source.name, kind="dest_path")

    destination.parent.mkdir(parents=True, exist_ok=True)

    if source.is_dir():
        if destination.exists():
            if destination.is_file():
                destination.unlink()
            else:
                shutil.rmtree(destination)

        shutil.copytree(source, destination)
        copied_type = "directory"
        size_bytes = sum(
            item.stat().st_size
            for item in destination.rglob("*")
            if item.is_file()
        )
    else:
        if destination.exists() and destination.is_dir():
            shutil.rmtree(destination)

        shutil.copy2(source, destination)
        copied_type = "file"
        size_bytes = destination.stat().st_size

    return {
        "ok": True,
        "source": str(source),
        "path": destination.relative_to(task_root()).as_posix() or ".",
        "type": copied_type,
        "bytes_copied": size_bytes,
    }


# Workspace cleanup.

def clear_workspace() -> dict:
    """Clear the dedicated workspace without deleting its root."""

    root = workspace_root()
    cleared: list[str] = []

    for child in root.iterdir():
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)

        cleared.append(child.name)

    return {"ok": True, "cleared": cleared}
