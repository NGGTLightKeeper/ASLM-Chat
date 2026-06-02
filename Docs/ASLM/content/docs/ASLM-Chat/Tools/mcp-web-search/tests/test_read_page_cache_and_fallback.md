---
title: "test_read_page_cache_and_fallback"
draft: false
---

## Module `test_read_page_cache_and_fallback`

`Tools/mcp-web-search/tests/test_read_page_cache_and_fallback.py` — ASLM Chat Python module.

---

## Test methods

#### `def test_source_cache_round_trips_and_searches_cached_pages() -> None`

**Purpose:** test_source_cache_round_trips_and_searches_cached_pages — cache hit and local search by terms.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def test_source_cache_recovers_corrupt_database_and_keeps_working() -> None`

**Purpose:** test_source_cache_recovers_corrupt_database_and_keeps_working — corrupt file renamed; new DB works.

#### `def test_read_page_uses_fresh_cache_without_network_or_camoufox(monkeypatch) -> None`

**Purpose:** test_read_page_uses_fresh_cache_without_network_or_camoufox — cache hit never calls _fetch_raw_html.

**Steps:**

1. Raise on invalid input or failure conditions.

#### `def test_fetch_raw_html_keeps_camoufox_idle_when_network_succeeds(monkeypatch) -> None`

**Purpose:** test_fetch_raw_html_keeps_camoufox_idle_when_network_succeeds — successful _fetch_race skips browser.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.

#### `def test_fetch_raw_html_falls_back_to_camoufox_after_empty_network(monkeypatch) -> None`

**Purpose:** test_fetch_raw_html_falls_back_to_camoufox_after_empty_network — empty network triggers browser fetch.

**Steps:**

1. Return the computed result to the caller.

---

## Private functions

#### `def _workspace_tmp_dir() -> Path`

**Purpose:** _workspace_tmp_dir — create isolated tmp dir for read_page cache tests.

#### `def _html(body) -> str`

**Purpose:** _html — build synthetic HTML page body for cache fixtures.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Related

- [tests/_index](../../../_index/)
