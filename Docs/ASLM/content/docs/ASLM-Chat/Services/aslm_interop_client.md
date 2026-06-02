---
title: "aslm_interop_client"
draft: false
---

## Module `aslm_interop_client`

`Services/aslm_interop_client.py` — ASLM Chat Python module.

---

## Public functions

#### `def get_registry() -> dict[str, Any]`

**Purpose:** Fetch installed and running modules from GET /v1/registry.

#### `def request_start(*, caller_module_id, module_ids) -> dict[str, Any]`

**Purpose:** Ask ASLM to start the given module ids via POST /v1/modules/start.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Handle errors and map them to a safe response.
4. Parse or serialize JSON payloads.

---

## Private functions

#### `def _base_url() -> str`

**Purpose:** Resolve the ASLM host module interop base URL from the environment.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.

---

## Related

- [Services/_index](../_index/)
