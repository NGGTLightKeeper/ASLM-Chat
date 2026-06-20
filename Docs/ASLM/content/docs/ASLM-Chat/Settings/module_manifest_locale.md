---
title: "module_manifest_locale"
draft: false
---

## Module `module_manifest_locale`

`Settings/module_manifest_locale.py` — ASLM Chat Python module.

---

## Overview

Part of `Settings`. See **Related** for package index and callers.

---

## Public functions

#### `def apply_manifest_locale(language) -> None`

**Purpose:** Patch ASLM_Module.json with localized manifest strings for the given language.

**Steps:**

1. Handle errors and map them to a safe response.
2. Parse or serialize JSON payloads.

---

## Private functions

#### `def _load_manifest_locale(language) -> dict[str, Any]`

**Purpose:** Load one manifest locale catalog from disk, falling back to English.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Parse or serialize JSON payloads.

#### `def _patch_command_list(commands, localized) -> None`

**Purpose:** Apply localized name/description fields to one command list by index.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def _patch_settings(settings, localized) -> None`

**Purpose:** Apply localized fields to manifest settings entries by setting key.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def _patch_download_categories(categories, localized) -> None`

**Purpose:** Apply localized fields to downloads bridge categories by category id.

**Steps:**

1. Iterate and transform or accumulate state.

---

## Related

- [Settings/_index](../_index/)
