---
title: "responses"
draft: false
---

## Module `responses`

`Tools/mcp-sandbox/supervisor/sandbox/responses.py` — ASLM Chat Python module.

---

## Classes

### `class SandboxToolError`

**Purpose:** Type `SandboxToolError` defined in `responses.py`.

---

## Public functions

#### `def SandboxToolError.__str__() -> str`

**Purpose:** Implements `SandboxToolError.__str__` in `responses.py`.

#### `def success_response(tool, result, *, warnings=…, truncated=…) -> dict[str, Any]`

**Purpose:** Wrap a successful tool result in the sandbox v2 envelope.

**Steps:**

1. Return the computed result to the caller.

#### `def error_response(tool, error_type, message, *, result=…, warnings=…, truncated=…) -> dict[str, Any]`

**Purpose:** Wrap a failed tool result in the sandbox v2 envelope.

**Steps:**

1. Return the computed result to the caller.

#### `def exception_response(tool, exc) -> dict[str, Any]`

**Purpose:** Map Python exceptions into typed sandbox v2 errors.

**Steps:**

1. Return the computed result to the caller.

---

## Related

- [sandbox/_index](../../../../_index/)
