---
title: "test_read_page_whatsnew_github"
draft: false
---

## Module `test_read_page_whatsnew_github`

`Tools/mcp-web-search/tests/test_read_page_whatsnew_github.py` — ASLM Chat Python module.

---

## Test methods

#### `def whatsnew_rst_markdown() -> str`

**Purpose:** Implements `whatsnew_rst_markdown` in `test_read_page_whatsnew_github.py`.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

#### `def test_github_whatsnew_fetch_is_long_document(whatsnew_rst_markdown) -> None`

**Purpose:** test_github_whatsnew_fetch_is_long_document — fixture markdown exceeds threshold and mentions GIL.

#### `def test_github_whatsnew_bm25_compress_keeps_focus(whatsnew_rst_markdown) -> None`

**Purpose:** test_github_whatsnew_bm25_compress_keeps_focus — BM25 compress stays under budget with focus terms.

#### `def test_github_whatsnew_gliner_compress_keeps_focus(whatsnew_rst_markdown) -> None`

**Purpose:** Implements `test_github_whatsnew_gliner_compress_keeps_focus` in `test_read_page_whatsnew_github.py`.

#### `def test_github_whatsnew_gliner_and_bm25_both_under_budget(whatsnew_rst_markdown) -> None`

**Purpose:** Implements `test_github_whatsnew_gliner_and_bm25_both_under_budget` in `test_read_page_whatsnew_github.py`.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def test_read_page_service_whatsnew_bm25_path(whatsnew_rst_markdown, monkeypatch) -> None`

**Purpose:** test_read_page_service_whatsnew_bm25_path — service.read compresses fixture via BM25 without live fetch.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.

#### `def test_read_page_service_whatsnew_gliner_path(whatsnew_rst_markdown, monkeypatch) -> None`

**Purpose:** Implements `test_read_page_service_whatsnew_gliner_path` in `test_read_page_whatsnew_github.py`.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.

---

## Private functions

#### `def _compress(markdown, *, focus=…, enable_gliner) -> str`

**Purpose:** _compress — run compress_read_page_markdown with BM25 and optional GLiNER.

**Steps:**

1. Return the computed result to the caller.

#### `def _gliner_runtime_ready() -> tuple[bool, str]`

**Purpose:** _gliner_runtime_ready — skip GLiNER tests when package or full_gpu unavailable.

**Steps:**

1. Return the computed result to the caller.

---

## Related

- [tests/_index](../../../_index/)
