---
title: "nextjs_rsc"
draft: false
---

## Module `nextjs_rsc`

`Tools/mcp-web-search/core/extract/nextjs_rsc.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools\mcp-web-search\core\extract`. See **Related** for package index and callers.

---

## Public functions

#### `def extract_nextjs_rsc_text(raw_html) -> str`

**Purpose:** Extract structured text from Next.js RSC flight payloads embedded in HTML.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Private functions

#### `def _parse_rsc_records(raw_html) -> dict[str, object]`

**Purpose:** Parse self.__next_f.push script chunks into record id → JSON node map.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.
4. Parse or serialize JSON payloads.

#### `def _is_content_root(node) -> bool`

**Purpose:** True when an RSC node is a content root (heading, paragraph, list, table, etc.).

**Steps:**

1. Return the computed result to the caller.

#### `def _render_node(node, records, seen) -> list[str]`

**Purpose:** Render an RSC subtree into markdown-like text blocks.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _render_list(node, records, seen) -> list[str]`

**Purpose:** Render ul/ol children as markdown list items.

#### `def _find_list_items(node, records, seen) -> list[str]`

**Purpose:** Recursively collect li text from a list subtree.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _render_table_like(node, records, seen) -> list[str]`

**Purpose:** Render table rows as pipe-separated cell lines.

#### `def _find_table_rows(node, records, seen) -> list[list[str]]`

**Purpose:** Recursively collect tr → cell text rows from a table subtree.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _find_row_cells(node, records, seen) -> list[str]`

**Purpose:** Collect td/th inline text for one table row.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _inline_text(node, records, seen) -> str`

**Purpose:** Flatten inline markup into a single line of text.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _clean_inline_text(text) -> str`

**Purpose:** Strip RSC sentinel strings and collapse whitespace in inline text.

**Steps:**

1. Return the computed result to the caller.

#### `def _clean_block(text) -> str`

**Purpose:** Normalize whitespace in a rendered block.

**Steps:**

1. Return the computed result to the caller.

#### `def _join_inline(parts) -> str`

**Purpose:** Join inline text parts with spaces, preserving explicit line breaks.

#### `def _resolve_if_ref(node, records, seen) -> object | None`

**Purpose:** Resolve a string node when it is an RSC $L reference.

#### `def _resolve_ref(value, records, seen) -> object | None`

**Purpose:** Follow $L<id> reference into the records map (cycle-safe).

**Steps:**

1. Return the computed result to the caller.

#### `def _is_element(node) -> bool`

**Purpose:** True when node is an RSC React element tuple ($, tag, …).

#### `def _tag_name(node) -> str`

**Purpose:** Tag name from an RSC element tuple.

#### `def _props(node) -> dict[str, object]`

**Purpose:** Props dict from an RSC element tuple.

---

## Related

- [extract/_index](../../../../_index/)
