---
title: "startpage"
draft: false
---

## Module `startpage`

`Tools/mcp-web-search/core/engines/startpage.py` — ASLM Chat Python module.

---

## Classes

### `class _Transport`

**Purpose:** Type `_Transport` defined in `startpage.py`.

#### Public Methods

- `def fetch(request) -> Any`
  - **Purpose:** Execute fetch logic.

### `class StartpageParser`

**Purpose:** Parser for the Startpage search engine.

#### Public Methods

- `def build_request_async(transport, query, *, region, safesearch, timelimit, page) -> EngineRequest`
  - **Purpose:** Execute build_request_async logic.
- `def parse(document) -> EngineParseResult`
  - **Purpose:** Parses the HTML document to extract SearchResult objects.

---

## Private functions

#### `def _to_text(value) -> str`

**Purpose:** Execute _to_text logic.

#### `def _between(text, start, end) -> str`

**Purpose:** Execute _between logic.

#### `def _fetch_sc_code(transport) -> str`

**Purpose:** Execute _fetch_sc_code logic.

#### `def _get_sc_code(transport) -> str`

**Purpose:** Execute _get_sc_code logic.

---

## Related

- [_index](../_index/)
