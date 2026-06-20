---
title: "transport"
draft: false
---

## Module `transport`

`Tools/mcp-web-search/core/fetch/transport.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools/mcp-web-search/core/fetch`.

---

## Classes

### `class AiohttpTransport`

**Purpose:** Implements `AiohttpTransport`.

#### `def AiohttpTransport.__init__(self, timeout_seconds, connection_limit) -> None`

**Purpose:** Implements `__init__`.

#### `async def AiohttpTransport.start(self) -> None`

**Purpose:** Implements `start`.

#### `async def AiohttpTransport.close(self) -> None`

**Purpose:** Implements `close`.

#### `async def AiohttpTransport.fetch(self, request) -> TransportResponse`

**Purpose:** Implements `fetch`.

### `class PrimpTransport`

**Purpose:** Implements `PrimpTransport`.

#### `def PrimpTransport.__init__(self, timeout_seconds, max_workers) -> None`

**Purpose:** Implements `__init__`.

#### `def PrimpTransport._client(self, host, primp_target, primp_os) -> ...`

**Purpose:** Implements `_client`.

#### `def PrimpTransport._fetch_sync(self, request) -> TransportResponse`

**Purpose:** Implements `_fetch_sync`.

#### `async def PrimpTransport.fetch(self, request) -> TransportResponse`

**Purpose:** Implements `fetch`.

#### `async def PrimpTransport.close(self) -> None`

**Purpose:** Implements `close`.

### `class AdaptiveTransport`

**Purpose:** Implements `AdaptiveTransport`.

#### `def AdaptiveTransport.__init__(self, timeout_seconds) -> None`

**Purpose:** Implements `__init__`.

#### `async def AdaptiveTransport.fetch(self, request) -> TransportResponse`

**Purpose:** Implements `fetch`.

#### `async def AdaptiveTransport.close(self) -> None`

**Purpose:** Implements `close`.

---

## Private functions

#### `def _replay_identity_cookies(request, host) -> EngineRequest`

**Purpose:** Implements `_replay_identity_cookies`.

#### `def _capture_identity_cookies(request, host, response) -> None`

**Purpose:** Implements `_capture_identity_cookies`.

#### `def _primp_set_cookie(response) -> list[...]`

**Purpose:** Implements `_primp_set_cookie`.

---

## Related

- [fetch/_index](../../_index/)
