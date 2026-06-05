---
title: "test_cwd_contract"
draft: false
---

## Module `test_cwd_contract`

`Tools/mcp-sandbox/tests/test_cwd_contract.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools\mcp-sandbox\tests`. See **Related** for package index and callers.

---

## Classes

### `class CwdContractTests`

**Purpose:** Type `CwdContractTests` defined in `test_cwd_contract.py`.

---

## Test methods

#### `def CwdContractTests.setUp() -> None`

**Purpose:** Implements `CwdContractTests.setUp` in `test_cwd_contract.py`.

**Steps:**

1. Handle errors and map them to a safe response.
2. Iterate and transform or accumulate state.

#### `def CwdContractTests.test_pwd_at_root_reports_task_root() -> None`

**Purpose:** pwd reports correct container path.

#### `def CwdContractTests.test_pwd_with_subdir_cwd_reports_subdir() -> None`

**Purpose:** Implements `CwdContractTests.test_pwd_with_subdir_cwd_reports_subdir` in `test_cwd_contract.py`.

#### `def CwdContractTests.test_routed_command_respects_explicit_cwd() -> None`

**Purpose:** cwd argument is respected.

#### `def CwdContractTests.test_cwd_returned_matches_input_cwd() -> None`

**Purpose:** Implements `CwdContractTests.test_cwd_returned_matches_input_cwd` in `test_cwd_contract.py`.

#### `def CwdContractTests.test_none_cwd_defaults_to_root() -> None`

**Purpose:** Passing cwd=None should be treated as '.'.

#### `def CwdContractTests.test_cat_container_absolute_path_falls_through() -> None`

**Purpose:** `cat /etc/os-release` must NOT be handled by the workspace controller.

#### `def CwdContractTests.test_ls_container_absolute_path_falls_through() -> None`

**Purpose:** `ls /usr/bin` must fall through to real bash.

#### `def CwdContractTests.test_cd_slash_does_not_affect_next_call_cwd() -> None`

**Purpose:** `cd / && ls` goes to real bash; next call still uses task_cwd.

#### `def CwdContractTests.test_consecutive_routed_calls_use_explicit_cwd() -> None`

**Purpose:** Each call is independent; cwd comes from the argument, not session.

#### `def CwdContractTests.test_cwd_subdir_resolves_correctly() -> None`

**Purpose:** Passing cwd='src/lib' resolves path inside task_root.

#### `def CwdContractTests.test_cwd_traversal_is_blocked() -> None`

**Purpose:** cwd='../../etc' must not allow reading outside task_root.

---

## Private functions

#### `def _mock_exec(stdout, stderr, exit_code, cwd)`

**Purpose:** Build a fake exec_bash return value.

**Steps:**

1. Return the computed result to the caller.

---

## Related

- [tests/_index](../../../_index/)
