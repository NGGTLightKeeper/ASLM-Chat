from __future__ import annotations

import base64
import difflib
import fnmatch
import mimetypes
import os
import posixpath
import re
import shutil
from pathlib import Path
from typing import Any

from sandbox.config import (
    ALLOWED_IMPORT_ROOTS,
    CONTAINER_WORKSPACE,
    DEFAULT_TASK_DIR,
    HOST_WORKSPACE,
    IGNORED_DIR_NAMES,
    MAX_FIND_RESULTS,
    MAX_GREP_RESULTS,
    MAX_IMAGE_PREVIEW_BYTES,
    MAX_LS_ENTRIES,
    MAX_READ_BYTES,
)
from sandbox.responses import SandboxToolError

CONTEXT_LINES = 3
TEXT_SAMPLE_BYTES = 8192
IMAGE_MIME_PREFIX = "image/"
TEXT_MIME_PREFIX = "text/"
LEGACY_MODEL_ROOT_ALIASES = ("task",)


def model_root_aliases() -> tuple[str, ...]:
    """Return accepted model-facing workspace root aliases."""

    aliases = [DEFAULT_TASK_DIR, *LEGACY_MODEL_ROOT_ALIASES]
    seen: set[str] = set()
    result: list[str] = []
    for alias in aliases:
        cleaned = alias.strip().strip("/")
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return tuple(result)


def smart_decode(bytes_data: bytes) -> tuple[str, str | None]:
    """Decode bytes with a small fallback chain."""

    if not bytes_data:
        return "", "utf-8"

    for encoding in ("utf-8", "cp866", "cp1251", "latin1"):
        try:
            return bytes_data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue

    return bytes_data.decode("utf-8", errors="replace"), "utf-8"


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


def workspace_root() -> Path:
    """Return the resolved host workspace root."""

    return Path(HOST_WORKSPACE).resolve()


def task_root() -> Path:
    """Return the sandbox workspace root exposed to the model."""

    return (workspace_root() / DEFAULT_TASK_DIR).resolve()


def normalize_relative_path(path: str) -> str:
    """Normalize a workspace-relative path to POSIX form."""

    normalized = str(path or ".").replace("\\", "/").strip()
    if not normalized:
        normalized = "."
    if normalized == ".":
        return "."
    return normalized.lstrip("/")


def normalize_model_relative_path(path: str) -> str:
    """Normalize model-facing paths and tolerate workspace-root aliases."""

    normalized = normalize_relative_path(path)
    for alias in model_root_aliases():
        if normalized == alias:
            return "."

        prefix = f"{alias}/"
        if normalized.startswith(prefix):
            return normalized[len(prefix) :] or "."

        container_task_prefix = f"{CONTAINER_WORKSPACE.strip('/')}/{alias}"
        if normalized == container_task_prefix:
            return "."

        container_task_prefix_with_slash = f"{container_task_prefix}/"
        if normalized.startswith(container_task_prefix_with_slash):
            return normalized[len(container_task_prefix_with_slash) :] or "."

    return normalized


def validate_model_path(rel_path: str, kind: str = "path") -> None:
    """Reject absolute model paths while tolerating workspace-root aliases."""

    raw = str(rel_path or ".").replace("\\", "/").strip()
    if not raw or raw == ".":
        return

    if "\x00" in raw:
        raise ValueError(f"{kind} must not contain null bytes.")

    drive, _tail = os.path.splitdrive(raw)
    if raw.startswith("/"):
        for alias in model_root_aliases():
            container_task_root = f"{CONTAINER_WORKSPACE.rstrip('/')}/{alias}"
            if raw == container_task_root or raw.startswith(f"{container_task_root}/"):
                return

    if drive or raw.startswith("/"):
        raise ValueError(
            f"{kind} must be relative to the model workspace root. "
            f"Use '.' or a relative path like 'script.py'. "
            f"Optional prefixes like '{DEFAULT_TASK_DIR}/' are tolerated, never '{raw}'."
        )


