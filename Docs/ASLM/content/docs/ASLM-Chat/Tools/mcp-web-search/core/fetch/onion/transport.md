---
title: "transport"
draft: false
---

## Module `transport`

`Tools/mcp-web-search/core/fetch/onion/transport.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools/mcp-web-search/core/fetch/onion`.

---

## Classes

### `class OnionFetch`

**Purpose:** Implements `OnionFetch`.

---

## Public functions

#### `def onion_available() -> bool`

**Purpose:** True when the onion layer can serve a fetch right now (tor enabled + a SOCKS resolved).

#### `async def onion_fetch(url: str, *, timeout: float | None = None, impersonate: str = "chrome124") -> OnionFetch`

**Purpose:** Fetch one URL over Tor. Never raises — returns an OnionFetch envelope.

---

## Private functions

#### `def _get(url: str, socks_url: str, timeout: float, impersonate: str) -> tuple[int, str]`

**Purpose:** Blocking curl_cffi GET through the tor SOCKS (runs in the io_pool).

---

## Related

- [onion/_index](../_index/)
