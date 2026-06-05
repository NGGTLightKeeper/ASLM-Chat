---
title: "presenters"
draft: false
---

## Module `presenters`

`Tools/mcp-sandbox/supervisor/sandbox/presenters.py` — ASLM Chat Python module.

---

## Public functions

#### `def present_auto_preview(path, head_lines, total_lines, size_bytes, mime, kind, tail_lines, tail_start_line) -> str`

**Purpose:** Pick code vs text preview based on extension and detected structure in head lines.

**Steps:**

1. Return the computed result to the caller.

#### `def present_read_slice(*, path, content, start_line, end_line, total_lines, size_bytes) -> str`

**Purpose:** Format a bounded read slice for legacy controller OPEN responses.

**Steps:**

1. Return the computed result to the caller.

#### `def present_grep_results(*, matches, pattern, path) -> str`

**Purpose:** Format grep matches for legacy controller LOCATE responses.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Private functions

#### `def _human_size(size_bytes) -> str`

**Purpose:** Format byte count as B, KB, or MB for display.

**Steps:**

1. Return the computed result to the caller.

#### `def _extract_code_structure(lines) -> list[dict[str, object]]`

**Purpose:** Scan head lines for top-level symbols (class, def, fn, etc.).

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _extract_markdown_headings(lines) -> list[dict[str, object]]`

**Purpose:** Collect markdown heading landmarks from head lines.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _extract_text_landmarks(lines, max_landmarks) -> list[dict[str, object]]`

**Purpose:** Sample evenly spaced non-empty lines as landmarks for plain text files.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _present_code_preview(path, head_lines, total_lines, size_bytes, tail_lines, tail_start_line) -> str`

**Purpose:** Structured preview for source files: symbol map, head/tail slices, next-step hints.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _present_text_preview(path, head_lines, total_lines, size_bytes, tail_lines, tail_start_line) -> str`

**Purpose:** Structured preview for prose/config: landmarks, head/tail slices, next-step hints.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Related

- [sandbox/_index](../../../../_index/)
