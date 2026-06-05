---
title: "test_destructive_container_resilience"
draft: false
---

## Module `test_destructive_container_resilience`

`Tools/mcp-sandbox/tests/test_destructive_container_resilience.py` — ASLM Chat Python module.

---

## Classes

### `class DisposableSandbox`

**Purpose:** Type `DisposableSandbox` defined in `test_destructive_container_resilience.py`.

---

## Test methods

#### `def DisposableSandbox.__init__() -> None`

**Purpose:** Implements `DisposableSandbox.__init__` in `test_destructive_container_resilience.py`.

#### `def DisposableSandbox.run(args, *, timeout=…, check=…) -> subprocess.CompletedProcess[str]`

**Purpose:** Implements `DisposableSandbox.run` in `test_destructive_container_resilience.py`.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Spawn or communicate with a child process.

#### `def DisposableSandbox.start() -> None`

**Purpose:** Implements `DisposableSandbox.start` in `test_destructive_container_resilience.py`.

#### `def DisposableSandbox.exec(script, *, user=…, workdir=…, timeout=…, check=…) -> subprocess.CompletedProcess[str]`

**Purpose:** Implements `DisposableSandbox.exec` in `test_destructive_container_resilience.py`.

**Steps:**

1. Return the computed result to the caller.
2. Spawn or communicate with a child process.

#### `def DisposableSandbox.cleanup() -> None`

**Purpose:** Implements `DisposableSandbox.cleanup` in `test_destructive_container_resilience.py`.

#### `def test_disposable_container_survives_escalating_destructive_actions() -> None`

**Purpose:** Escalate ordinary-to-destructive actions inside a disposable sandbox container.

---

## Private functions

#### `def _healthcheck(container, *, check=…) -> subprocess.CompletedProcess[str]`

**Purpose:** Implements `_healthcheck` in `test_destructive_container_resilience.py`.

**Steps:**

1. Return the computed result to the caller.
2. Spawn or communicate with a child process.

---

## Related

- [tests/_index](../../../_index/)
