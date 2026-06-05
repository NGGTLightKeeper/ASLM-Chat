---
title: "page_normalizer"
draft: false
---

## Module `page_normalizer`

`Tools/mcp-web-search/core/extract/page_normalizer.py` — ASLM Chat Python module.

---

## Public functions

#### `def normalize_page(url, raw_html, fallback_text) -> str`

**Purpose:** Produce a clean, structured markdown representation of a web page.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Private functions

#### `def _extract_meta_trafilatura(raw_html) -> dict[str, str]`

**Purpose:** Extract metadata using trafilatura (CPU only).

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _extract_meta_fallback(raw_html) -> dict[str, str]`

**Purpose:** Extract metadata from HTML using regex / bs4.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _extract_meta(raw_html, fallback_text, url) -> dict[str, str]`

**Purpose:** Build a meta dict from HTML, fallback text, and URL.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _extract_with_trafilatura_formatted(cleaned_html, url) -> str`

**Purpose:** Use trafilatura with include_formatting=True for markdown-like output.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _extract_content(raw_html, fallback_text, url) -> str`

**Purpose:** Extract and return the main textual content from HTML or fallback.

**Steps:**

1. Return the computed result to the caller.

#### `def _split_blocks_structured(text) -> list[str]`

**Purpose:** Split text into blocks by double-newlines, preserving markdown structure.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _is_structured_block(block) -> bool`

**Purpose:** True when block is markdown heading, list, quote, or code fence.

**Steps:**

1. Return the computed result to the caller.

#### `def _clean_content(text, strict) -> str`

**Purpose:** Clean and deduplicate blocks while preserving markdown structure.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _fallback_segment(text) -> str`

**Purpose:** Segment a wall-of-text into reasonable blocks.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _segment_lines(lines) -> str`

**Purpose:** Turn short non-sentence lines into markdown headings.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _build_markdown(meta, content) -> str`

**Purpose:** Assemble the final markdown document with meta header.

**Steps:**

1. Return the computed result to the caller.

---

## Related

- [extract/_index](../../../../_index/)
