---
title: "client"
draft: false
---

## Module `client`

`Tools/mcp-web-search/core/fetch/browser/client.py` — ASLM Chat Python module.

---

## Classes

### `class BrowserClient`

**Purpose:** Type `BrowserClient` defined in `client.py`.

---

## Public functions

#### `async def aclose(self) -> None`

**Purpose:** Close the shared HTTP client only. The daemon is deliberately LEFT RUNNING so it stays warm across tool calls.

---

## Private functions

#### `def _spawn_process(self) -> None`

**Purpose:** Internal method to spawn the persistent browser daemon process.

**Steps:**

1. Return the computed result to the caller.

#### `def _client(self) -> httpx.AsyncClient`

**Purpose:** Return the long-lived httpx AsyncClient for communicating with the daemon.

**Steps:**

1. Return the computed result to the caller.

---

## Related

- [browser/_index](../_index/)
