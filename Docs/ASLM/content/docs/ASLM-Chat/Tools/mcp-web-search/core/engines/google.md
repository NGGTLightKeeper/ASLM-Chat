---
title: "google"
draft: false
---

## Module `google`

`Tools/mcp-web-search/core/engines/google.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools/mcp-web-search/core/engines`.

---

## Classes

### `class GoogleParser`

**Purpose:** Implements `GoogleParser`.

#### `def GoogleParser.build_request(query, region, safesearch, timelimit, page) -> EngineRequest`

**Purpose:** Implements `build_request`.

#### `def GoogleParser.parse(self, document) -> EngineParseResult`

**Purpose:** Implements `parse`.

---

## Private functions

#### `def _gsa_user_agent() -> str`

**Purpose:** Implements `_gsa_user_agent`.

#### `def _unwrap_url(value) -> str`

**Purpose:** Implements `_unwrap_url`.

#### `def _is_internal(value) -> bool`

**Purpose:** Implements `_is_internal`.

---

## Related

- [engines/_index](../../_index/)
