---
title: "test_ddgs_partial_buffer"
draft: false
---

## Module `test_ddgs_partial_buffer`

`Tools/mcp-web-search/tests/test_ddgs_partial_buffer.py` — ASLM Chat Python module.

---

## Test methods

#### `def test_partial_buffer_merges_and_dedupes_by_url() -> None`

**Purpose:** test_partial_buffer_merges_and_dedupes_by_url — append merges and URL dedupe preserve first title.

**Steps:**

1. Iterate and transform or accumulate state.
2. Parse or serialize JSON payloads.

#### `def test_partial_buffer_read_is_safe_for_missing_or_invalid_files() -> None`

**Purpose:** test_partial_buffer_read_is_safe_for_missing_or_invalid_files — missing or corrupt files yield [].

#### `def test_async_ddgs_search_returns_partial_results_on_worker_timeout(monkeypatch) -> None`

**Purpose:** test_async_ddgs_search_returns_partial_results_on_worker_timeout — worker timeout surfaces buffered hits.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Iterate and transform or accumulate state.
4. Parse or serialize JSON payloads.
5. Spawn or communicate with a child process.

#### `def test_async_ddgs_search_uses_one_buffer_per_request(monkeypatch) -> None`

**Purpose:** test_async_ddgs_search_uses_one_buffer_per_request — each search gets a distinct partial buffer path.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Iterate and transform or accumulate state.
4. Parse or serialize JSON payloads.
5. Spawn or communicate with a child process.

#### `def test_zero_result_high_fallback_uses_bounded_snippet_only_options(monkeypatch) -> None`

**Purpose:** test_zero_result_high_fallback_uses_bounded_snippet_only_options — second pass uses medium effort caps.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def test_zero_result_high_fallback_does_not_repeat_full_high_for_every_variant(monkeypatch) -> None`

**Purpose:** test_zero_result_high_fallback_does_not_repeat_full_high_for_every_variant — variants use medium only.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Private functions

#### `def _workspace_tmp_dir() -> Path`

**Purpose:** _workspace_tmp_dir — create isolated tmp dir for partial-buffer tests.

#### `def _result(url, title, snippet) -> SearchResult`

**Purpose:** _result — build a synthetic SearchResult for fixtures.

**Steps:**

1. Return the computed result to the caller.

---

## Related

- [tests/_index](../../../_index/)
