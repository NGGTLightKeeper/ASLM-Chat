---
title: "quality"
draft: false
---

## Module `quality`

`Tools/mcp-web-search/core/search/quality.py` — ASLM Chat Python module.

---

## Overview

Model-free SERP quality signals.

Everything here is deterministic, allocation-light, and budgeted for sub-millisecond
per-source evaluation so triage can run inline with the live result stream.

---

## Public functions

#### `def lexical_score(query, title, snippet, url) -> float`

**Purpose:** Implements `lexical_score` in `quality.py`.

#### `def hub_penalty(url, title, snippet) -> float`

**Purpose:** Implements `hub_penalty` in `quality.py`.

#### `def is_skip_title(title) -> bool`

**Purpose:** Implements `is_skip_title` in `quality.py`.

#### `def query_years(query)`

**Purpose:** Implements `query_years` in `quality.py`.

#### `def year_match_score(text, years) -> float`

**Purpose:** Implements `year_match_score` in `quality.py`.

#### `def has_date_signal(snippet) -> bool`

**Purpose:** Implements `has_date_signal` in `quality.py`.

#### `def infer_query_language(query) -> str`

**Purpose:** Implements `infer_query_language` in `quality.py`.

---

## Private functions

#### `def _term_pattern(term)`

**Purpose:** Implements `_term_pattern` in `quality.py`.

---

## Related

- [core](../../_index/)
