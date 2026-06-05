---
title: "scoring"
draft: false
---

## Module `scoring`

`Tools/mcp-web-search/core/extract/scoring.py` — ASLM Chat Python module.

---

## Public functions

#### `def query_terms(query) -> list[str]`

**Purpose:** Tokenise query into meaningful terms (stopwords removed when possible).

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def lexical_score(query, title, snippet, url) -> float`

**Purpose:** BM25-lite relevance score in [0, 1] from title, snippet, and URL path.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def densify_text_gliner(text, output_chars) -> str`

**Purpose:** Keep highest entity-density paragraphs via GliNER; fall back to head-truncation.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

---

## Related

- [extract/_index](../../../../_index/)
