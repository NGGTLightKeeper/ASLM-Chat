---
title: "workspace"
draft: false
---

## Module `workspace`

`Tools/mcp-sandbox/supervisor/sandbox/workspace.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools\mcp-sandbox\supervisor\sandbox`. See **Related** for package index and callers.

---

## Public functions

#### `def model_root_aliases() -> tuple[str, ...]`

**Purpose:** Return accepted model-facing workspace root aliases.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def smart_decode(bytes_data) -> tuple[str, str | None]`

**Purpose:** Decode bytes with a small fallback chain.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def detect_newline_style(text) -> str`

**Purpose:** Detect the dominant newline style in text.

**Steps:**

1. Return the computed result to the caller.

#### `def normalize_newlines(text) -> str`

**Purpose:** Normalize all newline variants to LF.

#### `def workspace_root() -> Path`

**Purpose:** Return the resolved host workspace root.

#### `def task_root() -> Path`

**Purpose:** Return the sandbox workspace root exposed to the model.

#### `def normalize_relative_path(path) -> str`

**Purpose:** Normalize a workspace-relative path to POSIX form.

**Steps:**

1. Return the computed result to the caller.

#### `def normalize_model_relative_path(path) -> str`

**Purpose:** Normalize model-facing paths and tolerate workspace-root aliases.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def validate_model_path(rel_path, kind) -> None`

**Purpose:** Reject unsafe paths; allow absolute Linux paths inside the container.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Iterate and transform or accumulate state.

#### `def resolve_model_path(path, cwd) -> str`

**Purpose:** Resolve a model-facing path relative to the provided cwd.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Iterate and transform or accumulate state.

#### `def to_workspace_posix(path) -> str`

**Purpose:** Convert an absolute workspace path to a POSIX relative path.

#### `def get_secure_path(rel_path) -> Path`

**Purpose:** Resolve a path inside the workspace root.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.

#### `def get_secure_task_path(rel_path, kind) -> Path`

**Purpose:** Resolve a path to a sandbox-safe location (container vs host rules).

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.

#### `def is_within(path, root) -> bool`

**Purpose:** Return True when path is inside root.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def is_allowed_host_import(source) -> bool`

**Purpose:** Return True when a host path is allowed for import.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def render_numbered_context(text, start_line, end_line) -> str`

**Purpose:** Render a numbered text excerpt with context lines.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def build_match_preview(text, start_index, needle_len) -> dict[str, Any]`

**Purpose:** Build preview metadata for one text match.

**Steps:**

1. Return the computed result to the caller.

#### `def ls(path, depth, max_entries, include_hidden) -> dict[str, Any]`

**Purpose:** List files and directories inside the task workspace.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

#### `def read(path, start_line, end_line, max_bytes) -> dict[str, Any]`

**Purpose:** Read a file from the task workspace.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.

#### `def describe(path) -> dict[str, Any]`

**Purpose:** Return file metadata without loading the full file into memory.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.

#### `def read_image(path, include_preview, max_preview_bytes) -> dict[str, Any]`

**Purpose:** Read image metadata and, when small enough, an inline preview.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.

#### `def write(path, content) -> dict[str, Any]`

**Purpose:** Write a UTF-8 text file inside the task workspace.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.

#### `def edit(path, old_str, new_str, replace_all) -> dict[str, Any]`

**Purpose:** Replace exact text matches inside a text file.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Iterate and transform or accumulate state.

#### `def edit_lines(path, range_str, content, anchor, context_lines) -> dict[str, Any]`

**Purpose:** Replace or insert text by 1-based line range inside a text file.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Iterate and transform or accumulate state.

#### `def find(path, name_pattern, type_filter, max_depth, max_results) -> dict[str, Any]`

**Purpose:** Find files and directories inside the task workspace.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Iterate and transform or accumulate state.

#### `def grep(pattern, path, glob, case_sensitive, context_before, context_after, max_results) -> dict[str, Any]`

**Purpose:** Search text files inside the task workspace.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

#### `def mkdir(path, parents) -> dict[str, Any]`

**Purpose:** Create a directory inside the task workspace.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.

#### `def move(src, dst, overwrite) -> dict[str, Any]`

**Purpose:** Move or rename a file or directory inside the task workspace.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.

#### `def delete(path, recursive) -> dict[str, Any]`

**Purpose:** Delete a file or directory inside the task workspace.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.

#### `def copy_into_workspace(host_path, dest_path) -> dict[str, Any]`

**Purpose:** Copy a host file or directory into the task workspace.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Iterate and transform or accumulate state.

#### `def clear_workspace() -> dict[str, Any]`

**Purpose:** Clear the dedicated sandbox workspace without deleting its root.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Private functions

#### `def _legacy_upload_relative_path(normalized_path) -> str | None`

**Purpose:** Map old upload paths from the prompt contract into the task workspace.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _reject_symlink_escape(path, original) -> None`

**Purpose:** Raise if path is a symlink whose target escapes the task root.

**Steps:**

1. Raise on invalid input or failure conditions.

#### `def _is_workspace_absolute_path(path) -> bool`

**Purpose:** Return True when an absolute path is under the model workspace.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _reject_non_workspace_absolute_path(path, kind) -> None`

**Purpose:** Reject absolute paths outside the model workspace for image-only tools.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Iterate and transform or accumulate state.

#### `def _stat_size(path, original) -> int`

**Purpose:** Return file size or raise FileNotFoundError with a normalized path.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Handle errors and map them to a safe response.

#### `def _reject_oversized_read(path, original, max_bytes) -> int`

**Purpose:** Reject reads above max_bytes with a structured file_too_large error.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Iterate and transform or accumulate state.

#### `def _guess_mime(path) -> str`

**Purpose:** Guess MIME type from file extension.

#### `def _is_probably_binary(data, mime_type) -> bool`

**Purpose:** Heuristic check whether sample bytes look binary.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _image_dimensions(data, mime_type) -> dict[str, int] | None`

**Purpose:** Return basic image dimensions for common formats without full decoding.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _image_payload(path, data, mime_type, *, include_preview=…, max_preview_bytes=…) -> dict[str, Any]`

**Purpose:** Build read_image result dict with optional base64 preview.

**Steps:**

1. Return the computed result to the caller.

#### `def _should_skip_entry(name, include_hidden) -> bool`

**Purpose:** Return True when a directory listing entry should be skipped.

**Steps:**

1. Return the computed result to the caller.

#### `def _line_slice(text, start_line, end_line) -> tuple[str, int, int, int]`

**Purpose:** Extract a 1-based line range from normalized text.

**Steps:**

1. Return the computed result to the caller.

#### `def _truncate_text(text, max_bytes) -> tuple[str, bool]`

**Purpose:** Truncate UTF-8 text to max_bytes.

**Steps:**

1. Return the computed result to the caller.

#### `def _split_edit_lines(text) -> tuple[list[str], bool]`

**Purpose:** Split normalized text into lines preserving trailing newline flag.

**Steps:**

1. Return the computed result to the caller.

#### `def _parse_line_range(range_str, total_lines) -> tuple[int, int, bool]`

**Purpose:** Parse a 1-based line range string into start, end, and insert-mode flag.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

#### `def _new_edit_lines(content) -> list[str]`

**Purpose:** Normalize edit content into a list of lines.

**Steps:**

1. Return the computed result to the caller.

#### `def _render_compact_line_edit_context(lines, highlight_start, highlight_end, max_chars, min_radius, max_radius) -> tuple[list[str], int, int, bool]`

**Purpose:** Build compact numbered context around edited lines.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Related

- [sandbox/_index](../../../../_index/)
