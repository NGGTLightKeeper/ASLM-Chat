---
title: "domain_constraints"
draft: false
---

## Module `domain_constraints`

`Tools/mcp-web-search/core/query/domain_constraints.py` — ASLM Chat Python module.

---

## Classes

### `class DomainConstraints`

**Purpose:** Type `DomainConstraints` defined in `domain_constraints.py`.

---

## Public functions

#### `def DomainConstraints.has_constraints() -> bool`

**Purpose:** Implements `DomainConstraints.has_constraints` in `domain_constraints.py`.

#### `def parse_domain_constraints(query) -> DomainConstraints`

**Purpose:** Parse site: and bare -domain tokens from a search query string.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def build_provider_query(raw_query, constraints) -> str`

**Purpose:** Rebuild provider query with site: operators from parsed constraints.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def matches_domain_constraints(url, constraints) -> bool`

**Purpose:** Check whether a URL host satisfies include/exclude domain constraints.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def filter_results_by_domain_constraints(results, constraints) -> list[Any]`

**Purpose:** Filter result objects whose url attribute fails domain constraints.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Private functions

#### `def _normalize_domain(domain) -> str`

**Purpose:** Lowercase host pattern, strip www. and trailing dot.

**Steps:**

1. Return the computed result to the caller.

#### `def _is_host_match(host, pattern) -> bool`

**Purpose:** Match exact host or subdomain of pattern.

#### `def _append_unique(target, value) -> None`

**Purpose:** Append value to list if not already present.

#### `def _strip_orphan_domain_connectors(text) -> str`

**Purpose:** Remove leading/trailing OR connectors left after site: token removal.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Related

- [query/_index](../../../../_index/)
