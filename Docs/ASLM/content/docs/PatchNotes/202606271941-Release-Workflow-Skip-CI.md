---
title: "Fix Release Workflow Skip CI"
date: 2026-06-27T19:41:45Z
draft: false
description: "Fixes the automated release workflow to skip CI runs on version bump commits."
---

## New Features

- N/A

## Bug Fixes

- **[CI/CD]**: Added the `[skip ci]` marker to the automated release commit in `release.yml` to prevent redundant CI runs after the version bump.

## API Changes

- N/A

## Known Issues

- N/A
