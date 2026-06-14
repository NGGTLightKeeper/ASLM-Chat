---
title: "startpage"
draft: false
---

## Module `startpage`

`Tools/mcp-web-search/core/engines/startpage.py` — ASLM Chat Python module for parsing and interacting with Startpage search engine.

---

## Constants and Cache

- `_SC_TTL`: Time-to-live for the cached search token.
- `_SC_RETRY_COOLDOWN`: Cooldown duration after a failed scrape attempt (cold or blocked homepage) before retrying, preventing serialization of fresh homepage fetches under the global lock when blocked.
- `_SC_LOCK`: Global async lock to prevent stampedes when refreshing the cache.

---

## Core Flow

1. **`_fetch_sc_code`**: Scrapes the initial Startpage homepage to extract the required anti-bot `sc` token stamp from the form.
2. **`_get_sc_code`**: Returns a cached `sc` token, refreshing it through the transport when stale. Applies an exponential backoff / retry cooldown (`_SC_RETRY_COOLDOWN` via `_sc_failed_at`) to reuse stale/empty tokens during temporary scraping blocks instead of hammering the homepage on every search attempt.

---

## Related

- [engines/_index](../../../_index/)
