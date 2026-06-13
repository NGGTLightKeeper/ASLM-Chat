---
title: "brave"
draft: false
---

## Module `brave`

`Tools/mcp-web-search/core/engines/brave.py` — ASLM Chat Python module.

---

## Classes

### `class BraveParser`

**Purpose:** Parser for the Brave search engine.

#### Public Methods

- `def build_request(query, *, region, safesearch, timelimit, page) -> EngineRequest`
  - **Purpose:** Constructs an EngineRequest specific to the search engine, including parameters and headers.
- `def parse(document) -> EngineParseResult`
  - **Purpose:** Parses the HTML document to extract SearchResult objects.

---

## Related

- [_index](../_index/)