def resolve_model_path(path: str, cwd: str = ".") -> str:
    """Resolve a model-facing path relative to the provided cwd."""

    raw = str(path or ".").replace("\\", "/").strip()
    normalized_cwd = normalize_model_relative_path(cwd)
    if not raw or raw == ".":
        return normalized_cwd

    if raw.startswith("/"):
        return raw

    for alias in model_root_aliases():
        if raw == alias or raw.startswith(f"{alias}/"):
            return raw
        container_prefix = f"{CONTAINER_WORKSPACE.rstrip('/')}/{alias}"
        if raw == container_prefix or raw.startswith(f"{container_prefix}/"):
            return raw

    if normalized_cwd in ("", "."):
        return posixpath.normpath(raw)

    return posixpath.normpath(f"{normalized_cwd}/{raw}")


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


def get_secure_task_path(rel_path: str, kind: str = "path") -> Path:
    """Resolve a path confined to the sandbox workspace root."""

    validate_model_path(rel_path, kind=kind)
    normalized = normalize_model_relative_path(rel_path)

    if normalized == ".":
        return task_root()

    full_path = (task_root() / normalized).resolve()
    if not full_path.is_relative_to(task_root()):
        raise ValueError(f"Access denied: {rel_path} is outside sandbox workspace.")

    return full_path


def is_within(path: Path, root: Path) -> bool:
    """Return True when path is inside root."""

    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _reject_symlink_escape(path: Path, original: str) -> None:
    """Raise if path is a symlink whose target escapes the task root."""

    if not path.is_symlink():
        return

    resolved = path.resolve()
    if not resolved.is_relative_to(task_root()):
        raise ValueError(
            f"Access denied: {original!r} is a symlink pointing outside the sandbox workspace."
        )


def is_allowed_host_import(source: Path) -> bool:
    """Return True when a host path is allowed for import."""

    resolved = source.resolve()
    if is_within(resolved, task_root()):
        return True

    for root in ALLOWED_IMPORT_ROOTS:
        if is_within(resolved, Path(root)):
            return True

    return False


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


def build_match_preview(text: str, start_index: int, needle_len: int) -> dict[str, Any]:
    """Build preview metadata for one text match."""

    start_line = text[:start_index].count("\n") + 1
    end_line = start_line + text[start_index : start_index + needle_len].count("\n")
    return {
        "line_start": start_line,
        "line_end": end_line,
        "context": render_numbered_context(text, start_line, end_line),
    }


def _guess_mime(path: Path) -> str:
    mime_type, _ = mimetypes.guess_type(str(path))
    return mime_type or "application/octet-stream"


def _is_probably_binary(data: bytes, mime_type: str) -> bool:
    if mime_type.startswith(TEXT_MIME_PREFIX):
        return False
    if mime_type.startswith(IMAGE_MIME_PREFIX):
        return True
    if not data:
        return False
    if b"\x00" in data[:TEXT_SAMPLE_BYTES]:
        return True

    sample = data[:TEXT_SAMPLE_BYTES]
    try:
        sample.decode("utf-8")
        return False
    except UnicodeDecodeError:
        pass

    text_like = 0
    for byte in sample:
        if byte in (9, 10, 13) or 32 <= byte <= 126 or byte >= 128:
            text_like += 1

    return (text_like / len(sample)) < 0.85


def _should_skip_entry(name: str, include_hidden: bool) -> bool:
    if name in IGNORED_DIR_NAMES:
        return True
    if not include_hidden and name.startswith("."):
        return True
    return False


def _line_slice(
    text: str,
    start_line: int | None = None,
    end_line: int | None = None,
) -> tuple[str, int, int, int]:
    normalized = normalize_newlines(text)
    lines = normalized.split("\n")
    total_lines = len(lines)
    start = max(1, int(start_line or 1))
    end = min(total_lines, int(end_line or total_lines))
    if end < start:
        end = start
    return "\n".join(lines[start - 1 : end]), start, end, total_lines


def _truncate_text(text: str, max_bytes: int) -> tuple[str, bool]:
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text, False

    truncated = encoded[:max_bytes].decode("utf-8", errors="ignore")
    return truncated, True


