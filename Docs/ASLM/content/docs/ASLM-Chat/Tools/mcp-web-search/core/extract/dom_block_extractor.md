---
title: "dom_block_extractor"
draft: false
---

## Module `dom_block_extractor`

`Tools/mcp-web-search/core/extract/dom_block_extractor.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools\mcp-web-search\core\extract`. See **Related** for package index and callers.

---

## Public functions

#### `def observe_domain_page(domain) -> None`

**Purpose:** Record one more sampled page for per-domain template frequency.

#### `def template_frequency_score(domain, dom_path) -> float`

**Purpose:** Return [0, 1]: how often this DOM path appeared on sampled pages for the domain.

**Steps:**

1. Return the computed result to the caller.

#### `def structure_ui_score(tag, *, domain=…, debug_lexicon=…) -> float`

**Purpose:** Language-agnostic UI/nav score in [0, 1]; higher = more likely boilerplate.

**Steps:**

1. Return the computed result to the caller.

#### `def nav_score(tag, *, domain=…) -> float`

**Purpose:** Backward-compatible alias for structure_ui_score.

#### `def block_keep_score(tag, text, *, domain=…, query_relevance=…) -> float`

**Purpose:** Final keep score: content minus UI, with optional query relevance hook.

**Steps:**

1. Return the computed result to the caller.

#### `def extract_dom_blocks(cleaned_html, *, domain=…, url=…, min_block_chars=…, nav_reject_threshold=…, debug_lexicon=…) -> tuple[list[str], dict[str, int | str]]`

**Purpose:** Extract content blocks, filtering structural UI/nav noise.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

---

## Private functions

#### `def _record_path_observation(domain, dom_path, text_len, link_density) -> None`

**Purpose:** Update path-level length and link-density stats for a domain.

#### `def _domain_from_url(url) -> str`

**Purpose:** Hostname from URL (www. stripped).

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _dom_path(tag) -> str`

**Purpose:** Slash-separated tag path from element up to html.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _attr_nav_score(tag) -> float`

**Purpose:** Nav/UI score from id, class, role, and aria attributes.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _anchor_density(tag, text) -> float`

**Purpose:** Fraction of block text inside anchor tags.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _clickable_density(tag) -> float`

**Purpose:** Fraction of descendants that are clickable elements.

**Steps:**

1. Return the computed result to the caller.

#### `def _control_density(tag) -> float`

**Purpose:** Fraction of descendants that are form controls.

**Steps:**

1. Return the computed result to the caller.

#### `def _separator_ratio(text) -> float`

**Purpose:** Density of menu-style separator characters in text.

**Steps:**

1. Return the computed result to the caller.

#### `def _short_text_node_ratio(tag) -> float`

**Purpose:** Fraction of text nodes that are very short (menu-label signal).

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _text_density(tag, text) -> float`

**Purpose:** Text length per descendant element (paragraph mass proxy).

#### `def _sentence_like_ratio(text) -> float`

**Purpose:** Fraction of clause splits that look like real sentences (not menu labels).

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _monolithic_list_score(text) -> float`

**Purpose:** Score for long unstructured word lists without facts (mega-menus).

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _menu_cluster_score(tag) -> float`

**Purpose:** Many same-tag siblings with similar lengths (menu cluster).

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _ancestor_menu_hint(tag) -> float`

**Purpose:** Boost when ancestors have menu/nav-related attributes.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _sibling_uniformity(tag) -> float`

**Purpose:** Similarity of tag, length, and link density among siblings.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _nav_word_density_debug(text) -> float`

**Purpose:** Debug-only nav-word density (optional lexicon weight).

**Steps:**

1. Return the computed result to the caller.

#### `def _content_score(tag, text) -> float`

**Purpose:** Content signal from sentence shape, text mass, and low link density.

**Steps:**

1. Return the computed result to the caller.

#### `def _is_protected(tag, text) -> bool`

**Purpose:** True for table cells/rows and fact-like text blocks.

#### `def _collect_leaf_blocks(soup) -> list[tuple['Tag', str]]`

**Purpose:** Collect leaf-level block tags with deduplicated text signatures.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Related

- [extract/_index](../../../../_index/)
