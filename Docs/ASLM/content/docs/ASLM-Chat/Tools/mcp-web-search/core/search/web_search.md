---
title: "web_search"
draft: false
---

## Module `web_search`

`Tools/mcp-web-search/core/search/web_search.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools/mcp-web-search/core/search`.

---

## Classes

### `class EffortProfile`

**Purpose:** Implements `EffortProfile`.

### `class _Source`

**Purpose:** Implements `_Source`.

### `class WebSearchService`

**Purpose:** Implements `WebSearchService`.

#### `def WebSearchService.__init__(self, tracker, read_page) -> None`

**Purpose:** Implements `__init__`.

#### `def WebSearchService._reader(self)`

**Purpose:** Implements `_reader`.

#### `async def WebSearchService._parse_one(self, source, profile, query) -> None`

**Purpose:** Implements `_parse_one`.

#### `def WebSearchService._hosted_stream(self, query, region, deadline)`

**Purpose:** Implements `_hosted_stream`.

#### `async def WebSearchService.search(self, query, effort, region, safesearch, timelimit, shopping, academic) -> dict[...]`

**Purpose:** Implements `search`.

#### `async def WebSearchService._shopping_sources(self, query, profile, language, search_id, start_rank) -> list[...]`

**Purpose:** Implements `_shopping_sources`.

#### `async def WebSearchService._academic_sources(self, query, profile, search_id, start_rank) -> list[...]`

**Purpose:** Implements `_academic_sources`.

#### `async def WebSearchService._onion_sources(self, query, profile, search_id, start_rank) -> list[...]`

**Purpose:** Deep onion search: per-site search over Tor → parallel scrape of top results.

---

## Public functions

#### `def select_engines(effort, tracker) -> list[...]`

**Purpose:** Implements `select_engines`.

#### `async def run_web_search(query, effort, region, safesearch, timelimit, shopping, academic) -> dict[...]`

**Purpose:** Implements `run_web_search`.

---

## Private functions

#### `async def _merge_streams(*streams)`

**Purpose:** Implements `_merge_streams`.

#### `def _inline_parse_allowed(url) -> bool`

**Purpose:** Implements `_inline_parse_allowed`.

#### `def _infer_pdf_url(url) -> str`

**Purpose:** Implements `_infer_pdf_url`.

#### `def _make_search_id() -> str`

**Purpose:** Implements `_make_search_id`.

#### `def _citation_id(search_id, rank) -> str`

**Purpose:** Implements `_citation_id`.

#### `def _build_model_context(query, sources, total_budget, per_source_chars) -> str`

**Purpose:** Implements `_build_model_context`.

#### `def _shopping_product_dict(product, citation_id, rank) -> dict[...]`

**Purpose:** Implements `_shopping_product_dict`.

#### `def _academic_paper_dict(paper, citation_id, rank) -> dict[...]`

**Purpose:** Implements `_academic_paper_dict`.

#### `def _build_ui(sources) -> dict[...]`

**Purpose:** Implements `_build_ui`.

#### `def _repeat_block_payload(query, effort, age) -> dict[...]`

**Purpose:** Implements `_repeat_block_payload`.

---

## Related

- [search/_index](../../_index/)
