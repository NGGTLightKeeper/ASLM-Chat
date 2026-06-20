---
title: "parse"
draft: false
---

## Module `parse`

`Tools/mcp-web-search/core/fetch/academic/parse.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools/mcp-web-search/core/fetch/academic`.

---

## Classes

### `class _Empty`

**Purpose:** Implements `_Empty`.

#### `def _Empty.get_text(self, *_a, **_k) -> str`

**Purpose:** Implements `get_text`.

---

## Public functions

#### `def parse_openalex(body) -> list[...]`

**Purpose:** Implements `parse_openalex`.

#### `def parse_crossref(body) -> list[...]`

**Purpose:** Implements `parse_crossref`.

#### `def parse_europepmc(body) -> list[...]`

**Purpose:** Implements `parse_europepmc`.

#### `def parse_doaj(body) -> list[...]`

**Purpose:** Implements `parse_doaj`.

#### `def parse_arxiv(xml_text) -> list[...]`

**Purpose:** Implements `parse_arxiv`.

#### `def is_scholar_block(html_text) -> bool`

**Purpose:** Implements `is_scholar_block`.

#### `def parse_scholar(html_text) -> list[...]`

**Purpose:** Implements `parse_scholar`.

#### `def parse_serpapi_scholar(body) -> list[...]`

**Purpose:** Implements `parse_serpapi_scholar`.

---

## Private functions

#### `def _clean(text) -> str`

**Purpose:** Implements `_clean`.

#### `def _abstract(text) -> str`

**Purpose:** Implements `_abstract`.

#### `def _doi(value) -> str`

**Purpose:** Implements `_doi`.

#### `def _int(value) -> ...`

**Purpose:** Implements `_int`.

#### `def _deinvert_abstract(index) -> str`

**Purpose:** Implements `_deinvert_abstract`.

---

## Related

- [academic/_index](../../_index/)
