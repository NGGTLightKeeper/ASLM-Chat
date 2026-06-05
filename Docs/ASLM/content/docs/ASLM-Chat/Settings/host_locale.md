---
title: "host_locale"
draft: false
---

## Module `host_locale`

`Settings/host_locale.py` — ASLM Chat Python module.

---

## Public functions

#### `def atomic_write_json(path, data) -> None`

**Purpose:** Write JSON atomically via a temporary file and replace on success.

**Steps:**

1. Handle errors and map them to a safe response.

#### `def save_host_locale_payload(data) -> None`

**Purpose:** Persist the ASLM host locale snapshot next to module settings.

#### `def load_host_locale() -> dict[str, Any] | None`

**Purpose:** Load the last persisted host locale snapshot, or None when missing or invalid.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Parse or serialize JSON payloads.

#### `def normalize_host_language(value) -> str`

**Purpose:** Normalize a host language code to a supported value, defaulting to English.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def get_language() -> str`

**Purpose:** Return the BCP-47 language code from the host locale snapshot.

**Steps:**

1. Return the computed result to the caller.

#### `def get_display_name() -> str | None`

**Purpose:** Return the host-provided display name for the current language, when available.

**Steps:**

1. Return the computed result to the caller.

---

## Related

- [Settings/_index](../_index/)
