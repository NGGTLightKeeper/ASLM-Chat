---
title: "mcp-server"
draft: false
---

## Module `mcp-server`

`Tools/mcp-web-search/mcp-server.py` — ASLM Chat Python module.

---

## Public functions

#### `def supports(engine, model_name) -> bool`

**Purpose:** Return whether this server supports the given engine or model.

#### `async def call_tool(tool_id, arguments, context) -> dict[str, Any]`

**Purpose:** Dispatch an ASLM tool call to the matching search implementation.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Await async I/O or subprocess work.

---

#### `async def shutdown() -> None`

**Purpose:** Cancel outstanding background work (prefetch) at server shutdown.

## Private functions

#### `def _evict_caches_once() -> None`

**Purpose:** Reclaim disk from expired cache entries once per process, on first tool call.

#### `def _maybe_parse_list(val) -> Any`

**Purpose:** Run the ranked web_search pipeline (the model-facing default tool).

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.

#### `async def _call_serp_search(args) -> dict[str, Any]`

**Purpose:** Run the low-level raw SERP retrieval (unprocessed per-engine output).

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.

---

#### `async def _call_web_search(args) -> dict[str, Any]`

**Purpose:** Implementation of `_call_web_search`.


---

## Related

- [mcp-web-search/_index](../../_index/)
