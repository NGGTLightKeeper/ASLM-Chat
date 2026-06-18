---
title: "test_chunk_compaction"
draft: false
---

## Module `test_chunk_compaction`

`Tools/mcp-web-search/tests/test_chunk_compaction.py` — ASLM Chat Python module.

---

## Test methods

#### `def test_compress_selects_relevant_and_compacts() -> None`

**Purpose:** compress_chunks — relevance selection and size compaction.

#### `def test_compress_respects_budget_scaling() -> None`

**Purpose:** compress_chunks — respects char budget.

#### `def test_compress_rejects_seo_stuffed_block() -> None`

**Purpose:** compress_chunks — drops SEO-stuffed blocks.

#### `def test_compress_empty_query_does_not_crash() -> None`

**Purpose:** compress_chunks — handles empty query safely.

---

## Private functions

#### `def _doc() -> str`

**Purpose:** Provide a test document with relevant and irrelevant paragraphs.

---

## Related

- [tests/_index](../../../_index/)
