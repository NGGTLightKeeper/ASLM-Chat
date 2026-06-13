---
title: "qwant"
draft: false
---

## Module `qwant`

`Tools/mcp-web-search/core/engines/qwant.py` — ASLM Chat Python module.

---

## Classes

### `class QwantParser`

**Purpose:** Parser for the Qwant search engine.

#### Public Methods

- `def build_request(query, *, region, safesearch, timelimit, page) -> EngineRequest`
  - **Purpose:** Constructs an EngineRequest specific to the search engine, including parameters and headers.
- `def parse(document) -> EngineParseResult`
  - **Purpose:** Parses the HTML document to extract SearchResult objects.

---

## Related

- [_index](../_index/)
