---
title: "engine"
draft: false
---

## Module `engine`

`Tools/mcp-web-search/core/fetch/academic/engine.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools/mcp-web-search/core/fetch/academic`.

---

## Classes

### `class AcademicSearchEngine`

**Purpose:** Implements `AcademicSearchEngine`.

#### `async def AcademicSearchEngine.search(self, query, effort, limit, hard_timeout_ms) -> AcademicSearchResult`

**Purpose:** Implements `search`.

#### `async def AcademicSearchEngine._provider(self, client, provider, query, limit) -> tuple[...]`

**Purpose:** Implements `_provider`.

#### `def AcademicSearchEngine._score(self, paper, provider) -> float`

**Purpose:** Implements `_score`.

#### `def AcademicSearchEngine._rank_and_dedupe(self, papers, cap) -> list[...]`

**Purpose:** Implements `_rank_and_dedupe`.

#### `def AcademicSearchEngine._backfill(keep, other) -> None`

**Purpose:** Implements `_backfill`.

---

## Public functions

#### `async def search_academic(query, effort, limit) -> AcademicSearchResult`

**Purpose:** Implements `search_academic`.

---

## Private functions

#### `def _min_interval(provider) -> float`

**Purpose:** Implements `_min_interval`.

---

## Related

- [academic/_index](../../_index/)
