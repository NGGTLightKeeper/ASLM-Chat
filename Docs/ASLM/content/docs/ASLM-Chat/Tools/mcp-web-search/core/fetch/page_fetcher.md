---
title: "page_fetcher"
draft: false
---

## Module `page_fetcher`

`Tools/mcp-web-search/core/fetch/page_fetcher.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools\mcp-web-search\core\fetch`. See **Related** for package index and callers.

---

## Classes

### `class _DomainThrottle`

**Purpose:** Type `_DomainThrottle` defined in `page_fetcher.py`.

### `class PageFetcher`

**Purpose:** Type `PageFetcher` defined in `page_fetcher.py`.

---

## Public functions

#### `def is_skippable(url) -> bool`

**Purpose:** Return True for URLs that cannot be usefully scraped as text.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _DomainThrottle.__init__(rps) -> None`

**Purpose:** min_interval derived from requests-per-second cap.

#### `async def _DomainThrottle.acquire(domain) -> None`

**Purpose:** Sleep until the domain is allowed another request.

**Steps:**

1. Await async I/O or subprocess work.

#### `def PageFetcher.__init__(cache, max_concurrent, per_domain_rps, timeout, store_raw_html, tls_verify) -> None`

**Purpose:** Configure cache, concurrency, per-domain throttle, and TLS policy.

#### `async def PageFetcher.fetch_and_cache(urls, budget) -> dict[str, CachedPage | None]`

**Purpose:** Fetch up to budget URLs; skip URLs already fresh in cache.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

---

## Private functions

#### `def _is_redirect_status(status_code) -> bool`

**Purpose:** True for HTTP redirect status codes we follow manually.

#### `async def PageFetcher._fetch_httpx(url) -> tuple[str, int]`

**Purpose:** httpx GET with per-redirect SSRF validation.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Iterate and transform or accumulate state.

#### `async def PageFetcher._fetch_pdf_httpx(url, max_bytes) -> tuple[bytes, int]`

**Purpose:** httpx streaming PDF download with redirect checks.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `async def PageFetcher._fetch_curl_cffi(url) -> tuple[str, int]`

**Purpose:** curl_cffi fallback with SSRF checks on each redirect.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Iterate and transform or accumulate state.

#### `async def PageFetcher._fetch_pdf_curl_cffi(url, max_bytes) -> tuple[bytes, int]`

**Purpose:** curl_cffi PDF fallback with redirect checks.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Iterate and transform or accumulate state.

#### `async def PageFetcher._fetch_single(url) -> tuple[str, int]`

**Purpose:** Try httpx, then curl_cffi; returns (raw_html, status_code).

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

#### `async def PageFetcher._fetch_pdf_bytes(url) -> bytes`

**Purpose:** Fetch PDF bytes bounded by MAX_PDF_BYTES.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

#### `async def PageFetcher._fetch_pdf_normalize_cache(url) -> CachedPage | None`

**Purpose:** Download PDF, extract markdown, cache.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

#### `async def PageFetcher._fetch_normalize_cache(url) -> CachedPage | None`

**Purpose:** Fetch one URL, normalize, and store in cache.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

---

## Related

- [fetch/_index](../../../../_index/)
