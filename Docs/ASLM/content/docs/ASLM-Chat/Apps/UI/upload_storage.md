---
title: "upload_storage"
draft: false
---

## Module `upload_storage`

`Apps/UI/upload_storage.py` — ASLM Chat Python module.

---

## Overview

Part of `Apps\UI`. See **Related** for package index and callers.

---

## Classes

### `class UploadStorageTarget`

**Purpose:** Type `UploadStorageTarget` defined in `upload_storage.py`.

---

## Public functions

#### `def normalize_tool_server_ids(tool_server_ids) -> list[str]`

**Purpose:** Return a stable list of tool server ids from request payloads.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def resolve_upload_storage_target(tool_server_ids) -> UploadStorageTarget`

**Purpose:** Route UI uploads to the mcp-sandbox tree.

#### `def display_kind_for_upload(name, mime) -> tuple[str, str]`

**Purpose:** Return UI-facing kind and label for one upload.

**Steps:**

1. Return the computed result to the caller.

#### `def public_upload_payload(manifest, *, status=…) -> dict[str, Any]`

**Purpose:** Return the small user-facing upload payload.

**Steps:**

1. Return the computed result to the caller.

#### `def model_upload_payload(manifest, *, sandbox_enabled=…) -> dict[str, Any]`

**Purpose:** Return a model-facing manifest that respects the selected sandbox state.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def resolve_uploaded_file_host_path(manifest) -> Path`

**Purpose:** Map a stored manifest sandbox_path back to a host file path.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.

#### `def save_upload_to_sandbox(uploaded_file, *, scope=…, model_supports_vision=…, tool_server_ids=…) -> tuple[UploadedFileManifest, dict[str, Any]]`

**Purpose:** Persist one Django uploaded file and return its private manifest plus public payload.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Handle errors and map them to a safe response.

#### `def load_upload_manifest(file_id) -> dict[str, Any] | None`

**Purpose:** Load a private manifest by file id from external storage or legacy sidecars.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Private functions

#### `def _safe_scope(value) -> str`

**Purpose:** Safe scope.

**Steps:**

1. Return the computed result to the caller.

#### `def _stored_file_name(file_id, original_name) -> str`

**Purpose:** Stored file name.

**Steps:**

1. Return the computed result to the caller.

#### `def _manifest_sidecar_path(file_path) -> Path`

**Purpose:** Manifest sidecar path.

#### `def _manifest_storage_dir(sha256) -> Path`

**Purpose:** Manifest storage dir.

#### `def _manifest_storage_path(manifest) -> Path`

**Purpose:** Manifest storage path.

**Steps:**

1. Return the computed result to the caller.

#### `def _write_manifest(manifest) -> None`

**Purpose:** Write manifest.

**Steps:**

1. Parse or serialize JSON payloads.

#### `def _model_sandbox_path(model_prefix, scope, stored_name) -> str`

**Purpose:** Model sandbox path.

#### `def _file_sha256(file_bytes) -> str`

**Purpose:** File sha256.

#### `def _format_upload_size(size_bytes) -> str`

**Purpose:** Format upload size.

**Steps:**

1. Return the computed result to the caller.

#### `def _stream_upload_to_temp(uploaded_file, *, incoming_root) -> tuple[Path, int, str, bytes | None]`

**Purpose:** Stream upload to temp.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

#### `def _load_manifest_from_sidecar(sidecar_path) -> dict[str, Any] | None`

**Purpose:** Load manifest from sidecar.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Parse or serialize JSON payloads.

#### `def _iter_manifest_paths_for_sha(sha256)`

**Purpose:** Iterate manifest paths for sha.

#### `def _find_stored_manifest(*, sha256, size_bytes, clean_name, sandbox_path=…) -> dict[str, Any] | None`

**Purpose:** Find stored manifest.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _find_existing_upload(target_dir, *, model_prefix, safe_scope, clean_name, file_bytes) -> tuple[Path, dict[str, Any] | None] | None`

**Purpose:** Find existing upload.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _find_existing_upload_by_hash(target_dir, *, sha256, size_bytes, clean_name) -> tuple[Path, dict[str, Any] | None] | None`

**Purpose:** Find existing upload by hash.

**Steps:**

1. Return the computed result to the caller.

#### `def _manifest_from_dict(manifest) -> UploadedFileManifest | None`

**Purpose:** Manifest from dict.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _normalize_existing_manifest_for_path(manifest, *, model_prefix, safe_scope, stored_name) -> UploadedFileManifest | None`

**Purpose:** Normalize existing manifest for path.

**Steps:**

1. Return the computed result to the caller.

#### `def _build_lightweight_upload_manifest(*, file_id, clean_name, mime, size_bytes, sha256, sandbox_path, model_supports_vision, tool_server_id=…) -> UploadedFileManifest`

**Purpose:** Build lightweight upload manifest.

**Steps:**

1. Return the computed result to the caller.

---

## Related

- [UI/_index](../../_index/)
