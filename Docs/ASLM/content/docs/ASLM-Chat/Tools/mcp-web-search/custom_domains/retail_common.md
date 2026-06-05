---
title: "retail_common"
draft: false
---

## Module `retail_common`

`Tools/mcp-web-search/custom_domains/retail_common.py` — ASLM Chat Python module.

---

## Public functions

#### `def strip_html_fragment(text) -> str`

**Purpose:** Strip tags from a small HTML fragment and unescape entities.

**Steps:**

1. Return the computed result to the caller.

#### `def format_price_value(value) -> str`

**Purpose:** Format a price string as grouped integer digits (space thousands separator).

**Steps:**

1. Return the computed result to the caller.

#### `def normalize_availability(value) -> str`

**Purpose:** Normalize schema.org or free-text availability labels for display.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def prepend_retail_metadata(markdown, meta) -> str`

**Purpose:** Prepend structured retail fields (price, availability, specs) above markdown body.

**Steps:**

1. Return the computed result to the caller.

---

## Related

- [custom_domains/_index](../../../_index/)
