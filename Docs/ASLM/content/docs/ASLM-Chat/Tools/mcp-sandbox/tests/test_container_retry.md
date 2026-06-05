---
title: "test_container_retry"
draft: false
---

## Module `test_container_retry`

`Tools/mcp-sandbox/tests/test_container_retry.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools\mcp-sandbox\tests`. See **Related** for package index and callers.

---

## Classes

### `class TestInspectContainer`

**Purpose:** Type `TestInspectContainer` defined in `test_container_retry.py`.

### `class TestForceRemove`

**Purpose:** Type `TestForceRemove` defined in `test_container_retry.py`.

### `class TestStartExisting`

**Purpose:** Type `TestStartExisting` defined in `test_container_retry.py`.

### `class TestBuildRunCommand`

**Purpose:** Type `TestBuildRunCommand` defined in `test_container_retry.py`.

### `class TestEnsureImage`

**Purpose:** Type `TestEnsureImage` defined in `test_container_retry.py`.

### `class TestEnsureContainerRunning`

**Purpose:** Type `TestEnsureContainerRunning` defined in `test_container_retry.py`.

---

## Test methods

#### `def TestInspectContainer.test_returns_none_when_container_missing() -> None`

**Purpose:** Implements `TestInspectContainer.test_returns_none_when_container_missing` in `test_container_retry.py`.

#### `def TestInspectContainer.test_returns_running_true_when_up() -> None`

**Purpose:** Implements `TestInspectContainer.test_returns_running_true_when_up` in `test_container_retry.py`.

**Steps:**

1. Parse or serialize JSON payloads.

#### `def TestInspectContainer.test_detects_volume_mismatch() -> None`

**Purpose:** Implements `TestInspectContainer.test_detects_volume_mismatch` in `test_container_retry.py`.

**Steps:**

1. Parse or serialize JSON payloads.

#### `def TestInspectContainer.test_returns_none_on_invalid_json() -> None`

**Purpose:** Implements `TestInspectContainer.test_returns_none_on_invalid_json` in `test_container_retry.py`.

#### `def TestForceRemove.test_success() -> None`

**Purpose:** Implements `TestForceRemove.test_success` in `test_container_retry.py`.

#### `def TestForceRemove.test_already_gone_is_ok() -> None`

**Purpose:** Implements `TestForceRemove.test_already_gone_is_ok` in `test_container_retry.py`.

#### `def TestForceRemove.test_real_error_returns_false() -> None`

**Purpose:** Implements `TestForceRemove.test_real_error_returns_false` in `test_container_retry.py`.

#### `def TestStartExisting.test_returns_true_when_container_running_after_start() -> None`

**Purpose:** Implements `TestStartExisting.test_returns_true_when_container_running_after_start` in `test_container_retry.py`.

**Steps:**

1. Parse or serialize JSON payloads.

#### `def TestStartExisting.test_returns_false_when_start_fails() -> None`

**Purpose:** Implements `TestStartExisting.test_returns_false_when_start_fails` in `test_container_retry.py`.

#### `def TestStartExisting.test_returns_false_when_not_running_after_start() -> None`

**Purpose:** docker start returns 0 but container dies immediately.

**Steps:**

1. Parse or serialize JSON payloads.

#### `def TestBuildRunCommand.test_mounts_task_root_under_workspace_sandbox() -> None`

**Purpose:** Implements `TestBuildRunCommand.test_mounts_task_root_under_workspace_sandbox` in `test_container_retry.py`.

#### `def TestBuildRunCommand.test_no_supervisor_source_mount_by_default() -> None`

**Purpose:** Without SANDBOX_DEV_BIND=1 the src tree must NOT be bind-mounted.

#### `def TestBuildRunCommand.test_mounts_supervisor_source_read_only_when_dev_bind_enabled() -> None`

**Purpose:** With SANDBOX_DEV_BIND=1 the src tree is bind-mounted read-only.

#### `def TestBuildRunCommand.test_adds_read_only_linux_venv_mount_when_dev_bind_enabled() -> None`

**Purpose:** Implements `TestBuildRunCommand.test_adds_read_only_linux_venv_mount_when_dev_bind_enabled` in `test_container_retry.py`.

#### `def TestBuildRunCommand.test_no_venv_mount_without_dev_bind() -> None`

**Purpose:** Without SANDBOX_DEV_BIND=1 the venv must NOT be bind-mounted.

#### `def TestBuildRunCommand.test_rejects_windows_venv_mount() -> None`

**Purpose:** Implements `TestBuildRunCommand.test_rejects_windows_venv_mount` in `test_container_retry.py`.

#### `def TestEnsureImage.test_existing_image_with_runtime_label_is_reused() -> None`

**Purpose:** Implements `TestEnsureImage.test_existing_image_with_runtime_label_is_reused` in `test_container_retry.py`.

**Steps:**

1. Parse or serialize JSON payloads.

#### `def TestEnsureImage.test_existing_stale_image_without_runtime_label_is_rebuilt() -> None`

**Purpose:** Implements `TestEnsureImage.test_existing_stale_image_without_runtime_label_is_rebuilt` in `test_container_retry.py`.

**Steps:**

1. Return the computed result to the caller.
2. Parse or serialize JSON payloads.
3. Spawn or communicate with a child process.

#### `def TestEnsureContainerRunning.test_returns_true_when_already_running_correct_volume() -> None`

**Purpose:** Implements `TestEnsureContainerRunning.test_returns_true_when_already_running_correct_volume` in `test_container_retry.py`.

**Steps:**

1. Parse or serialize JSON payloads.

#### `def TestEnsureContainerRunning.test_recreates_container_on_volume_mismatch() -> None`

**Purpose:** If volume is wrong, old container is removed and a new one created.

**Steps:**

1. Return the computed result to the caller.
2. Parse or serialize JSON payloads.

#### `def TestEnsureContainerRunning.test_retries_on_name_conflict() -> None`

**Purpose:** Name-conflict error during create triggers a retry.

**Steps:**

1. Return the computed result to the caller.
2. Parse or serialize JSON payloads.

#### `def TestEnsureContainerRunning.test_concurrent_calls_serialized() -> None`

**Purpose:** Concurrent _ensure_container_running calls must not race each other.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

---

## Private functions

#### `def _ok(stdout, stderr) -> MagicMock`

**Purpose:** Build a fake subprocess result with returncode 0.

**Steps:**

1. Return the computed result to the caller.

#### `def _fail(stderr, returncode) -> MagicMock`

**Purpose:** Build a fake subprocess result with non-zero returncode.

**Steps:**

1. Return the computed result to the caller.

#### `def TestEnsureContainerRunning._mock_docker_ok() -> MagicMock`

**Purpose:** Simulate _ensure_docker_running returning True.

---

## Related

- [tests/_index](../../../_index/)
