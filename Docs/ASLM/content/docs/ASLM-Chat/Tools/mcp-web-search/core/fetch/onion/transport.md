---
title: "transport"
draft: false
---

## Module `transport`

`Tools/mcp-web-search/core/fetch/onion/transport.py` — ASLM Chat Python module.

---

## Classes

### `class OnionFetch`

**Purpose:** Implements `OnionFetch`.

---

## Public functions

#### `def onion_available() -> bool`

**Purpose:** True when the onion layer can serve a fetch right now.

#### `async def onion_fetch(url, timeout, impersonate) -> OnionFetch`

**Purpose:** Fetch one URL over Tor. Never raises — returns an OnionFetch envelope.

---

## Private functions

#### `def _get(url, socks_url, timeout, impersonate) -> tuple[int, str]`

**Purpose:** Implements `_get`.

---

## Related

- [onion/_index](../../_index/)
