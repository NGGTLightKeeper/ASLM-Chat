---
title: "health"
draft: false
---

## Module `health`

`Tools/mcp-web-search/core/search/health.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools/mcp-web-search/core/search`.

---

## Classes

### `class BreakerState`

**Purpose:** Implements `BreakerState`.

### `class EngineHealth`

**Purpose:** Implements `EngineHealth`.

### `class EngineHealthTracker`

**Purpose:** Implements `EngineHealthTracker`.

#### `def EngineHealthTracker.__init__(self, clock) -> None`

**Purpose:** Implements `__init__`.

#### `def EngineHealthTracker._health(self, engine) -> EngineHealth`

**Purpose:** Implements `_health`.

#### `def EngineHealthTracker.allow(self, engine) -> bool`

**Purpose:** Implements `allow`.

#### `def EngineHealthTracker._breaker_admits(self, health, now) -> bool`

**Purpose:** Implements `_breaker_admits`.

#### `def EngineHealthTracker._note_fired(self, engine, health, now) -> None`

**Purpose:** Implements `_note_fired`.

#### `def EngineHealthTracker.record(self, engine, status, fetch_ms, results) -> None`

**Purpose:** Implements `record`.

#### `def EngineHealthTracker._trip(self, health, base_cooldown) -> None`

**Purpose:** Implements `_trip`.

#### `def EngineHealthTracker.snapshot(self) -> dict[...]`

**Purpose:** Implements `snapshot`.

---

## Public functions

#### `def get_health_tracker() -> EngineHealthTracker`

**Purpose:** Implements `get_health_tracker`.

---

## Related

- [search/_index](../../_index/)
