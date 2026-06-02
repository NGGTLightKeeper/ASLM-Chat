---
title: "routing_score"
draft: false
---

## Module `routing_score`

`Tools/mcp-web-search/core/query/routing_score.py` — ASLM Chat Python module.

---

## Classes

### `class QueryClassWeight`

**Purpose:** Type `QueryClassWeight` defined in `routing_score.py`.

### `class RoutingScore`

**Purpose:** Type `RoutingScore` defined in `routing_score.py`.

---

## Public functions

#### `def normalize_class_mix(classes) -> list[QueryClassWeight]`

**Purpose:** Normalize class weights to sum to 1; fallback to general on empty input.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def ensure_general_fallback(classes, *, floor=…) -> list[QueryClassWeight]`

**Purpose:** Ensure a general-class floor when a single non-general class dominates.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def class_mix_map(classes) -> dict[str, float]`

**Purpose:** Convert class weight list to name → weight map.

#### `def allocate_source_budget(classes, total) -> dict[str, int]`

**Purpose:** Distribute integer source budget across classes by normalized weights.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def compute_routing_score(url, classes) -> RoutingScore`

**Purpose:** Compute combined domain and trust routing multiplier for one URL.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Private functions

#### `def _weighted(values, mix, default) -> float`

**Purpose:** Weighted average over class mix; general uses default when absent from values.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _trust_entry_for_url(trust_registry, url)`

**Purpose:** Lookup trust registry entry by URL host pattern.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Related

- [query/_index](../../../../_index/)
