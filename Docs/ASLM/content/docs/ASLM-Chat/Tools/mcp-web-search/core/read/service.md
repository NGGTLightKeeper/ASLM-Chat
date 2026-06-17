---
title: "service"
draft: false
---

## Module `service`

`Tools/mcp-web-search/core/read/service.py` — ASLM Chat Python module.

---

## Classes

#### `class RawFetch`

**Method:** `def attempt(parse_ms, quality, success) -> FetchAttempt`

#### `class ReadPageOptions`

#### `class ReadPageService`

**Method:** `async def read(url) -> str`

---

## Public functions

#### `async def run_read_page(url, timeout, max_chars, focus, allow_browser) -> str`

---

## Private functions

#### `def _host(url) -> str`

#### `def _is_redirect_status(status_code) -> bool`

#### `def _is_skippable(url) -> bool`

#### `def _cache_key_for_read(url, variant) -> str`

#### `def _variant_label(url) -> str`

#### `def _is_weak_extraction(markdown, min_length) -> bool`

#### `def _fallback_text_to_markdown(url, text) -> str`

#### `def _inner_text_to_markdown(url, inner_text) -> str`

#### `def _nextjs_rsc_to_markdown(url, raw_html) -> str`

#### `async def _fetch_httpx(url, timeout, tls_verify) -> RawFetch`

#### `async def _fetch_curl_cffi(url, timeout) -> RawFetch`

#### `async def _fetch_race(url, timeout, tls_verify) -> RawFetch`

#### `async def _fetch_browser(url, timeout) -> tuple[RawFetch, BrowserFetch | None]`

#### `async def _fetch_pdf_bytes(url, timeout, tls_verify) -> bytes`

#### `def _read_page_deadline(url, opts) -> float`

---

## Related

- [service/_index](../../_index/)
