---
title: "file_manifests"
draft: false
---

## Module `file_manifests`

`Apps/UI/file_manifests.py` — ASLM Chat Python module.

---

## Overview

Part of `Apps\UI`. See **Related** for package index and callers.

---

## Classes

### `class UploadedFileManifest`

**Purpose:** Type `UploadedFileManifest` defined in `file_manifests.py`.

---

## Public functions

#### `def UploadedFileManifest.to_dict() -> dict[str, Any]`

**Purpose:** Return a JSON-serializable dict for the dataclass.

#### `def normalize_upload_name(name) -> str`

**Purpose:** Return a display-safe basename for an uploaded file.

#### `def guess_upload_mime(name, mime) -> str`

**Purpose:** Return a stable MIME value for an uploaded file.

**Steps:**

1. Return the computed result to the caller.

#### `def is_probably_text_upload(name, mime) -> bool`

**Purpose:** Return whether an upload should be treated as text-like.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def build_uploaded_file_manifest(file_bytes, *, name, mime=…, sandbox_path=…, model_supports_vision=…, file_id=…, tool_server_id=…) -> UploadedFileManifest`

**Purpose:** Build the model-facing manifest for one uploaded file.

**Steps:**

1. Return the computed result to the caller.

---

## Private functions

#### `def _has_binary_markers(sample) -> bool`

**Purpose:** Return whether a byte sample contains binary markers.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _decode_text_bytes(file_bytes, *, explicit_text) -> tuple[str, bool]`

**Purpose:** Decode text bytes.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _looks_like_text(text) -> bool`

**Purpose:** Return whether decoded text looks printable enough to treat as text.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _trim_text_preview(text, *, source_truncated) -> tuple[str | None, int, bool]`

**Purpose:** Trim text preview.

**Steps:**

1. Return the computed result to the caller.

#### `def _build_table_preview(name, text) -> str | None`

**Purpose:** Build table preview.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _build_zip_tree(file_bytes) -> list[str] | None`

**Purpose:** Build zip tree.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _extract_xml_text(xml_bytes) -> str`

**Purpose:** Extract xml text.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _extract_pdf_text(file_bytes) -> str`

**Purpose:** Extract pdf text.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _extract_docx_text(archive) -> str`

**Purpose:** Extract docx text.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _extract_pptx_text(archive) -> str`

**Purpose:** Extract pptx text.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _extract_xlsx_text(archive) -> str`

**Purpose:** Extract xlsx text.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _extract_document_text(file_bytes, name, mime) -> str`

**Purpose:** Extract document text.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

---

## Related

- [UI/_index](../../_index/)
