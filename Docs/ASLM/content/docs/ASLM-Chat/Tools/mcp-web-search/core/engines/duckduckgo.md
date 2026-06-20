---
title: "duckduckgo"
draft: false
---

## Module `duckduckgo`

`Tools/mcp-web-search/core/engines/duckduckgo.py` — ASLM Chat Python module.

---

## Classes

### `DuckDuckGoParser`

**Purpose:** DuckDuckGo HTML SERP parser.

#### `def build_request(query, region, safesearch, timelimit, page) -> EngineRequest`

**Purpose:** Build the HTTP request for a DuckDuckGo search query using a random browser profile.

**Steps:**

1. Return the computed result to the caller.

#### `def parse(self, document) -> EngineParseResult`

**Purpose:** Parse a raw DuckDuckGo SERP HTML document into an EngineParseResult.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Private functions

#### `def _unwrap_url(value) -> str`

**Purpose:** Unwrap a DuckDuckGo redirect URL to the actual destination URL.

**Steps:**

1. Return the computed result to the caller.

---

## Related

- [engines/_index](../_index/)
