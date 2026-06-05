---
title: "Fix pr-sync-docs.yml"
date: 2026-06-05T10:05:02Z
draft: false
description: "Fix for the pr-sync-docs.yml workflow."
---

## New Features

- N/A

## Bug Fixes

- **[CI/CD]**: Fixed an issue in `.github/workflows/pr-sync-docs.yml` regarding sync and deletion of documentation and patchnotes branches. Refactored logic to better track related branches using basehead comparisons and to delete matched documentation branches once merged. Also resolved issues with orphan patchnotes branches and their merging process. Added proper handling for merging and squash-merging tracked branches.

## API Changes

- N/A

## Known Issues

- N/A
