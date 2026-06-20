---
title: "parsing"
draft: false
---

## Module `parsing`

`Tools/mcp-web-search/core/engines/parsing.py` — ASLM Chat Python module.

---

## Public functions

#### `def parse_html(document) -> LexborHTMLParser`

**Purpose:** Parse an HTML document string into a LexborHTMLParser tree.

**Steps:**

1. Return the computed result to the caller.

#### `def clean_text(parts) -> str`

**Purpose:** Join and collapse whitespace from an iterable of text parts into one string.

**Steps:**

1. Return the computed result to the caller.

#### `def node_text(node) -> str`

**Purpose:** Extract normalized text content from a node, or return an empty string.

**Steps:**

1. Return the computed result to the caller.

#### `def first_node_text(node, selectors) -> str`

**Purpose:** Return the first non-empty text value matched by any of the given CSS selectors.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def first_attribute(node, selectors, attribute) -> str`

**Purpose:** Return the first non-empty attribute value matched by any of the given selectors.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def first_cards(tree, variants) -> tuple[str, list[LexborNode]]`

**Purpose:** Return the first variant name and node list whose CSS selector matches cards in the tree.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def valid_http_url(value) -> bool`

**Purpose:** Return True when the value is an absolute HTTP or HTTPS URL with a host.

**Steps:**

1. Return the computed result to the caller.

#### `def split_region(region) -> tuple[str, str]`

**Purpose:** Split a region string like "us-en" into a (country, language) tuple.

**Steps:**

1. Return the computed result to the caller.

#### `def deduplicate(results) -> list[SearchResult]`

**Purpose:** Remove duplicate URLs from a result list while preserving order.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def classify_parse(engine, results, parser_variant, cards_seen, malformed_cards, blocked, explicit_empty, diagnostics) -> EngineParseResult`

**Purpose:** Classify parse outcomes and build an EngineParseResult from raw parse metrics.

**Steps:**

1. Return the computed result to the caller.

---

## Related

- [engines/_index](../_index/)
