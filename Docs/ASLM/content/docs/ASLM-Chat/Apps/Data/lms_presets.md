---
title: "lms_presets"
draft: false
---

## Module `lms_presets`

`Apps/Data/lms_presets.py` — ASLM Chat Python module.

---

## Overview

Part of `Apps\Data`. See **Related** for package index and callers.

---

## Public functions

#### `def normalize_lms_preset_config(config) -> dict[str, Any]`

**Purpose:** Return a compact LM Studio preset config ready for storage.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def ensure_lms_preset_state(model_name) -> tuple[list[LmsPreset], LmsPreset]`

**Purpose:** Ensure a model has one default preset and one active preset.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Iterate and transform or accumulate state.
4. Read or write Django ORM records.

#### `def get_lms_preset_payload(model_name) -> dict[str, Any]`

**Purpose:** Return presets and the active config for the selected model.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def activate_lms_preset(model_name, preset_id) -> dict[str, Any]`

**Purpose:** Mark one preset as active for its model.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.
3. Read or write Django ORM records.

#### `def create_lms_preset(model_name, *, name=…, config=…, activate=…) -> dict[str, Any]`

**Purpose:** Create a custom preset for the selected model.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.
5. Read or write Django ORM records.

#### `def rename_lms_preset(model_name, preset_id, new_name) -> dict[str, Any]`

**Purpose:** Rename a custom preset without changing its config.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

#### `def delete_lms_preset(model_name, preset_id) -> dict[str, Any]`

**Purpose:** Delete a custom preset and restore the default when needed.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Iterate and transform or accumulate state.

#### `def sync_active_lms_preset(model_name, config) -> dict[str, Any]`

**Purpose:** Persist UI changes into the active preset.

**Steps:**

1. Return the computed result to the caller.

---

## Private functions

#### `def _normalize_config_value(value) -> Any`

**Purpose:** Remove empty values while preserving scalar types.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _get_default_lms_preset_config(model_name) -> dict[str, Any]`

**Purpose:** Read the default LM Studio config baked into the selected model.

**Steps:**

1. Return the computed result to the caller.

#### `def _next_custom_preset_name(model_name) -> str`

**Purpose:** Generate the next free custom preset name for a model.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.
3. Read or write Django ORM records.

#### `def _serialize_preset(preset) -> dict[str, Any]`

**Purpose:** Convert a preset model into the frontend JSON shape.

**Steps:**

1. Return the computed result to the caller.

#### `def _get_preset_by_id(presets, preset_id) -> LmsPreset`

**Purpose:** Return one preset from a loaded list or raise when it is missing.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Iterate and transform or accumulate state.

---

## Related

- [Data/_index](../../_index/)
