---
title: "test_workspace_boundary"
draft: false
---

## Module `test_workspace_boundary`

`Tools/mcp-sandbox/tests/test_workspace_boundary.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools\mcp-sandbox\tests`. See **Related** for package index and callers.

---

## Classes

### `class WorkspaceBoundaryTests`

**Purpose:** Type `WorkspaceBoundaryTests` defined in `test_workspace_boundary.py`.

---

## Test methods

#### `def WorkspaceBoundaryTests.setUp() -> None`

**Purpose:** Implements `WorkspaceBoundaryTests.setUp` in `test_workspace_boundary.py`.

**Steps:**

1. Handle errors and map them to a safe response.
2. Iterate and transform or accumulate state.

#### `def WorkspaceBoundaryTests.test_read_traversal_blocked() -> None`

**Purpose:** Path traversal.

#### `def WorkspaceBoundaryTests.test_read_deep_traversal_blocked() -> None`

**Purpose:** Implements `WorkspaceBoundaryTests.test_read_deep_traversal_blocked` in `test_workspace_boundary.py`.

#### `def WorkspaceBoundaryTests.test_read_nested_traversal_blocked() -> None`

**Purpose:** Implements `WorkspaceBoundaryTests.test_read_nested_traversal_blocked` in `test_workspace_boundary.py`.

#### `def WorkspaceBoundaryTests.test_write_absolute_unix_path_blocked() -> None`

**Purpose:** Implements `WorkspaceBoundaryTests.test_write_absolute_unix_path_blocked` in `test_workspace_boundary.py`.

#### `def WorkspaceBoundaryTests.test_write_absolute_windows_path_blocked() -> None`

**Purpose:** Implements `WorkspaceBoundaryTests.test_write_absolute_windows_path_blocked` in `test_workspace_boundary.py`.

#### `def WorkspaceBoundaryTests.test_write_traversal_blocked() -> None`

**Purpose:** Implements `WorkspaceBoundaryTests.test_write_traversal_blocked` in `test_workspace_boundary.py`.

#### `def WorkspaceBoundaryTests.test_write_deep_traversal_blocked() -> None`

**Purpose:** Implements `WorkspaceBoundaryTests.test_write_deep_traversal_blocked` in `test_workspace_boundary.py`.

#### `def WorkspaceBoundaryTests.test_edit_traversal_blocked() -> None`

**Purpose:** Implements `WorkspaceBoundaryTests.test_edit_traversal_blocked` in `test_workspace_boundary.py`.

#### `def WorkspaceBoundaryTests.test_describe_traversal_blocked() -> None`

**Purpose:** Implements `WorkspaceBoundaryTests.test_describe_traversal_blocked` in `test_workspace_boundary.py`.

#### `def WorkspaceBoundaryTests.test_null_byte_in_path_blocked() -> None`

**Purpose:** Implements `WorkspaceBoundaryTests.test_null_byte_in_path_blocked` in `test_workspace_boundary.py`.

#### `def WorkspaceBoundaryTests.test_validate_rejects_unix_absolute() -> None`

**Purpose:** Absolute path rejection.

#### `def WorkspaceBoundaryTests.test_validate_rejects_windows_absolute() -> None`

**Purpose:** Implements `WorkspaceBoundaryTests.test_validate_rejects_windows_absolute` in `test_workspace_boundary.py`.

#### `def WorkspaceBoundaryTests.test_validate_rejects_workspace_root() -> None`

**Purpose:** Implements `WorkspaceBoundaryTests.test_validate_rejects_workspace_root` in `test_workspace_boundary.py`.

#### `def WorkspaceBoundaryTests.test_read_symlink_escape_blocked() -> None`

**Purpose:** read() must reject a symlink inside workspace pointing outside.

**Steps:**

1. Raise on invalid input or failure conditions.

#### `def WorkspaceBoundaryTests.test_write_symlink_escape_blocked() -> None`

**Purpose:** write() must reject writing through a symlink pointing outside.

**Steps:**

1. Raise on invalid input or failure conditions.

#### `def WorkspaceBoundaryTests.test_describe_symlink_escape_blocked() -> None`

