---
title: "tor_proxy"
draft: false
---

## Module `tor_proxy`

`Tools/mcp-web-search/core/fetch/onion/tor_proxy.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools/mcp-web-search/core/fetch/onion`.

---

## Public functions

#### `def resolve_socks(force: bool = False) -> str | None`

**Purpose:** Resolve (and cache) a usable tor SOCKS url, or None when unavailable/disabled. Pure probing — no process is ever spawned. `force` re-probes (e.g. after the user starts Tor Browser).

#### `def reset() -> None`

**Purpose:** Drop the cached resolution so the next call re-probes (tests / after starting tor).

---

## Private functions

#### `def _port_open(host: str, port: int, timeout: float = 1.0) -> bool`

**Purpose:** True when something accepts a TCP connection on host:port.

---

## Related

- [onion/_index](../_index/)