def ls(
    path: str = ".",
    depth: int = 1,
    max_entries: int = MAX_LS_ENTRIES,
    include_hidden: bool = False,
) -> dict[str, Any]:
    """List files and directories inside the task workspace."""

    target = get_secure_task_path(path)
    if not target.exists():
        raise FileNotFoundError(f"Path not found: {normalize_model_relative_path(path)}")
    if not target.is_dir():
        raise NotADirectoryError(f"Not a directory: {normalize_model_relative_path(path)}")

    depth = max(0, int(depth))
    max_entries = max(1, int(max_entries))
    entries: list[dict[str, Any]] = []
    truncated = False
    warnings: list[str] = []

    base_depth = len(target.relative_to(task_root()).parts)

    def _walk(current: Path) -> None:
        nonlocal truncated
        if truncated:
            return

        children = sorted(
            current.iterdir(),
            key=lambda item: (not item.is_dir(), item.name.lower()),
        )
        for child in children:
            if _should_skip_entry(child.name, include_hidden):
                continue

            child_depth = len(child.relative_to(task_root()).parts) - base_depth
            if child_depth > depth:
                continue

            entry: dict[str, Any] = {
                "path": child.relative_to(task_root()).as_posix(),
                "name": child.name,
                "type": "directory" if child.is_dir() else "file",
                "depth": child_depth,
            }
            if child.is_file():
                try:
                    entry["size_bytes"] = child.stat().st_size
                    entry["mime"] = _guess_mime(child)
                except OSError:
                    pass

            entries.append(entry)
            if len(entries) >= max_entries:
                truncated = True
                warnings.append(f"Entry limit reached at {max_entries} items.")
                return

            if child.is_dir() and child_depth < depth:
                _walk(child)

    _walk(target)
    return {
        "result": {
            "path": normalize_model_relative_path(path),
            "depth": depth,
            "entries": entries,
        },
        "warnings": warnings,
        "truncated": truncated,
    }


def read(
    path: str,
    start_line: int | None = None,
    end_line: int | None = None,
    max_bytes: int = MAX_READ_BYTES,
) -> dict[str, Any]:
    """Read a file from the task workspace."""

    target = get_secure_task_path(path)
    _reject_symlink_escape(target, path)
    if not target.is_file():
        raise FileNotFoundError(f"File not found: {normalize_model_relative_path(path)}")

    data = target.read_bytes()
    mime_type = _guess_mime(target)
    normalized_path = normalize_model_relative_path(path)
    warnings: list[str] = []
    truncated = False

    if mime_type.startswith(IMAGE_MIME_PREFIX):
        preview_data = None
        if len(data) <= MAX_IMAGE_PREVIEW_BYTES:
            preview_data = {
                "type": "inline_base64",
                "mime_type": mime_type,
                "data_base64": base64.b64encode(data).decode("utf-8"),
            }
        else:
            warnings.append(
                f"Image preview omitted because the file is larger than {MAX_IMAGE_PREVIEW_BYTES} bytes."
            )

        return {
            "result": {
                "path": normalized_path,
                "kind": "image",
                "mime": mime_type,
                "size_bytes": len(data),
                "encoding": None,
                "preview": preview_data,
            },
            "warnings": warnings,
            "truncated": False,
        }

    if _is_probably_binary(data, mime_type):
        return {
            "result": {
                "path": normalized_path,
                "kind": "binary",
                "mime": mime_type,
                "size_bytes": len(data),
                "encoding": None,
            },
            "warnings": warnings,
            "truncated": False,
        }

    text, encoding = smart_decode(data)
    if start_line is not None or end_line is not None:
        content, line_start, line_end, total_lines = _line_slice(text, start_line, end_line)
    else:
        normalized_text = normalize_newlines(text)
        total_lines = len(normalized_text.split("\n"))
        content = normalized_text
        line_start = 1
        line_end = total_lines

    content, truncated = _truncate_text(content, max(1, int(max_bytes)))
    if truncated:
        warnings.append(f"Read output truncated to {max_bytes} bytes.")

    return {
        "result": {
            "path": normalized_path,
            "kind": "text",
            "mime": mime_type,
            "encoding": encoding,
            "content": content,
            "start_line": line_start,
            "end_line": line_end,
            "total_lines": total_lines,
            "size_bytes": len(data),
        },
        "warnings": warnings,
        "truncated": truncated,
    }