**Purpose:** describe() must reject a symlink pointing outside.

**Steps:**

1. Raise on invalid input or failure conditions.

#### `def WorkspaceBoundaryTests.test_symlink_within_workspace_is_allowed() -> None`

**Purpose:** Symlinks pointing inside task_root should be allowed.

#### `def WorkspaceBoundaryTests.test_ls_does_not_recurse_into_symlink_directory() -> None`

**Purpose:** ls() may report a symlink but must not walk through it.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def WorkspaceBoundaryTests.test_grep_symlink_file_escape_blocked() -> None`

**Purpose:** grep() must not read through symlink files that escape task_root.

#### `def WorkspaceBoundaryTests.test_read_rejects_oversized_file_before_loading() -> None`

**Purpose:** In-container absolute path access.

#### `def WorkspaceBoundaryTests.test_grep_skips_oversized_file_before_loading() -> None`

**Purpose:** Implements `WorkspaceBoundaryTests.test_grep_skips_oversized_file_before_loading` in `test_workspace_boundary.py`.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def WorkspaceBoundaryTests.test_read_image_rejects_non_workspace_absolute_path() -> None`

**Purpose:** Implements `WorkspaceBoundaryTests.test_read_image_rejects_non_workspace_absolute_path` in `test_workspace_boundary.py`.

#### `def WorkspaceBoundaryTests.test_validate_allows_absolute_in_container() -> None`

**Purpose:** Implements `WorkspaceBoundaryTests.test_validate_allows_absolute_in_container` in `test_workspace_boundary.py`.

#### `def WorkspaceBoundaryTests.test_validate_allows_slash_tmp_in_container() -> None`

**Purpose:** Implements `WorkspaceBoundaryTests.test_validate_allows_slash_tmp_in_container` in `test_workspace_boundary.py`.

#### `def WorkspaceBoundaryTests.test_validate_still_rejects_windows_paths_in_container() -> None`

**Purpose:** Implements `WorkspaceBoundaryTests.test_validate_still_rejects_windows_paths_in_container` in `test_workspace_boundary.py`.

#### `def WorkspaceBoundaryTests.test_get_secure_task_path_returns_absolute_in_container() -> None`

**Purpose:** Implements `WorkspaceBoundaryTests.test_get_secure_task_path_returns_absolute_in_container` in `test_workspace_boundary.py`.

#### `def WorkspaceBoundaryTests.test_get_secure_task_path_normalizes_absolute_in_container() -> None`

**Purpose:** Implements `WorkspaceBoundaryTests.test_get_secure_task_path_normalizes_absolute_in_container` in `test_workspace_boundary.py`.

#### `def WorkspaceBoundaryTests.test_get_secure_task_path_relative_unchanged_in_container() -> None`

**Purpose:** Relative paths still resolve under task_root even in-container.

#### `def WorkspaceBoundaryTests.test_get_secure_task_path_accepts_legacy_upload_path_on_host() -> None`

**Purpose:** Implements `WorkspaceBoundaryTests.test_get_secure_task_path_accepts_legacy_upload_path_on_host` in `test_workspace_boundary.py`.

#### `def WorkspaceBoundaryTests.test_validate_rejects_absolute_on_host() -> None`

**Purpose:** Implements `WorkspaceBoundaryTests.test_validate_rejects_absolute_on_host` in `test_workspace_boundary.py`.

#### `def WorkspaceBoundaryTests.test_clear_workspace_does_not_touch_project_root() -> None`

**Purpose:** clear_workspace() must only clear task_root(), not workspace_root().

#### `def WorkspaceBoundaryTests.test_write_and_read_normal_path() -> None`

**Purpose:** Legitimate paths still work.

#### `def WorkspaceBoundaryTests.test_write_and_read_nested_path() -> None`

**Purpose:** Implements `WorkspaceBoundaryTests.test_write_and_read_nested_path` in `test_workspace_boundary.py`.

#### `def WorkspaceBoundaryTests.test_handle_tool_read_traversal_via_workspace_api_blocked() -> None`

**Purpose:** workspace read() with traversal path raises before reaching FS.

---

## Related

- [tests/_index](../../../_index/)
