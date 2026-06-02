---
title: "micro_chunk_worker"
draft: false
---

## Module `micro_chunk_worker`

`Tools/mcp-web-search/core/extract/micro_chunk_worker.py` — ASLM Chat Python module.

---

## Classes

### `class MicroPruneDebug`

**Purpose:** Type `MicroPruneDebug` defined in `micro_chunk_worker.py`.

---

## Public functions

#### `def prune_micro_chunks(text, query, *, reference_text=…) -> tuple[str, MicroPruneDebug]`

**Purpose:** Remove SEO-like micro-clauses; preserve factual fragments.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Private functions

#### `def _normalize_spaces(text) -> str`

**Purpose:** Collapse runs of whitespace to a single space.

#### `def _protect_numeric_punctuation(text) -> str`

**Purpose:** Protect decimal/range/version punctuation between digits from clause splits.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _restore_numeric_punctuation(text) -> str`

**Purpose:** Restore numeric punctuation sentinels after splitting.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _split_sentences(text) -> list[str]`

**Purpose:** Sentence-like split while preserving punctuation in each sentence.

#### `def _split_micro_clauses(sentence) -> list[str]`

**Purpose:** Split sentence into clauses by punctuation excluding dash.

#### `def _query_hits(tokens, query_set) -> int`

**Purpose:** Count tokens in clause that appear in the query/reference set.

#### `def _factual_signal(clause) -> float`

**Purpose:** Language-agnostic fact signal from structure (digits, ids, versions).

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _query_density(clause_tokens, query_set) -> float`

**Purpose:** Fraction of clause tokens that match query terms.

#### `def _reference_density(clause_tokens, reference_set) -> float`

**Purpose:** Fraction of clause tokens that match SERP/reference terms.

---

## Related

- [extract/_index](../../../../_index/)
