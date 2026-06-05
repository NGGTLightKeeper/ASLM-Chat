---
title: "aslm_embedding_models"
draft: false
---

## Module `aslm_embedding_models`

`Tools/mcp-web-search/core/query/aslm_embedding_models.py` — ASLM Chat Python module.

---

## Public functions

#### `def export_is_complete(path) -> bool`

**Purpose:** True when an on-disk ASLM embedding export has required artifacts.

**Steps:**

1. Return the computed result to the caller.

#### `def encoder_export_path(root) -> Path`

**Purpose:** Default on-disk path for query classifier (encoder) export.

#### `def decoder_export_path(root) -> Path`

**Purpose:** Default on-disk path for source relevance (decoder) export.

---

## Related

- [query/_index](../../../../_index/)