def describe(path: str) -> dict[str, Any]:
    """Return file metadata without loading the full file into memory."""

    target = get_secure_task_path(path)
    _reject_symlink_escape(target, path)
    if not target.is_file():
        raise FileNotFoundError(f"File not found: {normalize_model_relative_path(path)}")

    size_bytes = target.stat().st_size
    mime_type = _guess_mime(target)
    normalized_path = normalize_model_relative_path(path)

    with target.open("rb") as handle:
        sample = handle.read(TEXT_SAMPLE_BYTES)

    if mime_type.startswith(IMAGE_MIME_PREFIX):
        kind = "image"
        encoding = None
    elif _is_probably_binary(sample, mime_type):
        kind = "binary"
        encoding = None
    else:
        _text, encoding = smart_decode(sample)
        kind = "text"

    return {
        "result": {
            "path": normalized_path,
            "kind": kind,
            "mime": mime_type,
            "size_bytes": size_bytes,
            "encoding": encoding,
        },
        "warnings": [],
        "truncated": False,
    }


def write(path: str, content: str) -> dict[str, Any]:
    """Write a UTF-8 text file inside the task workspace."""

    target = get_secure_task_path(path)
    _reject_symlink_escape(target, path)
    existed = target.exists()
    if target.exists() and target.is_dir():
        raise IsADirectoryError(f"Cannot overwrite directory: {normalize_model_relative_path(path)}")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="")

    return {
        "result": {
            "path": normalize_model_relative_path(path),
            "bytes_written": target.stat().st_size,
            "created": not existed,
            "overwrote": existed,
        },
        "warnings": [],
        "truncated": False,
    }


def edit(path: str, old_str: str, new_str: str, replace_all: bool = False) -> dict[str, Any]:
    """Replace exact text matches inside a text file."""

    target = get_secure_task_path(path)
    _reject_symlink_escape(target, path)
    if not target.is_file():
        raise FileNotFoundError(f"File not found: {normalize_model_relative_path(path)}")
    if old_str == "":
        raise ValueError("old_str must not be empty.")

    original_bytes = target.read_bytes()
    mime_type = _guess_mime(target)
    if _is_probably_binary(original_bytes, mime_type):
        raise SandboxToolError("binary_not_supported", "edit only supports text files.")

    original_text, _encoding = smart_decode(original_bytes)
    newline_style = detect_newline_style(original_text)
    normalized_content = normalize_newlines(original_text)
    normalized_old = normalize_newlines(old_str)
    normalized_new = normalize_newlines(new_str)
    match_count = normalized_content.count(normalized_old)

    if match_count == 0:
        raise SandboxToolError(
            "match_not_found",
            "old_str not found in file.",
            result={
                "path": normalize_model_relative_path(path),
                "match_count": 0,
            },
        )

    if match_count > 1 and not replace_all:
        previews = []
        start = 0
        while len(previews) < 3:
            match_index = normalized_content.find(normalized_old, start)
            if match_index < 0:
                break
            previews.append(build_match_preview(normalized_content, match_index, len(normalized_old)))
            start = match_index + len(normalized_old)

        raise SandboxToolError(
            "ambiguous_match",
            f"old_str found {match_count} times. Set replace_all=true or add more context.",
            result={
                "path": normalize_model_relative_path(path),
                "match_count": match_count,
                "matches": previews,
            },
        )

    replaced_count = match_count if replace_all else 1
    updated_normalized = normalized_content.replace(normalized_old, normalized_new, replaced_count)
    match_index = normalized_content.find(normalized_old)
    before_preview = build_match_preview(normalized_content, match_index, len(normalized_old))
    after_preview = build_match_preview(updated_normalized, match_index, len(normalized_new))

    final_text = updated_normalized if newline_style == "\n" else updated_normalized.replace("\n", newline_style)
    target.write_text(final_text, encoding="utf-8", newline="")

    diff_text = "\n".join(
        difflib.unified_diff(
            normalized_content.splitlines(),
            updated_normalized.splitlines(),
            fromfile=f"{normalize_model_relative_path(path)} (before)",
            tofile=f"{normalize_model_relative_path(path)} (after)",
            lineterm="",
            n=CONTEXT_LINES,
        )
    )

    return {
        "result": {
            "path": normalize_model_relative_path(path),
            "match_count": match_count,
            "replaced_count": replaced_count,
            "replace_all": bool(replace_all),
            "before_preview": before_preview,
            "after_preview": after_preview,
            "diff": diff_text,
        },
        "warnings": [],
        "truncated": False,
    }


