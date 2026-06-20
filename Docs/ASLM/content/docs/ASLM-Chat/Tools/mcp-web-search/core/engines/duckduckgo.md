---
title: "duckduckgo"
draft: false
---

## Module `duckduckgo`

`Tools/mcp-web-search/core/engines/duckduckgo.py` — ASLM Chat Python module.

---

## Classes

### `class DuckDuckGoParser`

**Purpose:** Parser for the DuckDuckGo search engine.

#### Public Methods

- `def build_request(query, *, region, safesearch, timelimit, page) -> EngineRequest`
  - **Purpose:** Constructs an EngineRequest specific to the search engine, including parameters and headers.
- `def parse(document) -> EngineParseResult`
  - **Purpose:** Parses the HTML document to extract SearchResult objects.

---

## Private functions

#### `def _unwrap_url(value) -> str`

**Purpose:** Execute _unwrap_url logic.

---

## Related

- [_index](../_index/)
