---
title: "test_read_page_compress"
draft: false
---

## Module `test_read_page_compress`

`Tools/mcp-web-search/tests/test_read_page_compress.py` — ASLM Chat Python module.

---

## Test methods

#### `def test_derive_read_page_focus_from_url_and_title() -> None`

**Purpose:** derive_read_page_focus — infer focus tokens from URL and title.

#### `def test_compress_read_page_uses_bm25_when_gliner_disabled() -> None`

**Purpose:** compress_read_page_markdown — BM25 path shrinks long pages when GLiNER is off.

#### `def test_resolve_read_page_compress_query_prefers_explicit_focus() -> None`

**Purpose:** _resolve_read_page_compress_query — explicit focus wins over derived focus.

#### `def test_resolve_read_page_compress_query_falls_back_to_derived_focus() -> None`

**Purpose:** _resolve_read_page_compress_query — empty focus falls back to URL/title derivation.

#### `def test_compress_read_page_skips_when_below_threshold() -> None`

**Purpose:** compress_read_page_markdown — skip compression when below threshold.

---

## Private functions

#### `def _long_page(*, filler, needle, repeats=…) -> str`

**Purpose:** Build a long synthetic page with a unique needle paragraph inserted mid-body.

---

## Related

- [tests/_index](../../../_index/)