def find(
    path: str = ".",
    name_pattern: str | None = None,
    type_filter: str | None = None,
    max_depth: int = 8,
    max_results: int = MAX_FIND_RESULTS,
) -> dict[str, Any]:
    """Find files and directories inside the task workspace."""

    target = get_secure_task_path(path)
    if not target.exists():
        raise FileNotFoundError(f"Path not found: {normalize_model_relative_path(path)}")
    if not target.is_dir():
        raise NotADirectoryError(f"Not a directory: {normalize_model_relative_path(path)}")

    normalized_type = str(type_filter or "any").strip().lower()
    if normalized_type not in {"any", "file", "directory"}:
        raise ValueError("type must be one of: any, file, directory.")

    name_pattern = str(name_pattern or "*")
    max_depth = max(0, int(max_depth))
    max_results = max(1, int(max_results))
    matches: list[dict[str, Any]] = []
    warnings: list[str] = []
    truncated = False

    base_depth = len(target.relative_to(task_root()).parts)

    for root, dirnames, filenames in os.walk(target):
        root_path = Path(root)
        current_depth = len(root_path.relative_to(task_root()).parts) - base_depth
        dirnames[:] = [
            name
            for name in sorted(dirnames)
            if not _should_skip_entry(name, include_hidden=False)
        ]

        if current_depth >= max_depth:
            dirnames[:] = []

        if normalized_type in {"any", "directory"}:
            for dirname in dirnames:
                if not fnmatch.fnmatch(dirname, name_pattern):
                    continue
                child = root_path / dirname
                matches.append(
                    {
                        "path": child.relative_to(task_root()).as_posix(),
                        "name": dirname,
                        "type": "directory",
                        "depth": len(child.relative_to(task_root()).parts) - base_depth,
                    }
                )
                if len(matches) >= max_results:
                    truncated = True
                    warnings.append(f"Result limit reached at {max_results} items.")
                    return {
                        "result": {
                            "path": normalize_model_relative_path(path),
                            "matches": matches,
                        },
                        "warnings": warnings,
                        "truncated": True,
                    }

        if normalized_type in {"any", "file"}:
            for filename in sorted(filenames):
                if _should_skip_entry(filename, include_hidden=False):
                    continue
                if not fnmatch.fnmatch(filename, name_pattern):
                    continue
                child = root_path / filename
                matches.append(
                    {
                        "path": child.relative_to(task_root()).as_posix(),
                        "name": filename,
                        "type": "file",
                        "depth": len(child.relative_to(task_root()).parts) - base_depth,
                    }
                )
                if len(matches) >= max_results:
                    truncated = True
                    warnings.append(f"Result limit reached at {max_results} items.")
                    return {
                        "result": {
                            "path": normalize_model_relative_path(path),
                            "matches": matches,
                        },
                        "warnings": warnings,
                        "truncated": True,
                    }

    return {
        "result": {
            "path": normalize_model_relative_path(path),
            "matches": matches,
        },
        "warnings": warnings,
        "truncated": truncated,
    }


def grep(
    pattern: str,
    path: str = ".",
    glob: str | None = None,
    case_sensitive: bool = False,
    context_before: int = 0,
    context_after: int = 0,
    max_results: int = MAX_GREP_RESULTS,
) -> dict[str, Any]:
    """Search text files inside the task workspace."""

    target = get_secure_task_path(path)
    if not target.exists():
        raise FileNotFoundError(f"Path not found: {normalize_model_relative_path(path)}")

    regex_flags = re.MULTILINE if case_sensitive else (re.MULTILINE | re.IGNORECASE)
    try:
        regex = re.compile(pattern, regex_flags)
    except re.error as exc:
        raise ValueError(f"Invalid regular expression: {exc}") from exc

    max_results = max(1, int(max_results))
    context_before = max(0, int(context_before))
    context_after = max(0, int(context_after))
    matches: list[dict[str, Any]] = []
    warnings: list[str] = []
    truncated = False

    if target.is_file():
        candidates = [target]
    else:
        candidates = []
        for root, dirnames, filenames in os.walk(target):
            dirnames[:] = [
                name
                for name in sorted(dirnames)
                if not _should_skip_entry(name, include_hidden=False)
            ]
            for filename in sorted(filenames):
                if _should_skip_entry(filename, include_hidden=False):
                    continue
                file_path = Path(root) / filename
                rel_path = file_path.relative_to(task_root()).as_posix()
                if glob and not fnmatch.fnmatch(rel_path, glob):
                    continue
                candidates.append(file_path)

    for candidate in candidates:
        data = candidate.read_bytes()
        mime_type = _guess_mime(candidate)
        if _is_probably_binary(data, mime_type):
            continue

        text, _encoding = smart_decode(data)
        lines = normalize_newlines(text).split("\n")
        for index, line in enumerate(lines, start=1):
            if regex.search(line) is None:
                continue

            before_start = max(1, index - context_before)
            after_end = min(len(lines), index + context_after)
            matches.append(
                {
                    "path": candidate.relative_to(task_root()).as_posix(),
                    "line_number": index,
                    "line": line,
                    "before": lines[before_start - 1 : index - 1],
                    "after": lines[index:after_end],
                }
            )
            if len(matches) >= max_results:
                truncated = True
                warnings.append(f"Result limit reached at {max_results} items.")
                return {
                    "result": {
                        "path": normalize_model_relative_path(path),
                        "pattern": pattern,
                        "matches": matches,
                    },
                    "warnings": warnings,
                    "truncated": True,
                }

    return {
        "result": {
            "path": normalize_model_relative_path(path),
            "pattern": pattern,
            "matches": matches,
        },
        "warnings": warnings,
        "truncated": truncated,
    }


