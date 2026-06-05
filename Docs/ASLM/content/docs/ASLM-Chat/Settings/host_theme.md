---
title: "host_theme"
draft: false
---

## Module `host_theme`

`Settings/host_theme.py` — ASLM Chat Python module.

---

## Public functions

#### `def atomic_write_json(path, data) -> None`

**Purpose:** Write JSON atomically via a temporary file and replace on success.

**Steps:**

1. Handle errors and map them to a safe response.

#### `def save_host_theme_payload(data) -> None`

**Purpose:** Persist the ASLM host theme snapshot next to module settings.

#### `def load_host_theme() -> dict[str, Any] | None`

**Purpose:** Load the last persisted host theme snapshot, or None when missing or invalid.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Parse or serialize JSON payloads.

---

## Related

- [Settings/_index](../_index/)
