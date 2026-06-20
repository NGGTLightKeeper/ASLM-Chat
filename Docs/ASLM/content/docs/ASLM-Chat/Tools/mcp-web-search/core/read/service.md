---
title: "service"
draft: false
---

## Module `service`

`Tools/mcp-web-search/core/read/service.py` — ASLM Chat Python module.

---

## Classes

### `class RawFetch`

**Purpose:** Type `RawFetch` defined in `service.py`.

#### Public Methods

- `def attempt(*, parse_ms, quality, success) -> FetchAttempt`
  - **Purpose:** Execute attempt logic.

### `class ReadPageOptions`

**Purpose:** Options configuration for the read page service.

### `class ReadPageService`

**Purpose:** Service responsible for orchestrating page reads and handling fallback logic.

#### Public Methods

- `def read(url) -> str`
  - **Purpose:** Execute read logic.

#### Private Methods

- `def _browser_ok() -> bool`
  - **Purpose:** Execute _browser_ok logic.
- `def _apply_budget(markdown, url) -> str`
  - **Purpose:** Execute _apply_budget logic.
- `def _context() -> FetchContext`
  - **Purpose:** Execute _context logic.
- `def _resolve_strategy(url, req) -> tuple[bool, str | None, bool]`
  - **Purpose:** Execute _resolve_strategy logic.
- `def _fetch_candidate(url, *, camoufox_first, http_method) -> tuple[RawFetch, FetchResult | None]`
  - **Purpose:** Execute _fetch_candidate logic.
- `def _generic_read(req) -> PageResult`
  - **Purpose:** Execute _generic_read logic.
- `def _spa_recover(url, cres, prev_md, min_len) -> tuple[str, bool, str]`
  - **Purpose:** Execute _spa_recover logic.
- `def _read_pdf(url) -> PageResult`
  - **Purpose:** Execute _read_pdf logic.
- `def _read(url) -> str`
  - **Purpose:** Execute _read logic.
- `def _finalize(url, result) -> str`
  - **Purpose:** Execute _finalize logic.

---

## Public functions

#### `def run_read_page(url, timeout, max_chars, focus, allow_browser) -> str`

**Purpose:** Executes reading a page utilizing Camoufox or HTTPX as determined by allow_browser.

---

## Private functions

#### `def _host(url) -> str`

**Purpose:** Execute _host logic.

#### `def _is_redirect_status(status_code) -> bool`

**Purpose:** Execute _is_redirect_status logic.

#### `def _is_skippable(url) -> bool`

**Purpose:** Execute _is_skippable logic.

#### `def _cache_key_for_read(url, *, variant) -> str`

**Purpose:** Execute _cache_key_for_read logic.

#### `def _variant_label(url) -> str`

**Purpose:** Execute _variant_label logic.

#### `def _is_weak_extraction(markdown, *, min_length) -> bool`

**Purpose:** Execute _is_weak_extraction logic.

#### `def _fallback_text_to_markdown(url, text) -> str`

**Purpose:** Execute _fallback_text_to_markdown logic.

#### `def _inner_text_to_markdown(url, inner_text) -> str`

**Purpose:** Execute _inner_text_to_markdown logic.

#### `def _nextjs_rsc_to_markdown(url, raw_html) -> str`

**Purpose:** Execute _nextjs_rsc_to_markdown logic.

#### `def _fetch_httpx(url, timeout, tls_verify) -> RawFetch`

**Purpose:** Execute _fetch_httpx logic.

#### `def _fetch_curl_cffi(url, timeout) -> RawFetch`

**Purpose:** Execute _fetch_curl_cffi logic.

#### `def _fetch_race(url, timeout, tls_verify) -> RawFetch`

**Purpose:** Execute _fetch_race logic.

#### `def _fetch_camoufox(url, timeout) -> tuple[RawFetch, FetchResult | None]`

**Purpose:** Execute _fetch_camoufox logic.

#### `def _fetch_pdf_bytes(url, timeout, tls_verify) -> bytes`

**Purpose:** Execute _fetch_pdf_bytes logic.

#### `def _read_page_deadline(url, opts) -> float`

**Purpose:** Execute _read_page_deadline logic.

---

## Related

- [_index](../_index/)
