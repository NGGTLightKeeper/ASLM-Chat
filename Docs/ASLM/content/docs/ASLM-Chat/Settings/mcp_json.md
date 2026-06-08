---
title: "mcp_json"
draft: false
---

## Module `mcp_json`

`Settings/mcp_json.py` — ASLM Chat Python module.

---

## Classes

### `class UserMcpServerEntry`

**Purpose:** Type `UserMcpServerEntry` defined in `mcp_json.py`.

---

## Public functions

#### `def ensure_default_mcp_json() -> None`

**Purpose:** Create MCP/ and a default mcp.json when the file is missing.

#### `def mcp_json_signature() -> tuple[str, int] | None`

**Purpose:** Return path and mtime for cache invalidation, or None when the file is absent.

#### `def mcp_json_signature_for(module_dir) -> tuple[str, int] | None`

**Purpose:** Return path and mtime for cache invalidation, or None when the file is absent.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def load_raw_text() -> str`

**Purpose:** Return mcp.json contents, creating a default file when needed.

#### `def load_parsed() -> dict[str, Any]`

**Purpose:** Parse mcp.json into a dictionary.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Handle errors and map them to a safe response.
4. Parse or serialize JSON payloads.

#### `def validate_mcp_document(data) -> None`

**Purpose:** Raise ValueError when the document is not a valid MCP configuration.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Iterate and transform or accumulate state.

#### `def iter_user_mcp_entries(reserved_ids) -> list[UserMcpServerEntry]`

**Purpose:** Parse mcp.json and return user server entries with stable ids.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def save_raw_text(text) -> None`

**Purpose:** Validate JSON and atomically write mcp.json.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Handle errors and map them to a safe response.
3. Parse or serialize JSON payloads.

---

## Private functions

#### `def _slugify(value) -> str`

**Purpose:** Build a stable slug from a display name for MCP server ids.

#### `def _unique_server_id(base, taken) -> str`

**Purpose:** Pick a unique server id that does not collide with reserved ids.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---



#### `def iter_user_mcp_entries_for(module_dir, reserved_ids) -> list[UserMcpServerEntry]`

**Purpose:** Parse one module's mcp.json and return user server entries with stable ids.

**Steps:**

1. Execute the implementation in the source module.


## Related

- [Settings/_index](../_index/)