def mkdir(path: str, parents: bool = True) -> dict[str, Any]:
    """Create a directory inside the task workspace."""

    target = get_secure_task_path(path)
    existed = target.exists()
    if existed and not target.is_dir():
        raise SandboxToolError(
            "path_conflict",
            f"Path already exists and is not a directory: {normalize_model_relative_path(path)}",
        )

    target.mkdir(parents=parents, exist_ok=True)
    return {
        "result": {
            "path": normalize_model_relative_path(path),
            "created": not existed,
            "already_exists": existed,
        },
        "warnings": [],
        "truncated": False,
    }


def move(src: str, dst: str, overwrite: bool = False) -> dict[str, Any]:
    """Move or rename a file or directory inside the task workspace."""

    source = get_secure_task_path(src, kind="src")
    destination = get_secure_task_path(dst, kind="dst")
    if not source.exists():
        raise FileNotFoundError(f"Path not found: {normalize_model_relative_path(src)}")

    if destination.exists():
        if not overwrite:
            raise SandboxToolError(
                "destination_exists",
                f"Destination already exists: {normalize_model_relative_path(dst)}",
            )
        if destination.is_dir():
            shutil.rmtree(destination)
        else:
            destination.unlink()

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(destination))
    return {
        "result": {
            "src": normalize_model_relative_path(src),
            "dst": normalize_model_relative_path(dst),
            "overwrote": bool(overwrite),
        },
        "warnings": [],
        "truncated": False,
    }


def delete(path: str, recursive: bool = False) -> dict[str, Any]:
    """Delete a file or directory inside the task workspace."""

    target = get_secure_task_path(path)
    if not target.exists():
        raise FileNotFoundError(f"Path not found: {normalize_model_relative_path(path)}")

    if target.is_dir():
        if not recursive:
            raise SandboxToolError(
                "recursive_required",
                f"Refusing to delete directory without recursive=true: {normalize_model_relative_path(path)}",
            )
        shutil.rmtree(target)
        deleted_type = "directory"
    else:
        target.unlink()
        deleted_type = "file"

    return {
        "result": {
            "path": normalize_model_relative_path(path),
            "type": deleted_type,
        },
        "warnings": [],
        "truncated": False,
    }


def copy_into_workspace(host_path: str, dest_path: str | None = None) -> dict[str, Any]:
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

    destination_rel = dest_path or source.name
    destination = get_secure_task_path(destination_rel, kind="dest_path")
    destination.parent.mkdir(parents=True, exist_ok=True)

    if source.is_dir():
        if destination.exists():
            if destination.is_file():
                destination.unlink()
            else:
                shutil.rmtree(destination)
        shutil.copytree(source, destination)
        copied_type = "directory"
        size_bytes = sum(item.stat().st_size for item in destination.rglob("*") if item.is_file())
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


def clear_workspace() -> dict[str, Any]:
    """Clear the dedicated sandbox workspace without deleting its root."""

    root = task_root()
    cleared: list[str] = []

    for child in root.iterdir():
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)
        cleared.append(child.name)

    return {"ok": True, "cleared": cleared}
