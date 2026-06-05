---
title: "_shopping_worker"
draft: false
---

## Module `_shopping_worker`

`Tools/mcp-web-search/core/fetch/_shopping_worker.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools/mcp-web-search/core/fetch`. This script acts as an isolated worker for shopping search operations. It handles stdin/stdout communication, executes the shopping engine, and securely transmits JSON payloads even when non-ASCII text is present.

---

## Public functions

#### `def main() -> None`

**Purpose:** Entry point for the shopping worker. Reads payload from standard input, initiates the async search, writes partial buffers, and streams results back to standard output safely.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Parse or serialize JSON payloads.
5. Exit gracefully or with an error status code.

---

## Private functions

#### `def _fail(msg: str) -> None`

**Purpose:** Write a standard error JSON response to standard output and flush.

**Steps:**

1. Parse or serialize JSON payloads.

#### `def _write_partial(path: str | None, result: dict) -> None`

**Purpose:** Safely writes interim search results to a temporary file via atomic replace, guarding against sudden termination or timeouts.

**Steps:**

1. Handle errors and map them to a safe response.
2. Parse or serialize JSON payloads.

#### `async def _run(payload: dict) -> dict`

**Purpose:** Core shopping search dispatcher. Pulls query, effort, limit, and language parameters from the payload and queries the underlying `search_shopping` engine.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.

---

## Related

- [fetch/_index](../../../_index/)
