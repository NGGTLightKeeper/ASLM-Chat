---
title: "Interactive Dialogs"
date: 2026-06-17T17:48:21Z
draft: false
description: "Replaced native browser dialogs with custom interactive async UI dialogs."
---

## New Features

- **[UI]**: Replaced native browser dialogs (`window.prompt`, `window.confirm`, `window.alert`) with a new set of custom interactive asynchronous dialogs (`confirmDialog`, `textDialog`, `messageDialog`) in `dialogs.js`.
- **[UI]**: Updated multiple components (`chat-controller.js`, `engine-manager.js`, `parameters-ui.js`, `skills-ui.js`) to seamlessly integrate the new async dialog workflows for user actions such as renaming, deleting, and parameter validation.
- **[Styling]**: Added new CSS styles in `main.css` for the unified `aslm-dialog` components, including backdrops, inputs, and action buttons.
- **[Localization]**: Updated multiple language JSON files (`ar`, `de`, `en`, `es`, `fr`, `hi`, `id`, `it`, `ja`, `ko`, `nl`, `pl`, `pt-BR`, `pt`, `ru`, `tr`, `uk`, `vi`, `zh-Hans`, `zh-Hant`) to support translations for the new dialog interfaces (e.g., Ok, Cancel, Confirm, Input, Value is required).
- **[Documentation]**: Added documentation for the new UI scripts (`dialogs.md`) and updated references within the `_index.md` and `skills-ui.md` files in `Docs/ASLM/content/docs/ASLM-Chat/Apps/UI/static/js/ui/`.

## Bug Fixes

- N/A

## API Changes

- N/A

## Known Issues

- N/A
