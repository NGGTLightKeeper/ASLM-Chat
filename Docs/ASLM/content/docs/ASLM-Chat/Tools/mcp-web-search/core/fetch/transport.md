---
title: "transport"
draft: false
---

## Module `transport`

`Tools/mcp-web-search/core/fetch/transport.py` — ASLM Chat Python module.

---

## Classes

### `AiohttpTransport`

**Purpose:** One pooled aiohttp session shared by all engine requests.

#### `def __init__(self, timeout_seconds, connection_limit) -> None`

**Purpose:** Initialize timeout and connection pool settings without opening a session yet.

#### `async def start(self) -> None`

**Purpose:** Open a new aiohttp session if one is not already active.

**Steps:**

1. Return the computed result to the caller.

#### `async def close(self) -> None`

**Purpose:** Close and discard the active aiohttp session.

#### `async def fetch(self, request) -> TransportResponse`

**Purpose:** Send one HTTP request and return the raw response.

**Steps:**

1. Return the computed result to the caller.

### `PrimpTransport`

**Purpose:** Bounded browser-impersonating transport for engines that reject generic TLS clients.

#### `def __init__(self, timeout_seconds, max_workers) -> None`

**Purpose:** Initialize timeout and a thread-pool executor for blocking primp calls.

#### `async def fetch(self, request) -> TransportResponse`

**Purpose:** Run the blocking primp fetch on the thread-pool executor.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.

#### `async def close(self) -> None`

**Purpose:** Release all cached clients and shut down the executor.

### `AdaptiveTransport`

**Purpose:** Route each engine to one known transport without retry chains.

#### `def __init__(self, timeout_seconds) -> None`

**Purpose:** Initialize all transports: fast aiohttp for DDG, primp for Brave, httpx for Google.

#### `async def fetch(self, request) -> TransportResponse`

**Purpose:** Forward the request to the appropriate transport based on the target host.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.

#### `async def close(self) -> None`

**Purpose:** Close all underlying transports.

**Steps:**

1. Await async I/O or subprocess work.

---

## Private functions

#### `def _client(self, host, primp_target, primp_os) -> primp.Client`

**Purpose:** Return or create a primp client keyed by host+impersonation identity.

**Steps:**

1. Return the computed result to the caller.

#### `def _fetch_sync(self, request) -> TransportResponse`

**Purpose:** Execute one HTTP request synchronously using the matching primp client.

**Steps:**

1. Return the computed result to the caller.

---

## Related

- [fetch/_index](../_index/)
