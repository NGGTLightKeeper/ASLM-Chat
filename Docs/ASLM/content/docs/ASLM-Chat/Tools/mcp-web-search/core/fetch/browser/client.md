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

#### `def get_browser_client() -> BrowserClient`

**Purpose:** Lazily-initialised process-wide BrowserClient singleton.

**Steps:**

1. Return the computed result to the caller.

#### `def browser_available() -> bool`

**Purpose:** True when the configured browser backend may be used right now.

**Steps:**

1. Return the computed result to the caller.

#### `def browser_fetch(url, *, wait_sec, nav_timeout, family) -> BrowserFetch`

**Purpose:** Fetch one URL through the configured browser backend (never raises).

**Steps:**

1. Return the computed result to the caller.

#### `def shutdown_browser() -> None`

**Purpose:** Release the client's HTTP resources (wire into the MCP server shutdown hook).

**Steps:**

1. Return the computed result to the caller.
