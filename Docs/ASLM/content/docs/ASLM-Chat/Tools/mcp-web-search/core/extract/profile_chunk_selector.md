---
title: "profile_chunk_selector"
draft: false
---

## Module `profile_chunk_selector`

`Tools/mcp-web-search/core/extract/profile_chunk_selector.py` — ASLM Chat Python module.

---

## Classes

### `class ChunkCompressPolicy`

**Purpose:** Type `ChunkCompressPolicy` defined in `profile_chunk_selector.py`.

---

## Public functions

#### `def policy_family(query_type) -> str`

**Purpose:** Map query class to breadth / general / depth chunk family.

**Steps:**

1. Return the computed result to the caller.

#### `def resolve_chunk_policy(query_type, *, char_budget=…) -> ChunkCompressPolicy`

**Purpose:** Map primary query class to chunk selection policy (optional char budget override).

**Steps:**

1. Return the computed result to the caller.

#### `def compress_chunks_profiled(text, query, *, query_type=…, char_budget=…) -> tuple[str, dict[str, object]]`

**Purpose:** Select paragraphs by relevance + entity heuristics; penalize SEO stuffing.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Private functions

#### `def _tokenize(text) -> list[str]`

**Purpose:** Tokenize text via BM25 helper.

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

---

## Related

- [extract/_index](../../../../_index/)
