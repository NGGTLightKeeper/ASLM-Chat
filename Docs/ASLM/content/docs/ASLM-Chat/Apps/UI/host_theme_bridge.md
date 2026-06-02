---
title: "host_theme_bridge"
draft: false
---

## Module `host_theme_bridge`

`Apps/UI/host_theme_bridge.py` — ASLM Chat Python module.

---

## Public functions

#### `def normalize_color_to_css(raw) -> str | None`

**Purpose:** Convert MAUI / ASLM hex strings to a CSS color (``#rrggbb`` or ``rgba(...)``).

**Steps:**

1. Return the computed result to the caller.

#### `def css_color_to_srgb_channels(css) -> tuple[float, float, float] | None`

**Purpose:** Parse ``#rrggbb`` (from :func:`normalize_color_to_css`) or ``rgba(r,g,b,a)`` into sRGB 0..1.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def infer_prefer_light_activity_surfaces(resolved, fallback_theme) -> bool`

**Purpose:** Choose light vs dark activity surfaces from the resolved host canvas (not only ``theme``).

**Steps:**

1. Return the computed result to the caller.

#### `def build_host_theme_template_context() -> dict[str, Any]`

**Purpose:** Return keys for ``base.html``: CSS variable block, color-scheme, optional JSON.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Private functions

#### `def _effective_theme(payload) -> str`

**Purpose:** Effective theme.

**Steps:**

1. Return the computed result to the caller.

#### `def _srgb_channel_to_linear(c) -> float`

**Purpose:** Srgb channel to linear.

#### `def _relative_luminance_srgb(r, g, b) -> float`

**Purpose:** WCAG relative luminance for sRGB channels in 0..1.

**Steps:**

1. Return the computed result to the caller.

#### `def _empty_context() -> dict[str, Any]`

**Purpose:** Empty context.

**Steps:**

1. Return the computed result to the caller.

#### `def _derived_theme_declarations(prefer_light_surfaces) -> list[str]`

**Purpose:** Return semantic UI variables that should follow the resolved host palette.

**Steps:**

1. Return the computed result to the caller.

#### `def _json_for_script_tag(value) -> str`

**Purpose:** Return JSON that is safe to embed in an application/json script tag.

**Steps:**

1. Return the computed result to the caller.
2. Parse or serialize JSON payloads.

---

## Related

- [UI/_index](../../_index/)
