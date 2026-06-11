---
title: "brave"
draft: false
---

## Module `brave`

`Tools/mcp-web-search/core/engines/brave.py` — ASLM Chat Python module.

---

## Classes

### `BraveParser`

**Purpose:** Brave Search SERP parser.

#### `def build_request(query, region, safesearch, timelimit, page) -> EngineRequest`

**Purpose:** Build the HTTP request for a Brave search query using a random browser profile.

**Steps:**

1. Return the computed result to the caller.

#### `def parse(self, document) -> EngineParseResult`

**Purpose:** Parse a raw Brave SERP HTML document into an EngineParseResult.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Related

- [engines/_index](../_index/)
