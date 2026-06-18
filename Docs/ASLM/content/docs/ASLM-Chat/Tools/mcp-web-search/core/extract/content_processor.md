---
title: "content_processor"
draft: false
---

## Module `content_processor`

`Tools/mcp-web-search/core/extract/content_processor.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools\mcp-web-search\core\extract`. See **Related** for package index and callers.

---

## Public functions

#### `def compress_to_budget(text, query, max_chars) -> str`

**Purpose:** Select top paragraphs by BM25 relevance that fit within max_chars.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def derive_read_page_focus(url, markdown) -> str`

**Purpose:** Fallback BM25 query from URL path segments and page title.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def compress_read_page_markdown(markdown, *, url=…, focus=…, max_chars, compress_threshold, compress_target, enable_compress=…, enable_gliner=…) -> str`

**Purpose:** Shrink long read_page output with BM25 or GLiNER before the hard max_chars cap.

**Steps:**

1. Return the computed result to the caller.

#### `def _unknown_macros(text) -> list[str]`

**Purpose:** Return sorted list of \cmd names in text not in _KNOWN_MACROS.

#### `def _make_walker_context(unknown)`

**Purpose:** Build pylatexenc LatexWalker context with unknown macros as 1-arg pass-through.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _make_l2t_context(unknown)`

**Purpose:** Build pylatexenc latex2text context with unknown macros as 1-arg pass-through.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _has_latex(text) -> bool`

**Purpose:** True when text likely contains LaTeX markup.

**Steps:**

1. Return the computed result to the caller.

#### `def _clean_latex_for_index(text) -> str`

**Purpose:** Convert LaTeX markup to plain text suitable for BM25 tokenisation.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _node_to_text(node) -> str`

**Purpose:** Recursively transpile a pylatexenc node to readable text for the LLM.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _render_latex_for_llm(text) -> str`

**Purpose:** Transpile LaTeX markup to human-readable notation for the LLM.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _bm25_tokenize(text) -> list[str]`

**Purpose:** Tokenize text for BM25 (words longer than _BM25_MIN_TOKEN_LEN).

#### `def _bm25_score_paragraphs(paragraphs, query_terms) -> list[float]`

**Purpose:** Return BM25 score of each paragraph against query_terms.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _should_run_gliner(quality_score, hw_profile) -> tuple[bool, str]`

**Purpose:** Return (should_run, device) based on hardware profile and page quality.

**Steps:**

1. Return the computed result to the caller.

#### `def _gliner_compress(paragraphs, query_terms, max_chars, device, query_type) -> tuple[str, bool]`

**Purpose:** Re-rank paragraphs by BM25 + GLiNER hybrid; fit to max_chars.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _resolve_read_page_compress_query(focus, url, markdown) -> str`

**Purpose:** Prefer explicit focus; else derive from URL/title; else empty.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _normalize_text(text) -> str`

**Purpose:** Collapse whitespace and unescape HTML entities in text.

#### `def _single_line(text) -> str`

**Purpose:** Join paragraph blocks into a single pipe-separated line.

#### `def _truncate_at_sentence(text, max_chars) -> str`

**Purpose:** Truncate text to max_chars, preferring a sentence boundary when possible.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _regex_html_to_text(raw_html) -> str`

**Purpose:** Strip scripts/styles and tags; return normalized plain text.

**Steps:**

1. Return the computed result to the caller.

#### `def _preclean_html(raw_html) -> str`

**Purpose:** Remove noise tags and noise-marker nodes from HTML.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _split_trafilatura_sections(text) -> str`

**Purpose:** Re-split over-merged trafilatura output when possible.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _flat_nav_structural_ratio(text) -> float`

**Purpose:** Structural flat-text nav heuristic (short lines, separators, low sentence density).

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _choose_extraction(cleaned_html, *, url=…, min_clean_chars=…) -> tuple[str, str, dict[str, int | str]]`

**Purpose:** Pick trafilatura or DOM blocks, whichever yields cleaner structure.

**Steps:**

1. Return the computed result to the caller.

#### `def _extract_text_with_dom_blocks(cleaned_html, *, url=…) -> tuple[str, dict[str, int | str]]`

**Purpose:** DOM-aware block extraction (replaces naïve bs4 fallback).

**Steps:**

1. Return the computed result to the caller.

#### `def _extract_text_with_bs4(cleaned_html) -> str`

**Purpose:** Extract leaf block tags via BeautifulSoup.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _get_boilerplate_filter()`

**Purpose:** Return a callable that returns True for boilerplate text blocks.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _dedupe_blocks(blocks) -> list[str]`

**Purpose:** Deduplicate blocks by exact text and token signature.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _split_blocks(text) -> list[str]`

**Purpose:** Split text into normalized paragraph blocks.

#### `def _extract_text_with_trafilatura(cleaned_html) -> str`

**Purpose:** Extract main text via trafilatura (tables on, comments off).

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _clean_extracted_text(text) -> tuple[str, int]`

**Purpose:** Filter boilerplate blocks and dedupe; return joined text and block count.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _estimate_quality(text, block_count) -> float`

**Purpose:** Heuristic quality score in [0, 1] from length, blocks, and noise markers.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Related

- [extract/_index](../../../../_index/)
