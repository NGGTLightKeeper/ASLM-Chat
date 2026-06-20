---
title: "daemon"
draft: false
---

## Module `daemon`

`Tools/mcp-web-search/core/fetch/browser/daemon.py` — ASLM Chat Python module.

---

## Overview

Persistent, supervised warm-browser daemon (chromium / cloakbrowser only).

---

## Classes

### `class RecycleReason`

**Purpose:** Why the warm browser was torn down — drives whether identity is restored or rotated.

### `class ScrapeResult`

**Purpose:** Type `ScrapeResult` defined in `daemon.py`.

### `class WarmChromium`

**Purpose:** One warm Chromium with its identity context, recycle policy and checkpoint discipline.

### `class BrowserDaemon`

**Purpose:** Type `BrowserDaemon` defined in `daemon.py`.

---

## Public functions

#### `def WarmChromium.__init__(self) -> None`

**Purpose:** Implements `WarmChromium.__init__` in `daemon.py`.

#### `async def WarmChromium.fetch(self, url) -> ScrapeResult`

**Purpose:** Fetch one URL through the warm browser, recycling first if a threshold was crossed.

#### `async def WarmChromium.start(self) -> None`

**Purpose:** Eagerly warm the browser and start the idle-checkpoint loop.

#### `async def WarmChromium.stop(self) -> None`

**Purpose:** Final checkpoint, stop the loop, tear the browser down.

#### `def WarmChromium.health(self) -> dict[str, Any]`

**Purpose:** Runtime snapshot for /health.

#### `def BrowserDaemon.__init__(self, args) -> None`

**Purpose:** Implements `BrowserDaemon.__init__` in `daemon.py`.

#### `async def BrowserDaemon.start(self) -> None`

**Purpose:** Implements `BrowserDaemon.start` in `daemon.py`.

#### `async def BrowserDaemon.stop(self) -> None`

**Purpose:** Implements `BrowserDaemon.stop` in `daemon.py`.

#### `async def BrowserDaemon.handle_fetch(self, request) -> web.Response`

**Purpose:** POST /fetch {url, wait_ms?, timeout_ms?, html?} -> ScrapeResult json.

#### `async def BrowserDaemon.handle_health(self, _request) -> web.Response`

**Purpose:** Implements `BrowserDaemon.handle_health` in `daemon.py`.

#### `async def BrowserDaemon.handle_shutdown(self, _request) -> web.Response`

**Purpose:** Implements `BrowserDaemon.handle_shutdown` in `daemon.py`.

#### `def BrowserDaemon.make_app(self) -> web.Application`

**Purpose:** Implements `BrowserDaemon.make_app` in `daemon.py`.

---

## Related

- [browser/_index](../_index/)
