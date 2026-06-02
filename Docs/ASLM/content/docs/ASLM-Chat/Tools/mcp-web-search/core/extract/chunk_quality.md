---
title: "chunk_quality"
draft: false
---

## Module `chunk_quality`

`Tools/mcp-web-search/core/extract/chunk_quality.py` — ASLM Chat Python module.

---

## Public functions

#### `def seo_keyword_stuffing_penalty(text, query_terms) -> float`

**Purpose:** Return 0..1 penalty for SEO keyword piles (1 = reject-worthy spam).

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def is_seo_hard_reject(chunk_text, query_tokens, threshold) -> bool`

**Purpose:** True when SEO stuffing penalty meets or exceeds the hard-reject threshold.

**Steps:**

1. Return the computed result to the caller.

---

## Private functions

#### `def _tokenize(text) -> list[str]`

**Purpose:** Lowercase word tokens with length > 1.

#### `def _sentence_like_ratio(text) -> float`

**Purpose:** Fraction of text that looks like complete sentences (by ending punctuation).

**Steps:**

1. Return the computed result to the caller.

#### `def _repeated_trigram_penalty(tokens) -> float`

**Purpose:** Penalty for repeated trigrams (keyword-stuffing signal).

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Related

- [extract/_index](../../../../_index/)
