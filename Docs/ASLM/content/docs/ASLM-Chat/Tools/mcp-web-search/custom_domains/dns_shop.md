---
title: "dns_shop"
draft: false
---

## Module `dns_shop`

`Tools/mcp-web-search/custom_domains/dns_shop.py` — ASLM Chat Python module.

---

## Public functions

#### `def rewrite_read_page_url(url) -> str`

**Purpose:** Point product URLs at the characteristics subpage for richer read_page content.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def dns_variant_urls(url) -> list[str]`

**Purpose:** Build alternate fetch URLs (.xaml, characteristics) for a DNS-shop product page.

**Steps:**

1. Return the computed result to the caller.

#### `def extract_dns_metadata(raw_html) -> dict[str, str]`

**Purpose:** Extract product metadata from DNS-shop product HTML.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Private functions

#### `def _clean_dns_spec_text(text) -> str`

**Purpose:** Trim and cap a single DNS-shop spec line extracted from HTML.

---

## Related

- [custom_domains/_index](../../../_index/)
