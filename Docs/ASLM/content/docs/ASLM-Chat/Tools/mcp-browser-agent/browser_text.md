---
title: "browser_text"
draft: false
---

## Module `browser_text`

`Tools/mcp-browser-agent/browser_text.py` — ASLM Chat Python module.

---

## Public functions

#### `def replace_line_range(current, raw_range, replacement) -> str`

**Purpose:** Replace or insert lines in editor text using a 1-based line range.

**Steps:**

1. Return the computed result to the caller.

#### `async def handle_browser_text(args, *, page, keyboard, take_snapshot, flatten_content) -> str`

**Purpose:** Execute browser_text: read, set, replace, or delete editor content and return a snapshot.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.

---

## Private functions

#### `def _parse_line_range(raw_range, total_lines) -> tuple[int, int, bool]`

**Purpose:** Parse a 1-based line range string into start, end, and insert-mode flag.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.

#### `async def _read_or_set_text_state(page, ref, mode, text) -> dict[str, Any]`

**Purpose:** Read or set text in the focused editor or in the element identified by ref.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Await async I/O or subprocess work.

#### `async def _first_visible(locator) -> Any | None`

**Purpose:** Return the first visible locator match from a multi-match locator.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

#### `async def _resolve_text_locator(page, elem) -> Any | None`

**Purpose:** Resolve text refs using exact DOM attributes before broad role fallback.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Iterate and transform or accumulate state.

#### `def _css_string(value) -> str`

**Purpose:** Escape a string for use inside a CSS attribute selector.

#### `def _infer_action(args) -> str`

**Purpose:** Infer read/set/replace/delete from explicit action or argument shape.

**Steps:**

1. Return the computed result to the caller.

#### `def _non_editable_error(ref, target, action) -> str`

**Purpose:** Build a user-facing error when the text target is not editable.

**Steps:**

1. Return the computed result to the caller.

#### `def _next_text(action, args, current) -> str`

**Purpose:** Compute the next editor value for set, replace, or delete actions.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Iterate and transform or accumulate state.

#### `def _replace_match(current, old_text, replacement, replace_all) -> str`

**Purpose:** Replace one or all occurrences of old_text, with ambiguity checks.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.

---

## Related

- [mcp-browser-agent/_index](../../_index/)
