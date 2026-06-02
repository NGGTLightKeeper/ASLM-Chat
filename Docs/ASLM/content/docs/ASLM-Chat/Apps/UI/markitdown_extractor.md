---
title: "markitdown_extractor"
draft: false
---

## Module `markitdown_extractor`

`Apps/UI/markitdown_extractor.py` — ASLM Chat Python module.

---

## Public functions

#### `def extract_markdown(file_bytes, *, name, mime) -> str`

**Purpose:** Return Markdown extracted from document bytes, or an empty string on failure.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

---

## Private functions

#### `def _get_markitdown_instance()`

**Purpose:** Return a shared MarkItDown converter instance when available.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _extract_once(file_bytes, *, name, mime) -> str`

**Purpose:** Run one MarkItDown conversion for the given bytes.

**Steps:**

1. Return the computed result to the caller.

---

## Related

- [UI/_index](../../_index/)
