---
title: "gliner_wrapper"
draft: false
---

## Module `gliner_wrapper`

`Tools/mcp-web-search/core/extract/gliner_wrapper.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools\mcp-web-search\core\extract`. See **Related** for package index and callers.

---

## Public functions

#### `def get_gliner_runtime(device) -> tuple[str, str] | None`

**Purpose:** Return (model_id, device) for a safe CUDA GLiNER runtime, or None.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def gliner_cuda_enabled(log_fn) -> bool`

**Purpose:** True when a safe CUDA GLiNER runtime is available; log_fn receives diagnostics.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def is_gliner_available() -> bool`

**Purpose:** True when the gliner package is importable.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def score_entity_density(paragraphs, device, threshold, cpu_para_limit) -> list[float]`

**Purpose:** Return entity-density score [0.0, 1.0] for each paragraph.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def score_entity_density_with_entities(paragraphs, labels, device, threshold, cpu_para_limit) -> list[tuple[float, list[dict[str, Any]]]]`

**Purpose:** Return entity-density score and normalized entities for each paragraph.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def get_labels_for_query(query, query_type) -> list[str]`

**Purpose:** Choose GLiNER label set from explicit or inferred query type.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def check_information_density(text, labels, min_entities, threshold, max_length, device) -> tuple[bool, list[dict]]`

**Purpose:** Return (passes_threshold, entities); used to drop low-information pages.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def detect_language_and_adjust_threshold(text) -> float`

**Purpose:** Lower GLiNER threshold for Cyrillic-heavy text.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Private functions

#### `def _log_skip_once(key, message) -> None`

**Purpose:** Log a GLiNER skip reason at most once per key.

#### `def _restore_env(previous) -> None`

**Purpose:** Restore environment variables after a temporary HF offline override.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def _cuda_free_gb() -> float | None`

**Purpose:** Read free CUDA VRAM in GB via nvidia-smi or torch.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Spawn or communicate with a child process.

#### `def _load_model(device) -> Optional[Any]`

**Purpose:** Load (or return cached) GLiNER model on the requested device.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _normalize_entities(raw_entities) -> list[dict[str, Any]]`

**Purpose:** Normalize raw GLiNER entity dicts to a consistent shape.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

---

## Related

- [extract/_index](../../../../_index/)
