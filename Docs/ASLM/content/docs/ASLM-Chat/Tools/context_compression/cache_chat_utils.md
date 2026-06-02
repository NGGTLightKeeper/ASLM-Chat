---
title: "cache_chat_utils"
draft: false
---

## Module `cache_chat_utils`

`Tools/context_compression/cache_chat_utils.py` — ASLM Chat Python module.

---

## Public functions

#### `def connect_cache_db(db_path) -> sqlite3.Connection`

**Purpose:** Open the chat cache SQLite database with row dict access.

#### `def load_fattest_chat(conn) -> sqlite3.Row`

**Purpose:** Return the chat row with the largest combined message content footprint.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.

#### `def collect_chat_entries(conn, chat_id) -> tuple[list[dict[str, Any]], list[str]]`

**Purpose:** Load transcript entries and the latest user messages for compression input.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.
4. Parse or serialize JSON payloads.

---

## Related

- [context_compression/_index](../../_index/)
