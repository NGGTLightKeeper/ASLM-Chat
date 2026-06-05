---
title: "common"
draft: false
---

## Module `common`

`Tools/mcp-web-search/custom_domains/common.py` — ASLM Chat Python module.

---

## Public functions

#### `def trim(text, limit) -> str`

**Purpose:** Collapse whitespace and cap string length.

#### `def extract_title(html) -> str`

**Purpose:** Parse document title from raw HTML.

#### `def looks_blocked(title, html) -> bool`

**Purpose:** Heuristic: page looks like a bot/captcha block rather than real content.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def clean_trafilatura_snapshot(text) -> str`

**Purpose:** Drop known Trafilatura noise lines from extracted markdown.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def extract_with_preferred_pipeline(url, raw_html, *, prefer_trafilatura) -> dict[str, Any]`

**Purpose:** Run normalize_page or trafilatura extraction and build markdown snapshot fields.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Related

- [custom_domains/_index](../../../_index/)
