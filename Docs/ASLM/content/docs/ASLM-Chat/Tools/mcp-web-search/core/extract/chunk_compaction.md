---
title: "chunk_compaction"
draft: false
---

## Module `chunk_compaction`

`Tools/mcp-web-search/core/extract/chunk_compaction.py` — ASLM Chat Python module.

---

## Classes

### `class _Policy`

**Purpose:** Type `_Policy` defined in `chunk_compaction.py`.

---

## Public functions

#### `def compress_chunks(text, query, *, char_budget=…) -> str`

**Purpose:** Select the paragraphs most relevant to the query, dropping SEO-stuffed blocks, and pack them into the (optionally rescaled) character budget. Returns the joined text.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Private functions

#### `def _policy_for(char_budget) -> _Policy`

**Purpose:** The single compaction policy, optionally rescaled to a caller's char budget.

**Steps:**

1. Return the computed result to the caller.

#### `def _sentence_like_ratio(text) -> float`

**Purpose:** Fraction of text that looks like complete sentences.

**Steps:**

1. Return the computed result to the caller.

#### `def _entity_heuristic_score(text) -> float`

**Purpose:** Cheap factual-density proxy without GLiNER (0..1).

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _normalize_scores(values) -> list[float]`

**Purpose:** Scale scores to [0, 1] by peak value.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _score_paragraphs(paragraphs, query_terms, policy) -> list[tuple[float, float]]`

**Purpose:** Return (hybrid_score, seo_penalty) per paragraph.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _chunk_limit(policy, strong_count) -> int`

**Purpose:** Cap on paragraph count; expands when many strong chunks exist.

**Steps:**

1. Return the computed result to the caller.

---

## Related

- [extract/_index](../../../../_index/)
