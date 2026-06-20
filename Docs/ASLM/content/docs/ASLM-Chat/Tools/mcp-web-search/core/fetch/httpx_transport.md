---
title: "httpx_transport"
draft: false
---

## Module `httpx_transport`

`Tools/mcp-web-search/core/fetch/httpx_transport.py` — ASLM Chat Python module.

---

## Classes

### `HttpxTransport`

**Purpose:** Async httpx transport with per-request TLS fingerprint randomisation.

#### `def __init__(self, timeout_seconds) -> None`

**Purpose:** Build the transport.

#### `async def fetch(self, request) -> TransportResponse`

**Purpose:** Send the request as a legacy GSA mobile client.

**Steps:**

1. Return the computed result to the caller.

#### `async def close(self) -> None`

**Purpose:** No persistent client to close.

---

## Private functions

#### `def _gsa_user_agent() -> str`

**Purpose:** Build a randomised GSA-style User-Agent with a legacy Chrome 39 engine.

**Steps:**

1. Return the computed result to the caller.

#### `def _make_ssl_context() -> ssl.SSLContext`

**Purpose:** Build an SSL context whose cipher list is randomised per-instance.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Related

- [fetch/_index](../_index/)
