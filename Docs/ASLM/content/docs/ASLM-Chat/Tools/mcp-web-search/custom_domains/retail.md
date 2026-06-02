---
title: "retail"
draft: false
---

## Module `retail`

`Tools/mcp-web-search/custom_domains/retail.py` — ASLM Chat Python module.

---

## Public functions

#### `def extract_retail_metadata(url, raw_html) -> dict[str, str]`

**Purpose:** Dispatch retail metadata extraction by shop host (Citilink, DNS-shop).

**Steps:**

1. Return the computed result to the caller.

---

## Private functions

#### `def _host(url) -> str`

**Purpose:** Normalize URL host (strip www./m. prefixes).

---

## Related

- [custom_domains/_index](../../../_index/)
