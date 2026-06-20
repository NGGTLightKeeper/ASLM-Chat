---
title: "daemon"
draft: false
---

## Module `daemon`

`Tools/mcp-web-search/core/fetch/browser/daemon.py` — ASLM Chat Python module.

---

## Classes

### `class RecycleReason`

**Purpose:** Type `RecycleReason` defined in `daemon.py`.

### `class ScrapeResult`

**Purpose:** Type `ScrapeResult` defined in `daemon.py`.

### `class WarmChromium`

**Purpose:** Type `WarmChromium` defined in `daemon.py`.

### `class BrowserDaemon`

**Purpose:** Type `BrowserDaemon` defined in `daemon.py`.

---

## Public functions

#### `async def start(self) -> None`

**Purpose:** Start the warm browser daemon and bind it to the server.

#### `async def stop(self) -> None`

**Purpose:** Stop the warm browser daemon and close connections.

#### `async def handle_fetch(self, request) -> aiohttp.web.Response`

**Purpose:** Process a fetch request via the running chromium context.

#### `async def handle_health(self, request) -> aiohttp.web.Response`

**Purpose:** Return the current daemon health status.

#### `async def handle_shutdown(self, request) -> aiohttp.web.Response`

**Purpose:** Trigger the daemon to gracefully shut down.

#### `def make_app(self) -> aiohttp.web.Application`

**Purpose:** Create and return the aiohttp application for the daemon.

---

## Private functions

#### `def _parse_proxy() -> Any`

**Purpose:** Parse proxy configuration for the chromium context.

#### `def _process_tree_rss_mb() -> Any`

**Purpose:** Measure memory consumption of the browser process tree.

#### `def _parse_args() -> argparse.Namespace`

**Purpose:** Parse arguments and config overrides.

#### `async def _idle_monitor(self) -> None`

**Purpose:** Monitor idle state and recycle if needed.

---

## Related

- [browser/_index](../_index/)
