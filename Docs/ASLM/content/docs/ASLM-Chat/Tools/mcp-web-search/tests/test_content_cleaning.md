---
title: "test_content_cleaning"
draft: false
---

## Module `test_content_cleaning`

`Tools/mcp-web-search/tests/test_content_cleaning.py` — ASLM Chat Python module.

---

## Test methods

#### `def test_dom_block_extractor_rejects_nav_clusters() -> None`

**Purpose:** DOM block extraction — rejects structural nav/UI/link-farm.

#### `def test_normalize_page_drops_junk_keeps_content() -> None`

**Purpose:** normalize_page — drops junk blocks, retains real content.

#### `def test_micro_prune_drops_keyword_stuffed_clause() -> None`

**Purpose:** compress_read_page_markdown — query-aware clause pruning targets SEO text.

#### `def test_micro_prune_debug_reports_drop() -> None`

**Purpose:** prune_micro_chunks — debug payload reports clauses dropped.

#### `def test_micro_prune_noop_without_query() -> None`

**Purpose:** compress_read_page_markdown — no-op if no focus/query is provided.

---

## Private functions

#### `def _html() -> str`

**Purpose:** Load the test HTML fixture.

---

## Related

- [tests/_index](../../../_index/)
