---
title: "hosted_stream"
draft: false
---

## Module `hosted_stream`

`Tools/mcp-web-search/core/search/hosted_stream.py` — ASLM Chat Python module.

---

## Overview

Hosted providers as a merged, real-time supplement stream.

Emits the exact event shape of `serp_api.search_stream` ({"type": "source"|"vote"
|"engine"}), so `web_search` consumes scrape and hosted sources through one triage with
no special-casing. As content-bearing providers (Tavily, Firecrawl) return, their full
page text is pre-populated into SourceCache under the read_page cache key BEFORE the
source event is emitted — so when the orchestrator later parses that URL, read_page gets
a cache hit and runs the normal extraction/compaction pipeline with no network fetch.

Hosted is strictly a supplement: with no API keys configured it yields nothing and the
search stays pure scrape.

---

## Public functions

#### `def hosted_search_stream(query)`

**Purpose:** Implements `hosted_search_stream` in `hosted_stream.py`.

---

## Private functions

#### `def _host_of(url) -> str`

**Purpose:** Implements `_host_of` in `hosted_stream.py`.

#### `def _wrap_as_html(text) -> str`

**Purpose:** Implements `_wrap_as_html` in `hosted_stream.py`.

#### `def _prepopulate_cache(results) -> int`

**Purpose:** Implements `_prepopulate_cache` in `hosted_stream.py`.

#### `def _engine_payload(provider_name, family, results, fetch_ms)`

**Purpose:** Implements `_engine_payload` in `hosted_stream.py`.

---

## Related

- [core](../../_index/)
