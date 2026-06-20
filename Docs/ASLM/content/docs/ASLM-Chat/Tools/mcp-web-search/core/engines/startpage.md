---
title: "startpage"
draft: false
---

## Module `startpage`

`Tools/mcp-web-search/core/engines/startpage.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools/mcp-web-search/core/engines`.

---

## Classes

### `class _Transport`

**Purpose:** Implements `_Transport`.

#### `async def _Transport.fetch(self, request)`

**Purpose:** Implements `fetch`.

### `class StartpageParser`

**Purpose:** Implements `StartpageParser`.

#### `async def StartpageParser.build_request_async(transport, query, region, safesearch, timelimit, page) -> EngineRequest`

**Purpose:** Implements `build_request_async`.

#### `def StartpageParser.parse(self, document) -> EngineParseResult`

**Purpose:** Implements `parse`.

---

## Private functions

#### `def _to_text(value) -> str`

**Purpose:** Implements `_to_text`.

#### `def _between(text, start, end) -> str`

**Purpose:** Implements `_between`.

#### `async def _fetch_sc_code(transport) -> str`

**Purpose:** Implements `_fetch_sc_code`.

#### `async def _get_sc_code(transport) -> str`

**Purpose:** Implements `_get_sc_code`.

---

## Related

- [engines/_index](../../_index/)
