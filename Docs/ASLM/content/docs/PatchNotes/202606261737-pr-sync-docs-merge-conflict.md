---
title: "Update pr-sync-docs.yml to handle merge conflicts"
date: 2026-06-26T17:37:00Z
draft: false
description: "Gracefully handle squash merge conflicts by dropping the branch."
---

## New Features

- N/A

## Bug Fixes

- **[CI/CD]**: Updated `.github/workflows/pr-sync-docs.yml` to gracefully handle squash merge conflicts during branch syncing. Instead of failing the workflow, the script will now abort the merge (`git merge --abort`), clean the repository state (`git reset --hard HEAD` and `git clean -fd`), emit a warning, and continue with the remaining branches.

## API Changes

- N/A

## Known Issues

- N/A
