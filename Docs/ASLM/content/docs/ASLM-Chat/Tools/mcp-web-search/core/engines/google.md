---
title: "google"
draft: false
---

## Module `google`

`Tools/mcp-web-search/core/engines/google.py` — ASLM Chat Python module.

---

## Classes

### `class GoogleParser`

**Purpose:** Parser for the Google search engine.

#### Public Methods

- `def build_request(query, *, region, safesearch, timelimit, page) -> EngineRequest`
  - **Purpose:** Constructs an EngineRequest specific to the search engine, including parameters and headers.
- `def parse(document) -> EngineParseResult`
  - **Purpose:** Parses the HTML document to extract SearchResult objects.

---

## Private functions

#### `def _unwrap_url(value) -> str`

**Purpose:** Execute _unwrap_url logic.

#### `def _is_internal(value) -> bool`

**Purpose:** Execute _is_internal logic.

---

## Related

- [_index](../_index/)
