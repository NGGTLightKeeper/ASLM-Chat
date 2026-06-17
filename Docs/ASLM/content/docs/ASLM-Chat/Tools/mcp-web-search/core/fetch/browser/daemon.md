---
title: "daemon"
draft: false
---

## Module `daemon`

`Tools/mcp-web-search/core/fetch/browser/daemon.py` — ASLM Chat Python module.

---

## Classes

#### `class RecycleReason`

#### `class ScrapeResult`

#### `class WarmChromium`

**Method:** `async def fetch(url, wait, nav_timeout) -> ScrapeResult`

**Method:** `async def start() -> None`

**Method:** `async def stop() -> None`

**Method:** `def health() -> dict[str, Any]`

#### `class BrowserDaemon`

**Method:** `async def start() -> None`

**Method:** `async def stop() -> None`

**Method:** `async def handle_fetch(request) -> web.Response`

**Method:** `async def handle_health(_request) -> web.Response`

**Method:** `async def handle_shutdown(_request) -> web.Response`

**Method:** `def make_app() -> web.Application`

---

## Private functions

#### `def _parse_proxy(proxy_url) -> Optional[str]`

#### `def _process_tree_rss_mb() -> float`

#### `async def _serve(args) -> None`

#### `def _parse_args() -> argparse.Namespace`

---

## Related

- [daemon/_index](../../_index/)
