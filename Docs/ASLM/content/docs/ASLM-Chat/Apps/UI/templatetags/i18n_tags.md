---
title: "i18n_tags"
draft: false
---

## Module `i18n_tags`

`Apps/UI/templatetags/i18n_tags.py` — ASLM Chat Python module.

---

## Public functions

#### `def append_static_cache_version(url) -> str`

**Purpose:** Implements `append_static_cache_version` in `i18n_tags.py`.

#### `def static(path) -> str`

**Purpose:** Resolve a static asset URL with the per-process cache-bust query.

#### `def t(context, key) -> str`

**Purpose:** Translate ``key`` using the effective locale from template context.

**Steps:**

1. Return the computed result to the caller.

#### `def t_param(context, key, **kwargs) -> str`

**Purpose:** Translate ``key`` with ``{name}`` placeholders.

**Steps:**

1. Return the computed result to the caller.

---

## Related

- [templatetags/_index](../../../_index/)
