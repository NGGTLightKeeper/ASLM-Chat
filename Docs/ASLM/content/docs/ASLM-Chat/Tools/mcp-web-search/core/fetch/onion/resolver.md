---
title: "resolver"
draft: false
---

## Module `resolver`

`Tools/mcp-web-search/core/fetch/onion/resolver.py` — ASLM Chat Python module.

---

## Public functions

#### `def resolve_onion(service, ttl, timeout, force) -> str`

**Purpose:** Current onion URL for a service: cached if fresh, else refreshed.

#### `def resolve_all(ttl, timeout) -> dict[str, str]`

**Purpose:** Refresh every vetted service's address.

#### `def reset_cache() -> None`

**Purpose:** Drop the resolver cache.

---

## Private functions

#### `def _fetch_onion_location(anchor, timeout) -> str | None`

**Purpose:** Read a clearnet anchor's Onion-Location header.

---

## Related

- [onion/_index](../../_index/)
