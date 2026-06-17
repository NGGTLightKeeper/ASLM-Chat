---
title: "mcp-server"
draft: false
---

## Module `mcp-server`

`Tools/mcp-web-search/mcp-server.py` — ASLM Chat Python module.

---

## Public functions

#### `def supports(engine, model_name) -> bool`

**Purpose:** Report whether this bridge supports the given engine/model pair.

#### `async def call_tool(tool_id, arguments, context) -> Any`

**Purpose:** Dispatch MCP tool calls to web_search or read_page services.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Await async I/O or subprocess work.
4. Iterate and transform or accumulate state.

---

## Private functions

#### `async def _call_serp_search(args) -> dict[str, Any]`

**Purpose:** Call the SERP API adapter for a raw structured search.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Await async I/O or subprocess work.

#### `async def _call_read_page(args) -> dict[str, Any]`

**Purpose:** Fetch one or many URLs as markdown and wrap them in the structured payload.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Iterate and transform or accumulate state.

#### `def _maybe_parse_list(val) -> Any`

**Purpose:** Parse JSON-encoded list strings passed as tool arguments.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Parse or serialize JSON payloads.

#### `def _source_domain(url) -> str`

**Purpose:** Normalize a URL host into a bare registrable domain label.

**Steps:**

1. Return the computed result to the caller.

#### `def _display_domain(domain) -> str`

**Purpose:** Build a short human-readable label from a domain name.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _favicon_url(domain) -> str`

**Purpose:** DuckDuckGo favicon URL for a source domain chip.

#### `def _read_page_source(url, rank, result_text) -> dict[str, object]`

**Purpose:** Build one read_page source metadata record for UI chips.

**Steps:**

1. Return the computed result to the caller.

#### `def _read_page_payload(urls, results) -> dict[str, object]`

**Purpose:** Assemble the structured read_page payload for one or many URLs.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Related

- [mcp-web-search/_index](../../_index/)
