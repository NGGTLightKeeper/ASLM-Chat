---
title: "health"
draft: false
---

## Module `health`

`Tools/mcp-web-search/core/search/health.py` — ASLM Chat Python module.

---

## Classes

#### `class EngineHealthTracker`

**Purpose:** In-memory health registry + circuit breaker for SERP engines.

**Methods:**
- `allow(self, engine: str) -> bool:` Checks if an engine should be allowed.
- `record(self, engine: str, status: str, fetch_ms: float, results: int) -> None:` Record the outcome of one engine call (its serp_api payload fields).

---

## Related

- [search/_index](../_index/)
