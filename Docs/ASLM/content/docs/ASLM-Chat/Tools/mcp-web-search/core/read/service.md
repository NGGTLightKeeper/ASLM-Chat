---
title: "service"
draft: false
---

## Module `service`

`Tools/mcp-web-search/core/read/service.py` — see source for implementation details.

---

## Classes

### `class ReadPageOptions`

**Purpose:** Data or behavior type `ReadPageOptions` in `read_page.py`.

### `class ReadPageVariantAttempt`

**Purpose:** Data or behavior type `ReadPageVariantAttempt` in `read_page.py`.

### `class ReadPageService`

**Purpose:** Data or behavior type `ReadPageService` in `read_page.py`.

---

## Public functions

#### `def ReadPageService.__init__(options) -> None`

**Purpose:** Implement `ReadPageService.__init__` as defined in `read_page.py`.

**Steps:**

1. Execute the implementation in the source module.

#### `async def ReadPageService.trace(url) -> list[ReadPageVariantAttempt]`

**Purpose:** Return per-variant trace for debugging (no user-facing read).

#### `async def ReadPageService.read_with_trace(url) -> tuple[str, list[ReadPageVariantAttempt]]`

**Purpose:** Like read() but also returns variant attempt trace.

#### `async def ReadPageService.read(url) -> str`

**Purpose:** Public entry: fetch URL as markdown with global deadline.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate over items and accumulate or transform state.

#### `async def run_read_page(url, timeout, max_chars, focus) -> str`

**Purpose:** Convenience entry point for MCP adapter and CLI.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.

---

## Private functions

#### `def _is_redirect_status(status_code) -> bool`

**Purpose:** True for HTTP redirect status codes.

#### `def _host(url) -> str`

**Purpose:** Extract normalized host from URL (no www/m prefix).

#### `def _is_youtube(url) -> bool`

**Purpose:** True for YouTube watch/short URLs.

#### `def _is_skippable(url) -> bool`

**Purpose:** True when read_page should not fetch HTML (non-text hosts/extensions).

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _cache_key_for_read(url, *, strategy_tag, variant=…) -> str`

**Purpose:** Cache key including strategy tag and DNS variant label.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _variant_label(url) -> str`

**Purpose:** Label DNS-shop variant URLs for cache/trace.

**Steps:**

1. Return the computed result to the caller.

#### `def _is_weak_extraction(markdown, *, min_length) -> bool`

**Purpose:** True when extracted markdown is too short or mostly boilerplate.

**Steps:**

1. Return the computed result to the caller.
2. Iterate over items and accumulate or transform state.

#### `def _apply_read_page_budget(markdown, *, url, focus, cfg, max_chars) -> str`

**Purpose:** Apply GLiNER/read_page compression budget from config.

**Steps:**

1. Return the computed result to the caller.

#### `def _fallback_text_to_markdown(url, text) -> str`

**Purpose:** Wrap already-extracted fallback text in minimal markdown headers.

**Steps:**

1. Return the computed result to the caller.

#### `def _inner_text_to_markdown(url, inner_text) -> str`

**Purpose:** Convert raw DOM innerText to minimal markdown (SPA last resort).

#### `def _nextjs_rsc_to_markdown(url, raw_html) -> str`

**Purpose:** Extract Next.js RSC text and wrap as minimal markdown.

**Steps:**

1. Return the computed result to the caller.

#### `def _youtube_video_id(url) -> str | None`

**Purpose:** Parse 11-char YouTube video id from URL.

#### `async def _fetch_youtube_transcript(url) -> str`

**Purpose:** Fetch YouTube transcript: youtube-transcript-api, then yt-dlp fallback.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate over items and accumulate or transform state.

#### `async def _fetch_httpx(url, timeout, tls_verify) -> str | None`

**Purpose:** Fetch HTML via httpx with per-redirect SSRF checks.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate over items and accumulate or transform state.

#### `async def _fetch_curl_cffi(url, timeout) -> str | None`

**Purpose:** curl_cffi HTML fetch with the same redirect-by-redirect SSRF checks.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate over items and accumulate or transform state.

#### `async def _fetch_pdf_bytes(url, timeout, tls_verify) -> bytes`

**Purpose:** Fetch PDF bytes with SSRF checks and MAX_PDF_BYTES ceiling.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate over items and accumulate or transform state.

#### `async def _read_pdf(url, timeout, tls_verify, max_chars) -> str`

**Purpose:** Download PDF and return markdown via pdf_bytes_to_markdown.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate over items and accumulate or transform state.

#### `async def _fetch_race(url, timeout, tls_verify) -> str | None`

**Purpose:** Race httpx vs curl_cffi; first non-antibot response wins.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate over items and accumulate or transform state.

#### `async def ReadPageService._fetch_camoufox_raw_html(url, opts) -> str | None`

**Purpose:** Fetch raw HTML through Camoufox within read_page's deadline.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Iterate over items and accumulate or transform state.

#### `async def ReadPageService._fetch_raw_html(url, opts, original_url) -> str | None`

**Purpose:** HTTP race or Camoufox depending on domain registry tier.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.

#### `async def ReadPageService._read(url, *, collect_attempts) -> tuple[str, list[ReadPageVariantAttempt]]`

**Purpose:** Core read pipeline: special hosts, variants, normalize, budget.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate over items and accumulate or transform state.

---

## Related

- [services/_index](_index/)
