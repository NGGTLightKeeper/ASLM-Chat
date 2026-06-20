---
title: "serp_api"
draft: false
---

## Module `serp_api`

`Tools/mcp-web-search/core/search/serp_api.py` — ASLM Chat Python module.

---

## Classes

### `class SerpTransport`

**Purpose:** Type `SerpTransport` defined in `serp_api.py`.

**Methods:**

- `fetch`
- `close`

### `class SerpApi`

**Purpose:** Type `SerpApi` defined in `serp_api.py`.

**Methods:**

- `__init__`
- `close`
- `__aenter__`
- `__aexit__`
- `_run_engine`
- `search_stream`
- `search`

---

## Public functions

#### `def encode_json(payload)`

**Purpose:** Implements encode_json

**Steps:**

1. Return the computed result to the caller.

#### `async def run_serp_search(query)`

**Purpose:** Implements run_serp_search

**Steps:**

1. Return the computed result to the caller.

---

## Private functions

#### `async def _build_engine_request(parser, transport, query)`

**Purpose:** Implements _build_engine_request

**Steps:**

1. Return the computed result to the caller.

#### `def _host_of(url)`

**Purpose:** Implements _host_of

**Steps:**

1. Return the computed result to the caller.

#### `def _error_parse_result(engine, message)`

**Purpose:** Implements _error_parse_result

**Steps:**

1. Return the computed result to the caller.

#### `def _parse_result_payload(result)`

**Purpose:** Implements _parse_result_payload

**Steps:**

1. Return the computed result to the caller.

#### `def _get_transport(timeout_seconds)`

**Purpose:** Implements _get_transport

**Steps:**

1. Return the computed result to the caller.

---

## Related

- [search/_index](../../../../_index/)
