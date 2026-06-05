---
title: "academic_fetcher"
draft: false
---

## Module `academic_fetcher`

`Tools/mcp-web-search/core/fetch/academic_fetcher.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools\mcp-web-search\core\fetch`. See **Related** for package index and callers.

---

## Classes

### `class AcademicFetcher`

**Purpose:** Type `AcademicFetcher` defined in `academic_fetcher.py`.

---

## Public functions

#### `def AcademicFetcher.__init__(timeout)`

**Purpose:** Load registry and set HTTP timeout.

#### `async def AcademicFetcher.search(query, target_domains, max_results) -> list[SearchResult]`

**Purpose:** Search matching registry engines in parallel.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

#### `async def AcademicFetcher.search_fast(query, *, max_results=…, topics=…) -> list[SearchResult]`

**Purpose:** Fast path: only lightweight friendly engines.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Iterate and transform or accumulate state.

---

## Private functions

#### `def _normalize_pdf_url(url) -> str`

**Purpose:** Keep only URLs that look like PDFs.

#### `def _arxiv_pdf_url(url) -> str`

**Purpose:** Derive arxiv PDF URL from abs link or validate direct PDF URL.

**Steps:**

1. Return the computed result to the caller.

#### `def _load_academic_registry() -> list[dict[str, Any]]`

**Purpose:** Load academic_registry.json domain entries.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def AcademicFetcher._fast_entries(topics) -> list[dict[str, Any]]`

**Purpose:** Friendly JSON/HTTP engines with response_time_ms <= 1200.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `async def AcademicFetcher._fetch_engine(entry, query, max_results) -> list[SearchResult]`

**Purpose:** Dispatch by registry method: json_api, camoufox, or http.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

#### `async def AcademicFetcher._fetch_json_api(entry, query, max_results) -> list[SearchResult]`

**Purpose:** Fetch one registry entry via its JSON API template.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.

#### `async def AcademicFetcher._fetch_camoufox(entry, query, max_results) -> list[SearchResult]`

**Purpose:** Fetch one registry entry via Camoufox browser subprocess.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.

#### `async def AcademicFetcher._fetch_http(entry, query, max_results) -> list[SearchResult]`

**Purpose:** Fetch one registry entry via plain HTTP GET.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.

#### `def AcademicFetcher._build_web_search_url(domain, query) -> str`

**Purpose:** Build domain-specific search URL for web scraping backends.

**Steps:**

1. Return the computed result to the caller.

#### `def AcademicFetcher._parse_html_result(domain, html, url, max_results, query) -> list[SearchResult]`

**Purpose:** Parse HTML search results page into SearchResult list.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def AcademicFetcher._parse_json_result(domain, data, max_results, query) -> list[SearchResult]`

**Purpose:** Parse JSON API response into SearchResult list (domain-specific).

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _strip_jats(text) -> str`

**Purpose:** Remove JATS XML tags from Crossref abstracts.

**Steps:**

1. Return the computed result to the caller.

#### `def _clean_snippet_text(text) -> str`

**Purpose:** Collapse whitespace and strip trailing ellipsis from snippet text.

#### `def _trim_to_sentence(text, target_chars, hard_cap) -> str`

**Purpose:** Trim text to a sentence boundary near target_chars, capped at hard_cap.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _build_dynamic_snippet(*, query, title, body, url, meta_parts=…) -> str`

**Purpose:** Build relevance-scored snippet with optional metadata suffix.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _finalize_sentence_candidate(text) -> str`

**Purpose:** Ensure sentence candidate ends cleanly when source had trailing ellipsis.

**Steps:**

1. Return the computed result to the caller.

---

## Related

- [fetch/_index](../../../../_index/)
