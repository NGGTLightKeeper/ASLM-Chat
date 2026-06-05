---
title: "engine_stats"
draft: false
---

## Module `engine_stats`

`Tools/mcp-web-search/core/fetch/engine_stats.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools\mcp-web-search\core\fetch`. See **Related** for package index and callers.

---

## Classes

### `class Observation`

**Purpose:** Type `Observation` defined in `engine_stats.py`.

### `class EngineStats`

**Purpose:** Type `EngineStats` defined in `engine_stats.py`.

---

## Public functions

#### `def EngineStats.is_tripped() -> bool`

**Purpose:** Implements `EngineStats.is_tripped` in `engine_stats.py`.

#### `def EngineStats.observation_count() -> int`

**Purpose:** Implements `EngineStats.observation_count` in `engine_stats.py`.

#### `def EngineStats.latencies() -> list[float]`

**Purpose:** Implements `EngineStats.latencies` in `engine_stats.py`.

#### `def EngineStats.p50_latency() -> float`

**Purpose:** Implements `EngineStats.p50_latency` in `engine_stats.py`.

#### `def EngineStats.p95_latency() -> float`

**Purpose:** Implements `EngineStats.p95_latency` in `engine_stats.py`.

**Steps:**

1. Return the computed result to the caller.

#### `def EngineStats.success_rate() -> float`

**Purpose:** Implements `EngineStats.success_rate` in `engine_stats.py`.

#### `def EngineStats.error_rate() -> float`

**Purpose:** Implements `EngineStats.error_rate` in `engine_stats.py`.

#### `def EngineStats.quality_pass_rate() -> float`

**Purpose:** Implements `EngineStats.quality_pass_rate` in `engine_stats.py`.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def EngineStats.freshness_score() -> float`

**Purpose:** Implements `EngineStats.freshness_score` in `engine_stats.py`.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def EngineStats.result_stability() -> float`

**Purpose:** Implements `EngineStats.result_stability` in `engine_stats.py`.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def EngineStats.normalized_latency() -> float`

**Purpose:** Implements `EngineStats.normalized_latency` in `engine_stats.py`.

#### `def EngineStats.score() -> float`

**Purpose:** Implements `EngineStats.score` in `engine_stats.py`.

**Steps:**

1. Return the computed result to the caller.

#### `def EngineStats.tier() -> str`

**Purpose:** Implements `EngineStats.tier` in `engine_stats.py`.

**Steps:**

1. Return the computed result to the caller.

#### `def EngineStats.record(obs) -> None`

**Purpose:** Append observation and trip breaker on sustained failures.

#### `def EngineStats.summary() -> dict`

**Purpose:** JSON-serializable status dict for debugging and dashboards.

**Steps:**

1. Return the computed result to the caller.

#### `def make_registry(extra_engines) -> dict[str, EngineStats]`

**Purpose:** Build engine stats registry; optional extra_engines adds hosted providers.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Related

- [fetch/_index](../../../../_index/)
