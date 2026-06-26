---
title: "registry"
draft: false
---

## Module `registry`

`Tools/mcp-web-search/core/fetch/onion/registry.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools/mcp-web-search/core/fetch/onion`.

---

## Public functions

#### `def load_seed_services() -> tuple[OnionService, ...]`

**Purpose:** The hand-vetted bootstrap from the JSON seed (immutable → cached).

#### `def load_services() -> tuple[OnionService, ...]`

**Purpose:** All vetted services. The allowlist is exactly the hand-vetted seed — kept as a distinct function (not just an alias) so callers have a stable "all services" entry point.

#### `def service_for(name: str) -> OnionService | None`

**Purpose:** Look up one vetted service by name (exact, case-insensitive).

#### `def services_in(category: str) -> tuple[OnionService, ...]`

**Purpose:** Services in a given category (e.g. all "media" onions for a news query).

---

## Related

- [onion/_index](../_index/)
