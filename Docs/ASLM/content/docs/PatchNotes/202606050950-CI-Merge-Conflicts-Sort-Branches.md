---
title: "CI Merge Conflicts & Sort Branches"
date: 2026-06-05T09:50:08Z
draft: false
description: "Fixed merge conflicts and sorted branches in the PR sync docs workflow."
---

## New Features

- N/A

## Bug Fixes

- **[CI]**: Updated `.github/workflows/pr-sync-docs.yml` to sort PR sync branches chronologically (oldest to newest) to prevent out-of-order merging.
- **[CI]**: Modified the PR merge strategy to use `git merge --squash -X theirs` to automatically resolve potential conflicts by favoring the incoming documentation branch.

## API Changes

- N/A

## Known Issues

- N/A
