---
title: "search"
draft: false
---

## Module `search`

`Tools/mcp-web-search/core/fetch/onion/search.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools/mcp-web-search/core/fetch/onion`.

---

## Classes

### `class OnionResult`

**Purpose:** Implements `OnionResult`.

---

## Public functions

#### `async def onion_search(query: str, *, limit: int, per_link_timeout: float, max_chars: int, concurrency: int, providers: tuple[str, ...] | None) -> list[OnionResult]`

**Purpose:** Deep onion search: discover article URLs via the clearnet SERP, then scrape+compress the top results over Tor — discovery and scraping each parallel and per-link bounded. Returns BM25-compressed content records.

---

## Private functions

#### `def _anchor_host(url: str) -> str`

**Purpose:** Registrable host of a URL/anchor, www-stripped ("https://www.dw.com/en/" -> "dw.com").

#### `def _is_article_path(path: str) -> bool`

**Purpose:** Heuristic: does this path look like an article (vs nav/listing)? Generic across news sites: at least two segments, not a known listing root, and a date/id marker.

#### `def _resolve_providers(providers: tuple[str, ...] | None)`

**Purpose:** Names of the providers to search: explicit list (resolved to services) or, by default, every vetted service in a searchable category.

#### `async def _discover_for_service(svc, query: str, *, limit: int, serp_timeout: float) -> list[tuple[str, str]]`

**Purpose:** Discover article URLs for one service via the clearnet SERP, rewritten to its onion mirror. Returns (provider_name, onion_url) pairs. Clearnet-only (no Tor); soft-fails to [].

#### `async def _scrape_one(url: str, query: str, provider: str, *, timeout: float, max_chars: int)`

**Purpose:** Fetch one result page over Tor and return its BM25-compressed content (None on any failure).

#### `async def _warm_tor(budget: float) -> bool`

**Purpose:** Resolve the tor SOCKS once before the parallel scrapes (probes a running tor; we never spawn). Returns True if tor is usable. Runs the blocking probe in the io pool, bounded so it can't hang.

#### `def _round_robin(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]`

**Purpose:** Round-robin interleave (name, url) pairs across providers for source diversity.

---

## Related

- [onion/_index](../_index/)
