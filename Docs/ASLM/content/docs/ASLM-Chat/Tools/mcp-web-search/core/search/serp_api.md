---
title: "serp_api"
draft: false
---

## Module `serp_api`

`Tools/mcp-web-search/core/search/serp_api.py` — ASLM Chat Python module.

---

## Classes

### `SerpTransport(Protocol)`

**Purpose:** Protocol for transport backends accepted by SerpApi.

#### `async def fetch(self, request) -> TransportResponse`

**Steps:**

1. Await async I/O or subprocess work.

#### `async def close(self) -> None`

**Steps:**

1. Await async I/O or subprocess work.

### `SerpApi`

**Purpose:** Run general-purpose engines concurrently through one pooled transport.

#### `def __init__(self, transport, timeout_seconds, source_limit) -> None`

**Purpose:** Initialize the API with an optional pre-built transport and search limits.

#### `async def close(self) -> None`

**Purpose:** Close the owned transport if this instance created it.

**Steps:**

1. Await async I/O or subprocess work.

#### `async def __aenter__(self) -> "SerpApi"`

**Purpose:** Support async context manager entry.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.

#### `async def __aexit__(self, *_args) -> None`

**Purpose:** Close resources on async context manager exit.

**Steps:**

1. Await async I/O or subprocess work.

#### `async def search_stream(self, query, region, safesearch, timelimit, deadline_seconds) -> AsyncIterator[dict[str, Any]]`

**Purpose:** Stream sources and per-engine status events through a short-lived in-process buffer as each engine completes, yielding them in real time.

**Steps:**

1. Initialize or construct object instances.
2. Delegate work to an inner closure or thread.

#### `async def search(self, query, region, safesearch, timelimit) -> dict[str, Any]`

**Purpose:** Run all engines and return the combined result dict by draining the stream.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Iterate and transform or accumulate state.

---

## Public functions

#### `def encode_json(payload) -> bytes`

**Purpose:** Serialize a payload to indented JSON bytes using orjson.

**Steps:**

1. Return the computed result to the caller.

#### `async def run_serp_search(query, region, safesearch, timelimit, timeout_seconds, source_limit) -> dict[str, Any]`

**Purpose:** Convenience wrapper that reuses the shared transport for a single search.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Initialize or construct object instances.

---

## Private functions

#### `def _host_of(url) -> str`

**Purpose:** Return the lowercased host of a URL, or an empty string.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _error_parse_result(engine, message) -> EngineParseResult`

**Purpose:** Build an error EngineParseResult with a single diagnostic message.

**Steps:**

1. Return the computed result to the caller.

#### `def _parse_result_payload(result, limit, http_status, fetch_ms, parse_ms, response_bytes, transport) -> dict[str, Any]`

**Purpose:** Serialize one engine parse result into the final payload dict.

**Steps:**

1. Return the computed result to the caller.

#### `async def _run_engine(self, parser_type, query, region, safesearch, timelimit) -> dict[str, Any]`

**Purpose:** Fetch one engine, parse its response, and return the serialized result dict.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Await async I/O or subprocess work.
4. Initialize or construct object instances.

#### `def _get_transport(timeout_seconds) -> AdaptiveTransport`

**Steps:**

1. Return the computed result to the caller.

---

## Related

- [search/_index](../_index/)
