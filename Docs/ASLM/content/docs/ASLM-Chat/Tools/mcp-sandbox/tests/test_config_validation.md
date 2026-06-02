---
title: "test_config_validation"
draft: false
---

## Module `test_config_validation`

`Tools/mcp-sandbox/tests/test_config_validation.py` — ASLM Chat Python module.

---

## Classes

### `class ConfigValidationTests`

**Purpose:** Type `ConfigValidationTests` defined in `test_config_validation.py`.

---

## Test methods

#### `def ConfigValidationTests.test_dot_task_dir_rejects_generic_home_workspace() -> None`

**Purpose:** Reject generic home paths when DEFAULT_TASK_DIR is '.'.

#### `def ConfigValidationTests.test_dot_task_dir_allows_dedicated_sandbox_workspace() -> None`

**Purpose:** Allow dedicated sandbox workspace paths when DEFAULT_TASK_DIR is '.'.

#### `def ConfigValidationTests.test_subdir_task_dir_keeps_existing_workspace_validation() -> None`

**Purpose:** Subdir task dir keeps existing workspace validation rules.

---

## Related

- [tests/_index](../../../_index/)
