---
title: "server"
draft: false
---

## Module `server`

`Tools/mcp-web-search/adapters/mcp/server.py` — ASLM Chat Python module.

---

## Classes

### `class SearchSourceOutput`

**Purpose:** Type `SearchSourceOutput` defined in `server.py`.

### `class SearchSourceChipOutput`

**Purpose:** Type `SearchSourceChipOutput` defined in `server.py`.

### `class SearchCompactUiOutput`

**Purpose:** Type `SearchCompactUiOutput` defined in `server.py`.

### `class SearchUiOutput`

**Purpose:** Type `SearchUiOutput` defined in `server.py`.

### `class SearchRichOutput`

**Purpose:** Type `SearchRichOutput` defined in `server.py`.

### `class ReadPageSourceOutput`

**Purpose:** Type `ReadPageSourceOutput` defined in `server.py`.

### `class ReadPageUiOutput`

**Purpose:** Type `ReadPageUiOutput` defined in `server.py`.

---

## Public functions

#### `async def web_search(query, effort, context) -> CallToolResult`

**Purpose:** FastMCP tool handler for ranked web search with structured UI output.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.

#### `async def read_page(url, focus, context) -> CallToolResult`

**Purpose:** FastMCP tool handler for single or batched page reads.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Iterate and transform or accumulate state.

---

## Private functions

#### `def _find_aslm_root() -> Path`

**Purpose:** Walk parent directories until ASLM project root markers are found.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `async def _keepalive(context, message, coro)`

**Purpose:** Send periodic MCP log pings while a long-running coroutine is in flight.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

#### `async def _report_progress(context, progress, total, message) -> None`

**Purpose:** Best-effort MCP progress notification when a live session context exists.

**Steps:**

1. Await async I/O or subprocess work.

#### `def _split_search_result_blocks(text) -> list[str]`

**Purpose:** Split numbered search result blocks from a single model_context string.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

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

- [mcp/_index](../../../../_index/)
