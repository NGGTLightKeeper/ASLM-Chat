---
title: "test_web_search_neural_domain_eval"
draft: false
---

## Module `test_web_search_neural_domain_eval`

`Tools/mcp-web-search/tests/test_web_search_neural_domain_eval.py` — ASLM Chat Python module.

---

## Test methods

#### `def test_neural_web_search_domain_eval_trace() -> None`

**Purpose:** test_neural_web_search_domain_eval_trace — print JSON trace of domain/trust multipliers per fixture case.

**Steps:**

1. Iterate and transform or accumulate state.
2. Parse or serialize JSON payloads.

---

## Private functions

#### `def _class_mix(hybrid) -> dict[str, float]`

**Purpose:** _class_mix — flatten hybrid query-type tuples to name→weight map.

#### `def _trust_entry_for_url(trust_registry, url)`

**Purpose:** _trust_entry_for_url — resolve trust registry entry by host pattern match.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _domain_multiplier(url, class_mix) -> dict[str, float | str]`

**Purpose:** _domain_multiplier — compute domain weight breakdown for eval trace output.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _trust_multiplier(trust_registry, url, class_mix) -> dict[str, float | str]`

**Purpose:** _trust_multiplier — compute trust tier affinity for eval trace output.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Related

- [tests/_index](../../../_index/)
