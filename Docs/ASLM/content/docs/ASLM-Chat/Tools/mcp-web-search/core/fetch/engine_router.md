---
title: "engine_router"
draft: false
---

## Module `engine_router`

`Tools/mcp-web-search/core/fetch/engine_router.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools\mcp-web-search\core\fetch`. See **Related** for package index and callers.

---

## Classes

### `class EngineRouter`

**Purpose:** Type `EngineRouter` defined in `engine_router.py`.

---

## Public functions

#### `def EngineRouter.__init__(registry) -> None`

**Purpose:** Wire registry and reentrant lock for nested pick_pool calls.

#### `def EngineRouter.hot() -> list[EngineStats]`

**Purpose:** Engines currently in the hot tier.

#### `def EngineRouter.warm() -> list[EngineStats]`

**Purpose:** Engines currently in the warm tier.

#### `def EngineRouter.cold() -> list[EngineStats]`

**Purpose:** Engines currently in the cold tier.

#### `def EngineRouter.tripped() -> list[EngineStats]`

**Purpose:** Engines with an active circuit-breaker trip.

#### `def EngineRouter.pick() -> str`

**Purpose:** Return the single best backend name (hot → warm → cold; 10% exploration).

**Steps:**

1. Return the computed result to the caller.

#### `def EngineRouter.pick_pool(n) -> list[str]`

**Purpose:** Return up to n backend names for parallel probing (hot, then warm, then cold).

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def EngineRouter.available(exclude) -> list[str]`

**Purpose:** Return non-tripped engines not in exclude, sorted by score.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def EngineRouter.record(engine, obs) -> None`

**Purpose:** Record one observation and update engine reputation.

#### `def EngineRouter.status() -> list[dict]`

**Purpose:** Per-engine summary rows sorted by score (for status endpoints).

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def get_router() -> EngineRouter`

**Purpose:** Lazily initialized global EngineRouter; registers hosted engines on first call.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

---

## Private functions

#### `def _quality_pass(results) -> bool`

**Purpose:** True if >= 50% of results have a non-trivial snippet (>= 30 chars).

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _result_hash(results) -> int`

**Purpose:** Stable hash of the top-5 URLs for stability tracking.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Related

- [fetch/_index](../../../../_index/)
