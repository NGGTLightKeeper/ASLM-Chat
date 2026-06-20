---
title: "httpx_transport"
draft: false
---

## Module `httpx_transport`

`Tools/mcp-web-search/core/fetch/httpx_transport.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools/mcp-web-search/core/fetch`.

---

## Classes

### `class HttpxTransport`

**Purpose:** Implements `HttpxTransport`.

#### `def HttpxTransport.__init__(self, timeout_seconds) -> None`

**Purpose:** Implements `__init__`.

#### `async def HttpxTransport.fetch(self, request) -> TransportResponse`

**Purpose:** Implements `fetch`.

#### `async def HttpxTransport.close(self) -> None`

**Purpose:** Implements `close`.

---

## Private functions

#### `def _gsa_user_agent() -> str`

**Purpose:** Implements `_gsa_user_agent`.

#### `def _make_ssl_context() -> ...`

**Purpose:** Implements `_make_ssl_context`.

---

## Related

- [fetch/_index](../../_index/)
