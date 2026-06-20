---
title: "Remove legacy profile page"
date: 2026-06-08T11:18:11Z
draft: false
description: "Removed the legacy profile page, its associated styles, templates, localization keys, and documentation."
---

## New Features

- N/A

## Bug Fixes

- N/A

## API Changes

- **[UI]**: Removed the legacy `/profile/` endpoint and `ProfileView` class in `Apps/UI/views.py`.
- **[UI]**: Deleted `profile.html` template and `user.svg` icon.
- **[UI]**: Cleaned up legacy profile styles in `main.css`.
- **[UI]**: Removed related localization keys from all supported languages.
- **[Docs]**: Removed `ProfileView` documentation from `Docs/ASLM/content/docs/ASLM-Chat/Apps/UI/views.md`.

## Known Issues

- N/A
