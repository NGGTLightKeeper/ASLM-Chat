---
title: "service"
draft: false
---

## Module `service`

`Tools/mcp-web-search/core/read/service.py` — see source for implementation details.

---

## Classes

### `class RawFetch`

**Purpose:** Outcome of one low-level HTTP fetch with the metadata needed for runtime profiling.

### `class ReadPageOptions`

**Purpose:** Data or behavior type.

### `class ReadPageService`

**Purpose:** Fetch a single URL and return clean markdown text via the custom-domain dispatch layer and a profile-driven generic pipeline. Caches extracted clean markdown instead of raw HTML for instant reuse.

---

## Public functions

#### `def RawFetch.attempt(parse_ms, quality, success) -> FetchAttempt`

**Purpose:** Build a FetchAttempt for the runtime profile store, folding in parse-time stats.

#### `def ReadPageService.__init__(options) -> None`

**Purpose:** Data or behavior type.

#### `async def ReadPageService.read(url) -> str`

**Purpose:** Public entry: fetch URL as markdown with a global deadline.

#### `async def run_read_page(url, timeout, max_chars, focus, allow_browser) -> str`

**Purpose:** Convenience entry point for the central API and debug CLI.

---

## Private functions

#### `async def ReadPageService._browser_ok() -> bool`

**Purpose:** Whether the warm browser path may run. Disabled by web_search so the browser stays exclusive to the read_page tool; otherwise gated on backend availability.

#### `def ReadPageService._apply_budget(markdown, url) -> str`

**Purpose:** Apply the read_page BM25 compression budget from config.

#### `def ReadPageService._context() -> FetchContext`

**Purpose:** Build the FetchContext handed to custom-domain handlers.

#### `def ReadPageService._resolve_strategy(url, req) -> tuple[bool, str | None, bool]`

**Purpose:** Pick the fetch strategy for a domain from hard overrides then runtime profiles.

#### `async def ReadPageService._fetch_candidate(url, browser_first, http_method) -> tuple[RawFetch, BrowserFetch | None]`

**Purpose:** Fetch one candidate URL with the chosen method (warm browser / single http / race).

#### `async def ReadPageService._generic_read(req) -> PageResult`

**Purpose:** Generic fetch+normalise pipeline shared by the default path and strategy handlers. Records every attempt into the runtime profile store so later reads skip dead ends.

#### `def ReadPageService._spa_recover(url, cres, prev_md, min_len) -> tuple[str, bool, str]`

**Purpose:** Recover the best markdown from a warm-browser SPA render: normalize → innerText → RSC.

#### `async def ReadPageService._read_pdf(url) -> PageResult`

**Purpose:** Download a PDF and return extracted markdown.

#### `async def ReadPageService._read_onion(url) -> PageResult`

**Purpose:** Fetch a .onion page over Tor and extract it through the same normalizer as the generic path.

#### `async def ReadPageService._read(url) -> str`

**Purpose:** Core read pipeline: SSRF, custom-domain dispatch, then the generic pipeline.

#### `def ReadPageService._finalize(url, result) -> str`

**Purpose:** Apply the compression budget when the result asks for it, then return markdown.

#### `def _host(url) -> str`

**Purpose:** Extract normalized host from URL (no www/m prefix).

#### `def _is_redirect_status(status_code) -> bool`

**Purpose:** True for HTTP redirect status codes.

#### `def _is_skippable(url) -> bool`

**Purpose:** True when read_page should not fetch HTML (non-text hosts/extensions).

#### `def _cache_key_for_read(url, variant) -> str`

**Purpose:** Cache key including strategy tag and variant label.

#### `def _variant_label(url) -> str`

**Purpose:** Label DNS-shop variant URLs for cache/trace.

#### `def _is_weak_extraction(markdown, min_length) -> bool`

**Purpose:** True when extracted markdown is too short or mostly boilerplate.

#### `def _fallback_text_to_markdown(url, text) -> str`

**Purpose:** Wrap already-extracted fallback text in minimal markdown headers.

#### `def _inner_text_to_markdown(url, inner_text) -> str`

**Purpose:** Convert raw DOM innerText to minimal markdown (SPA last resort).

#### `def _nextjs_rsc_to_markdown(url, raw_html) -> str`

**Purpose:** Extract Next.js RSC text and wrap as minimal markdown.

#### `async def _fetch_httpx(url, timeout, tls_verify) -> RawFetch`

**Purpose:** Fetch HTML via httpx with per-redirect SSRF checks; returns an instrumented RawFetch.

#### `async def _fetch_curl_cffi(url, timeout) -> RawFetch`

**Purpose:** curl_cffi HTML fetch with the same redirect-by-redirect SSRF checks.

#### `async def _fetch_race(url, timeout, tls_verify) -> RawFetch`

**Purpose:** Race httpx vs curl_cffi; first non-antibot response wins, loser is cancelled.

#### `async def _fetch_browser(url, timeout) -> tuple[RawFetch, BrowserFetch | None]`

**Purpose:** Run the warm browser within read_page's deadline and adapt the result into a RawFetch.

#### `async def _fetch_pdf_bytes(url, timeout, tls_verify) -> bytes`

**Purpose:** Fetch PDF bytes with SSRF checks and the MAX_PDF_BYTES ceiling (httpx, then curl_cffi).

#### `def _read_page_deadline(url, opts) -> float`

**Purpose:** Global asyncio deadline for one read; Reddit needs room for curl + browser render.
