---
title: "pdf_extractor"
draft: false
---

## Module `pdf_extractor`

`Tools/mcp-web-search/core/extract/pdf_extractor.py` — ASLM Chat Python module.

---

## Public functions

#### `def looks_like_pdf_url(url) -> bool`

**Purpose:** True when URL path or query indicates a PDF resource.

**Steps:**

1. Return the computed result to the caller.

#### `def looks_like_pdf_bytes(data) -> bool`

**Purpose:** True when raw bytes start with the PDF magic header.

#### `def looks_like_pdf_text_dump(text) -> bool`

**Purpose:** True when decoded text looks like a PDF object stream, not article body.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def looks_like_decoded_binary(text) -> bool`

**Purpose:** True when text is likely arbitrary binary decoded as UTF-8.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def pdf_bytes_to_markdown(*, url, data, title=…, max_chars=…) -> str`

**Purpose:** Write PDF bytes to a temp file, extract markdown, then delete the temp file.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def pdf_file_to_markdown(*, url, path, title=…, max_chars=…) -> str`

**Purpose:** Extract a local PDF file into a bounded markdown document.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

---

## Related

- [extract/_index](../../../../_index/)
