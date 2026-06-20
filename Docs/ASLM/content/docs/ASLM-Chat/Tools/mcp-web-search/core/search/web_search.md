---
title: "web_search"
draft: false
---

## Module `web_search`

`Tools/mcp-web-search/core/search/web_search.py` — ASLM Chat Python module.

---

## Overview

Web-search orchestrator: stream → triage → bounded eager parse scheduler.

Wires the live SERP stream to incremental triage and an eager parse scheduler:

    search_stream → source event → triage.ingest (~0.1 ms)
        ├─ PARSE  → fetch/parse starts immediately (bounded slots)
        ├─ QUEUE  → held; consensus votes may upgrade it mid-stream
        └─ SKIP   → dropped

Engine selection is tier-based (low/medium/high) and gated by the per-engine
circuit breaker. Parsing of early winners overlaps the tail of slow engines, so
parse latency hides inside SERP latency.

Process discipline (non-negotiable): every parse task is tracked and cancelled
at the deadline. No fire-and-forget tasks. The persistent warm browser lives in
its own daemon, so a cancelled search never leaves a browser process behind.

---

## Classes

### `class EffortProfile`

**Purpose:** Type `EffortProfile` defined in `web_search.py`.

### `class _Source`

**Purpose:** Type `_Source` defined in `web_search.py`.

### `class WebSearchService`

**Purpose:** Type `WebSearchService` defined in `web_search.py`.

#### `def WebSearchService.__init__()`

**Purpose:** Implements `WebSearchService.__init__` in `web_search.py`.

#### `def WebSearchService.search(query)`

**Purpose:** Implements `WebSearchService.search` in `web_search.py`.

---

## Public functions

#### `def select_engines(effort, tracker)`

**Purpose:** Implements `select_engines` in `web_search.py`.

#### `def run_web_search(query)`

**Purpose:** Implements `run_web_search` in `web_search.py`.

---

## Private functions

#### `def _merge_streams()`

**Purpose:** Implements `_merge_streams` in `web_search.py`.

#### `def _inline_parse_allowed(url) -> bool`

**Purpose:** Implements `_inline_parse_allowed` in `web_search.py`.

#### `def _infer_pdf_url(url) -> str`

**Purpose:** Implements `_infer_pdf_url` in `web_search.py`.

#### `def _make_search_id() -> str`

**Purpose:** Implements `_make_search_id` in `web_search.py`.

#### `def _citation_id(search_id, rank) -> str`

**Purpose:** Implements `_citation_id` in `web_search.py`.

#### `def _build_model_context(query, sources) -> str`

**Purpose:** Implements `_build_model_context` in `web_search.py`.

#### `def _shopping_product_dict(product)`

**Purpose:** Implements `_shopping_product_dict` in `web_search.py`.

#### `def _build_ui(sources)`

**Purpose:** Implements `_build_ui` in `web_search.py`.

#### `def _repeat_block_payload(query, effort, age)`

**Purpose:** Implements `_repeat_block_payload` in `web_search.py`.

---

## Related

- [core](../../_index/)
