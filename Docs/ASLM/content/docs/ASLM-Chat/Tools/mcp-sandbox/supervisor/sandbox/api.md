---
title: "api"
draft: false
---

## Module `api`

`Tools/mcp-sandbox/supervisor/sandbox/api.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools\mcp-sandbox\supervisor\sandbox`. See **Related** for package index and callers.

---

## Public functions

#### `def handle_tool(tool_id, arguments, context, *, progress_callback=…) -> dict[str, Any]`

**Purpose:** Dispatch a sandbox tool call to the registered handler with error wrapping.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

---

## Private functions

#### `def _wrap_workspace_payload(tool, payload) -> dict[str, Any]`

**Purpose:** Wrap a workspace helper payload in the sandbox v2 success envelope.

**Steps:**

1. Return the computed result to the caller.

#### `def _safe_split(command) -> list[str] | None`

**Purpose:** Split a shell command with shlex; return None on malformed quoting.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _normalize_cwd_argument(raw_cwd) -> str`

**Purpose:** Normalize bash cwd: empty, None, and "none" map to ".".

**Steps:**

1. Return the computed result to the caller.

#### `def _read_text_for_cat(path) -> tuple[str, list[str], bool, dict[str, Any]]`

**Purpose:** Read text for supervised cat/less/more routing.

**Steps:**

1. Return the computed result to the caller.

#### `def _build_large_file_preview(path, meta) -> str`

**Purpose:** Build a structured preview for large text files routed from cat/less/more.

**Steps:**

1. Return the computed result to the caller.

#### `def _bash_success(stdout, stderr, warnings, cwd) -> dict[str, Any]`

**Purpose:** Build a successful routed bash response with output truncation applied.

**Steps:**

1. Return the computed result to the caller.

#### `def _bash_routed_error(error_type, message, cwd) -> dict[str, Any]`

**Purpose:** Build a failed routed bash response that preserves bash result shape.

**Steps:**

1. Return the computed result to the caller.

#### `def _try_file_preview_command(command, cwd) -> dict[str, Any] | None`

**Purpose:** Intercept plain cat/less/more of a single file with structured previews.

**Steps:**

1. Return the computed result to the caller.

#### `def _try_job_command(command, cwd) -> dict[str, Any] | None`

**Purpose:** Intercept jobs/fg/kill commands for background job management.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Parse or serialize JSON payloads.

#### `def _try_supervise(command, cwd) -> dict[str, Any] | None`

**Purpose:** Handle only supervisor-owned commands; everything else runs as bash.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _handle_bash(arguments, _context, *, progress_callback=…) -> dict[str, Any]`

**Purpose:** Run bash with supervisor routing for cat/less/more and background jobs.

**Steps:**

1. Return the computed result to the caller.

#### `def _handle_write(arguments, _context) -> dict[str, Any]`

**Purpose:** Create or overwrite a UTF-8 text file in the task workspace.

**Steps:**

1. Return the computed result to the caller.

#### `def _handle_share_file(arguments, _context) -> dict[str, Any]`

**Purpose:** Present a workspace file as a downloadable shared_file card.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _build_share_render_preview(raw_path, meta) -> tuple[dict[str, Any] | None, list[str]]`

**Purpose:** Build optional rich render preview for shared images and tabular files.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _has_argument_value(arguments, key) -> bool`

**Purpose:** Return True when an edit argument key is present and non-empty.

**Steps:**

1. Return the computed result to the caller.

#### `def _is_lines_edit_arguments(arguments) -> bool`

**Purpose:** Detect line-range edit mode from explicit mode or range argument presence.

**Steps:**

1. Return the computed result to the caller.

#### `def _line_range_argument(arguments) -> Any`

**Purpose:** Return the line range argument for mode='lines' edits.

#### `def _handle_edit(arguments, _context) -> dict[str, Any]`

**Purpose:** Dispatch match or lines edit modes to workspace helpers.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _load_model_runtime_metadata() -> dict[str, Any]`

**Purpose:** Load model runtime metadata from the shared JSON file on disk.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _resolve_active_model_record(context) -> tuple[dict[str, Any], str]`

**Purpose:** Resolve the active model record from context or runtime metadata.

**Steps:**

1. Return the computed result to the caller.

#### `def _model_supports_vision(context) -> tuple[bool, dict[str, Any], str]`

**Purpose:** Check whether the active model supports vision from runtime metadata.

**Steps:**

1. Return the computed result to the caller.

#### `def _view_image_without_visual_preview(image_payload, model_record, source) -> dict[str, Any]`

**Purpose:** Replace inline image preview with a text placeholder when vision is disabled.

**Steps:**

1. Return the computed result to the caller.

#### `def _handle_view_image(arguments, _context) -> dict[str, Any]`

**Purpose:** Read image metadata and gate inline preview on model vision support.

**Steps:**

1. Return the computed result to the caller.

---

## Related

- [sandbox/_index](../../../../_index/)
