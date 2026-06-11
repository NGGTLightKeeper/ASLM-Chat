---
title: "models"
draft: false
---

## Module `models`

`Tools/mcp-web-search/core/engines/models.py` — ASLM Chat Python module.

---

## Classes

### `ParseStatus(StrEnum)`

**Purpose:** Possible outcomes of one engine parse attempt.

### `SearchResult`

**Purpose:** Immutable representation of a single search result.

### `EngineRequest`

**Purpose:** Immutable HTTP request descriptor passed to transport backends.

### `EngineParseResult`

**Purpose:** Mutable result container produced by each engine parser.

#### `def coverage(self) -> float`

**Purpose:** Return the fraction of seen cards that produced usable results.

**Steps:**

1. Return the computed result to the caller.

---

## Related

- [engines/_index](../_index/)
