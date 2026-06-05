---
title: "Auto-Merge Docs Workflow"
date: 2026-06-05T06:31:00Z
draft: false
description: "Added a new GitHub Actions workflow to automatically squash-merge documentation branches and reverse-sync PRs."
---

## New Features

- **[CI/CD]**: Added `.github/workflows/pr-sync-docs.yml` to automatically squash-merge Jules documentation and patchnotes branches into pull requests. This workflow also cleans up merged tracking branches and automatically reverse-syncs changes from `main` to `dev` upon merge.

## Bug Fixes

- N/A

## API Changes

- N/A

## Known Issues

- N/A
