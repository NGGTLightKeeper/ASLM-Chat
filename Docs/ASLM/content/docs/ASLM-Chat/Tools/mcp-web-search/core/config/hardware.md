---
title: "hardware"
draft: false
---

## Module `hardware`

`Tools/mcp-web-search/core/config/hardware.py` — ASLM Chat Python module.

---

## Public functions

#### `def detect_hardware_profile() -> str`

**Purpose:** Probe GPU VRAM once and return full_gpu, partial_gpu, or cpu_safe.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def get_hardware_profile() -> str`

**Purpose:** Return cached hardware profile (probed once per process).

**Steps:**

1. Return the computed result to the caller.

---

## Related

- [config/_index](../../../../_index/)
