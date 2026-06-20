---
title: "hosted_providers"
draft: false
---

## Module `hosted_providers`

`Tools/mcp-web-search/core/search/hosted_providers.py` — ASLM Chat Python module.

---

## Overview

Hosted search-API clients (optional supplement layer).

Ported from the legacy `core/fetch/hosted_clients.py` and rebuilt async-first on httpx
(the new stack's HTTP client) instead of sync `requests` in a thread pool. Every client
exposes the same Tavily-style shape — `search() -> list[HostedResult]` — where
content-bearing providers (Tavily advanced, Firecrawl) carry the full page text in
`HostedResult.content`. That text is pre-populated into SourceCache by `hosted_stream`
so the shared read_page extraction/compaction pipeline runs on it without a re-fetch.

`provider_family` drives consensus voting: SerpApi serves Google's index, so it votes
with the Google scrape parser; Tavily/Firecrawl/Brave are their own families.

---

## Classes

### `class HostedResult`

**Purpose:** Type `HostedResult` defined in `hosted_providers.py`.

### `class HostedProvider`

**Purpose:** Type `HostedProvider` defined in `hosted_providers.py`.

#### `def HostedProvider.key(keys)`

**Purpose:** Implements `HostedProvider.key` in `hosted_providers.py`.

#### `def HostedProvider.search(client, query)`

**Purpose:** Implements `HostedProvider.search` in `hosted_providers.py`.

### `class TavilyClient`

**Purpose:** Type `TavilyClient` defined in `hosted_providers.py`.

#### `def TavilyClient.key(keys)`

**Purpose:** Implements `TavilyClient.key` in `hosted_providers.py`.

#### `def TavilyClient.search(client, query)`

**Purpose:** Implements `TavilyClient.search` in `hosted_providers.py`.

### `class FirecrawlClient`

**Purpose:** Type `FirecrawlClient` defined in `hosted_providers.py`.

#### `def FirecrawlClient.key(keys)`

**Purpose:** Implements `FirecrawlClient.key` in `hosted_providers.py`.

#### `def FirecrawlClient.search(client, query)`

**Purpose:** Implements `FirecrawlClient.search` in `hosted_providers.py`.

### `class BraveClient`

**Purpose:** Type `BraveClient` defined in `hosted_providers.py`.

#### `def BraveClient.key(keys)`

**Purpose:** Implements `BraveClient.key` in `hosted_providers.py`.

#### `def BraveClient.search(client, query)`

**Purpose:** Implements `BraveClient.search` in `hosted_providers.py`.

### `class SerpApiClient`

**Purpose:** Type `SerpApiClient` defined in `hosted_providers.py`.

#### `def SerpApiClient.key(keys)`

**Purpose:** Implements `SerpApiClient.key` in `hosted_providers.py`.

#### `def SerpApiClient.search(client, query)`

**Purpose:** Implements `SerpApiClient.search` in `hosted_providers.py`.

---

## Public functions

#### `def sanitize_query_for_api(query) -> str`

**Purpose:** Implements `sanitize_query_for_api` in `hosted_providers.py`.

#### `def available_providers()`

**Purpose:** Implements `available_providers` in `hosted_providers.py`.

---

## Private functions

#### `def _post_json(client, url)`

**Purpose:** Implements `_post_json` in `hosted_providers.py`.

#### `def _get_json(client, url)`

**Purpose:** Implements `_get_json` in `hosted_providers.py`.

---

## Related

- [core](../../_index/)
