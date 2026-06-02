---
title: "update_model_runtime_metadata"
draft: false
---

## Module `update_model_runtime_metadata`

`Tools/update_model_runtime_metadata.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools`. See **Related** for package index and callers.

---

## Public functions

#### `def main() -> int`

**Purpose:** Implements `main` in `update_model_runtime_metadata.py`.

**Steps:**

1. Return the computed result to the caller.
2. Parse or serialize JSON payloads.

---

## Private functions

#### `def _read_json_file(path) -> dict[str, Any]`

**Purpose:** Implements `_read_json_file` in `update_model_runtime_metadata.py`.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _manifest_setting(manifest, key) -> Any`

**Purpose:** Implements `_manifest_setting` in `update_model_runtime_metadata.py`.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _runtime_setting(settings, manifest, key, default, *, env_key=…) -> Any`

**Purpose:** Implements `_runtime_setting` in `update_model_runtime_metadata.py`.

**Steps:**

1. Return the computed result to the caller.

#### `def _coerce_port(value) -> int | None`

**Purpose:** Implements `_coerce_port` in `update_model_runtime_metadata.py`.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _local_route_url(port, route) -> str`

**Purpose:** Implements `_local_route_url` in `update_model_runtime_metadata.py`.

#### `def _source_descriptor(name, route, port_key) -> dict[str, Any]`

**Purpose:** Implements `_source_descriptor` in `update_model_runtime_metadata.py`.

**Steps:**

1. Return the computed result to the caller.

#### `def _fetch_json(url, *, method=…, body=…) -> dict[str, Any]`

**Purpose:** Implements `_fetch_json` in `update_model_runtime_metadata.py`.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Parse or serialize JSON payloads.

#### `def _ollama_base_url(settings, manifest) -> str`

**Purpose:** Implements `_ollama_base_url` in `update_model_runtime_metadata.py`.

**Steps:**

1. Return the computed result to the caller.

#### `def _find_loaded_ollama_model(models, model_name) -> dict[str, Any]`

**Purpose:** Implements `_find_loaded_ollama_model` in `update_model_runtime_metadata.py`.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _active_model_key(engine, model_name) -> str`

**Purpose:** Implements `_active_model_key` in `update_model_runtime_metadata.py`.

#### `def _build_metadata() -> dict[str, Any]`

**Purpose:** Implements `_build_metadata` in `update_model_runtime_metadata.py`.

**Steps:**

1. Return the computed result to the caller.

#### `def _write_json_atomic(path, payload) -> None`

**Purpose:** Implements `_write_json_atomic` in `update_model_runtime_metadata.py`.

---

## Related

- [Tools/_index](../_index/)
