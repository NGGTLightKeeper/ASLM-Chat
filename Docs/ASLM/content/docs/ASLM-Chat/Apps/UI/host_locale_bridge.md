---
title: "host_locale_bridge"
draft: false
---

## Module `host_locale_bridge`

`Apps/UI/host_locale_bridge.py` — ASLM Chat Python module.

---

## Public functions

#### `def is_rtl_language(language_code) -> bool`

**Purpose:** Return whether the UI should use right-to-left layout.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def language_to_html_lang(language_code) -> str`

**Purpose:** Convert BCP-47 to a value suitable for the HTML ``lang`` attribute.

**Steps:**

1. Return the computed result to the caller.

#### `def build_host_locale_template_context() -> dict[str, Any]`

**Purpose:** Return keys for ``base.html`` and the client locale bootstrap.

**Steps:**

1. Return the computed result to the caller.

---

## Private functions

#### `def _json_for_script_tag(value) -> str`

**Purpose:** Escape JSON before embedding it in a script tag.

**Steps:**

1. Return the computed result to the caller.
2. Parse or serialize JSON payloads.

---

## Related

- [UI/_index](../../_index/)
