---
title: "locale_catalog"
draft: false
---

## Module `locale_catalog`

`Apps/UI/locale_catalog.py` — ASLM Chat Python module.

---

## Public functions

#### `def list_available_chat_locales() -> list[str]`

**Purpose:** Return locale codes that have a catalog file on disk.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def resolve_effective_locale(host_language) -> str`

**Purpose:** Map host language to a Chat catalog file, falling back to English.

**Steps:**

1. Return the computed result to the caller.

#### `def resolve_effective_locale_from_snapshot() -> str`

**Purpose:** Resolve effective locale from snapshot.

#### `def load_catalog(locale) -> dict[str, Any]`

**Purpose:** Return merged messages for ``locale`` with English as the base layer.

**Steps:**

1. Return the computed result to the caller.

#### `def translate(key, *, locale=…, fallback=…, **params) -> str`

**Purpose:** Resolve a dot-path key with optional ``{name}`` placeholders.

**Steps:**

1. Return the computed result to the caller.

#### `def catalog_for_js(locale) -> dict[str, Any]`

**Purpose:** Return the merged catalog tree embedded in pages for client-side ``t()``.

---

## Private functions

#### `def _locale_file_path(locale) -> Path`

**Purpose:** Return the on-disk path for one locale catalog file.

#### `def _load_raw_catalog(locale) -> dict[str, Any]`

**Purpose:** Implements `_load_raw_catalog` in `locale_catalog.py`.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Parse or serialize JSON payloads.

#### `def _deep_merge(base, overlay) -> dict[str, Any]`

**Purpose:** Deep merge.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _lookup_nested(catalog, key) -> Any | None`

**Purpose:** Lookup nested.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _interpolate(template, params) -> str`

**Purpose:** Interpolate.

**Steps:**

1. Return the computed result to the caller.

---

## Related

- [UI/_index](../../_index/)
