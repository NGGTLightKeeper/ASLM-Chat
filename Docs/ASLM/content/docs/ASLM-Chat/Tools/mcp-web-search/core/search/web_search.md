---
title: "web_search"
draft: false
---

## Module `web_search`

`Tools/mcp-web-search/core/search/web_search.py` — ASLM Chat Python module.

---

## Classes

### `class EffortProfile`

**Purpose:** Type `EffortProfile` defined in `web_search.py`.

### `class WebSearchService`

**Purpose:** Type `WebSearchService` defined in `web_search.py`.

---

## Public functions

#### `def select_engines(effort, tracker) -> list[type]`

**Purpose:** Pick engines for a tier, honoring the circuit breaker.

**Steps:**

1. Return the computed result to the caller.

---

## Private functions

#### `def _host_readpage_only(host) -> bool`

**Purpose:** True when host is (a subdomain of) a read_page-only host.

**Steps:**

1. Return the computed result to the caller.

#### `def _inline_parse_allowed(host, url) -> bool`

**Purpose:** Whether a source may be parsed inline during a search, or should stay snippet-only.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _infer_pdf_url(url) -> str`

**Purpose:** Resolve a direct PDF URL for a result (already a PDF, or an arXiv abs → pdf link).

**Steps:**

1. Return the computed result to the caller.
