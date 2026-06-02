---
title: "test_micro_chunk_worker"
draft: false
---

## Module `test_micro_chunk_worker`

`Tools/mcp-web-search/tests/test_micro_chunk_worker.py` — ASLM Chat Python module.

---

## Test methods

#### `def test_numeric_variants_not_broken_by_micro_split() -> None`

**Purpose:** prune_micro_chunks — numeric punctuation variants survive micro-split.

#### `def test_surgically_drops_query_dense_fact_poor_clause() -> None`

**Purpose:** prune_micro_chunks — drop query-dense clauses with poor factual content.

#### `def test_reference_overlap_prunes_serp_like_clause() -> None`

**Purpose:** prune_micro_chunks — reference overlap prunes SERP-like boilerplate clauses.

#### `def test_drops_whole_sentence_if_only_tumor_remains() -> None`

**Purpose:** prune_micro_chunks — drop entire sentence when only noise clauses remain.

---

## Related

- [tests/_index](../../../_index/)
