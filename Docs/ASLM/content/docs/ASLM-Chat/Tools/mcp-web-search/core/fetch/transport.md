---
title: "transport"
draft: false
---

## Module `transport`

`Tools/mcp-web-search/core/fetch/transport.py` — ASLM Chat Python module.

---

## Classes

### `class AiohttpTransport`

**Purpose:** One pooled aiohttp session shared by all engine requests.

### `class PrimpTransport`

**Purpose:** Bounded browser-impersonating transport for engines that reject generic TLS clients.

### `class AdaptiveTransport`

**Purpose:** Route each engine to one known transport without retry chains.

---

## Public functions

#### `def AiohttpTransport.__init__(*, timeout_seconds=…, connection_limit=…) -> None`

**Purpose:** Initialize timeout and connection pool settings without opening a session yet.

#### `async def AiohttpTransport.start() -> None`

**Purpose:** Open a new aiohttp session if one is not already active.

#### `async def AiohttpTransport.close() -> None`

**Purpose:** Close and discard the active aiohttp session.

#### `async def AiohttpTransport.fetch(request) -> TransportResponse`

**Purpose:** Send one HTTP request and return the raw response.

#### `def PrimpTransport.__init__(*, timeout_seconds=…, max_workers=…) -> None`

**Purpose:** Initialize timeout and a thread-pool executor for blocking primp calls.

#### `async def PrimpTransport.fetch(request) -> TransportResponse`

**Purpose:** Run the blocking primp fetch on the thread-pool executor.

#### `async def PrimpTransport.close() -> None`

**Purpose:** Release all cached clients and shut down the executor.

#### `def AdaptiveTransport.__init__(*, timeout_seconds=…) -> None`

**Purpose:** Initialize all transports: fast aiohttp for DDG, primp for Brave, httpx for Google.

#### `async def AdaptiveTransport.fetch(request) -> TransportResponse`

**Purpose:** Forward the request to the appropriate transport based on the target host.

#### `async def AdaptiveTransport.close() -> None`

**Purpose:** Close all underlying transports.

---

## Private functions

#### `def PrimpTransport._client(host, primp_target, primp_os) -> primp.Client`

**Purpose:** Return or create a primp client keyed by host+impersonation identity.

#### `def PrimpTransport._fetch_sync(request) -> TransportResponse`

**Purpose:** Execute one HTTP request synchronously using the matching primp client. Includes cookies in the request headers if present.

---

## Related

- [fetch/_index](../../../../_index/)
