---
title: "download_types"
draft: false
---

## Module `download_types`

`Tools/mcp-web-search/core/fetch/download_types.py` — ASLM Chat Python module.

---

## Public functions

#### `def get_download_info(url) -> tuple[str, str] | None`

**Purpose:** Return (extension, category) if url points to a known downloadable file.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

---

## Private functions

#### `def _extract_extension(filename) -> str`

**Purpose:** Return the lowercase extension, including compound archive suffixes.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Related

- [fetch/_index](../../../../_index/)
