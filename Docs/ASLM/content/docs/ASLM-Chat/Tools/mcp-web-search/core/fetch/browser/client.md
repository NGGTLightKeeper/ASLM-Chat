---
title: "client"
draft: false
---

## Module `client`

`Tools/mcp-web-search/core/fetch/browser/client.py` — ASLM Chat Python module.

---

## Classes

### `class BrowserClient`

**Purpose:** Routes page fetches to the warm cloakbrowser daemon (autostarted on first use).

---

## Public functions

#### `def get_browser_client() -> BrowserClient`

**Purpose:** Return the shared browser client singleton.

#### `async def browser_available() -> bool`

**Purpose:** Check if the browser layer is available.

#### `async def browser_fetch(url, wait_sec, nav_timeout, family) -> BrowserFetch`

**Purpose:** Fetch a URL via the browser layer.

#### `async def shutdown_browser() -> None`

**Purpose:** Close the shared HTTP client and shut down the daemon if autostarted.

---

## Related

- [browser/_index](./_index/)
