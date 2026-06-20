---
title: "health"
draft: false
---

## Module `health`

`Tools/mcp-web-search/core/fetch/academic/health.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools/mcp-web-search/core/fetch/academic`.

---

## Classes

### `class ProviderHealth`

**Purpose:** Implements `ProviderHealth`.

#### `def ProviderHealth.__init__(self) -> None`

**Purpose:** Implements `__init__`.

#### `def ProviderHealth.available(self, name, min_interval) -> bool`

**Purpose:** Implements `available`.

#### `def ProviderHealth.note_fired(self, name) -> None`

**Purpose:** Implements `note_fired`.

#### `def ProviderHealth.cooldown_remaining(self, name) -> float`

**Purpose:** Implements `cooldown_remaining`.

#### `def ProviderHealth.record(self, name, ok, status_code, error) -> None`

**Purpose:** Implements `record`.

#### `def ProviderHealth.snapshot(self) -> dict[...]`

**Purpose:** Implements `snapshot`.

#### `def ProviderHealth.reset(self) -> None`

**Purpose:** Implements `reset`.

---

## Public functions

#### `def get_provider_health() -> ProviderHealth`

**Purpose:** Implements `get_provider_health`.

---

## Private functions

#### `def _is_empty_ok(status_code, error) -> bool`

**Purpose:** Implements `_is_empty_ok`.

---

## Related

- [academic/_index](../../_index/)
