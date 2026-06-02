---
title: "setup_mcp"
draft: false
---

## Module `setup_mcp`

`Tools/mcp-web-search/setup_mcp.py` — ASLM Chat Python module.

---

## Public functions

#### `def main() -> None`

**Purpose:** CLI entry: write or print mcp.json for lmstudio or the project root.

**Steps:**

1. Iterate and transform or accumulate state.
2. Parse or serialize JSON payloads.

---

## Private functions

#### `def _detect_python() -> Path`

**Purpose:** Resolve the project virtualenv Python, falling back to the current interpreter.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _target_path(target, output) -> Path`

**Purpose:** Map a setup target or explicit output path to the destination mcp.json file.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.

#### `def _load_existing(path) -> dict`

**Purpose:** Load an existing mcp.json payload when present, otherwise return an empty dict.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Parse or serialize JSON payloads.

#### `def _server_entry(python_exe, timeout_ms) -> dict`

**Purpose:** Build one mcpServers entry for the FastMCP adapter module.

**Steps:**

1. Return the computed result to the caller.

---

## Related

- [mcp-web-search/_index](../../_index/)
