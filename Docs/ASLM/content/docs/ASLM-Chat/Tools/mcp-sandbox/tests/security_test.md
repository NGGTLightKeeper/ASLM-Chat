---
title: "security_test"
draft: false
---

## Module `security_test`

`Tools/mcp-sandbox/tests/security_test.py` — ASLM Chat Python module.

---

## Test methods

#### `def print_group(title) -> None`

**Purpose:** Print a formatted group header.

#### `def check(name, *, expect_raise, fn, notes=…) -> bool`

**Purpose:** Run a check and record whether it raised as expected.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Handle errors and map them to a safe response.

#### `def docker_exec(cmd, check_output) -> tuple[int, str, str]`

**Purpose:** Run a command inside the sandbox container.

**Steps:**

1. Return the computed result to the caller.
2. Spawn or communicate with a child process.

---

## Related

- [tests/_index](../../../_index/)
