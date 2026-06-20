---
title: "Update Localization"
date: 2026-06-13T00:44:00Z
draft: false
description: "Updates to localization strings and module manifest localization."
---

## New Features

- **[Localization]**: Added module manifest localization support via `Settings/module_manifest_locale.py` and `Settings/module_manifest_locales/`. The module settings and commands will now appear translated in the host ASLM app according to the host language.
- **[UI]**: Replaced hardcoded "Intelligence" string in `parameters-ui.js` to use the translation key `composer.intelligence`.
- **[Documentation]**: Added documentation for `module_manifest_locale` and updated `main.py` documentation.

## Bug Fixes

- **[Localization]**: Updated "Intelligence" or "Reasoning depth" translation strings to "Thinking" across all supported UI locales for better consistency.

## API Changes

- N/A

## Known Issues

- N/A
