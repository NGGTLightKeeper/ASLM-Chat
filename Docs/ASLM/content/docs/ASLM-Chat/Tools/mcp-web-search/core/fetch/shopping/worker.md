---
title: "worker"
draft: false
---

## Module `worker`

`Tools/mcp-web-search/core/fetch/shopping/worker.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools/mcp-web-search/core/fetch/shopping`. Manages the asynchronous execution of the isolated shopping search subprocess. Includes timeout handling, inter-process communication, and partial result recovery.

---

## Public functions

#### `async def async_shopping_search_worker(query: str, *, effort: str = "medium", limit: int = 8, language: str = "en", worker_timeout: float | None = None) -> dict[str, Any]`

**Purpose:** Spawns and manages the `_shopping_worker.py` child process. Captures JSON responses via stdout and gracefully recovers partial results or timeouts if the process runs too long.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Parse or serialize JSON payloads.
5. Spawn or communicate with a child process.

---

## Private functions

#### `def _read_partial_result(path: str | None) -> dict[str, Any]`

**Purpose:** Loads interim JSON payload directly from disk when a worker process timeouts or fails unexpectedly.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Parse or serialize JSON payloads.

#### `def _empty_result(query: str, effort: str, reason: str) -> dict[str, Any]`

**Purpose:** Normalizes empty or severely failed responses into a standard dictionary schema structure expected by downstream routing engines.

**Steps:**

1. Return the computed result to the caller.

---

## Related

- [shopping/_index](../../../../_index/)
