---
title: "Auto Release Workflow"
date: 2026-06-26T21:33:00Z
draft: false
description: "Introduced a new GitHub Actions workflow to automate release generation, tagging, and versioning based on PR titles."
---

## New Features

- **[CI/CD]**: Added a new GitHub Actions workflow (`release.yml`) to automatically manage versioning, tagging, and GitHub Release creation driven by pull request titles.
- **[CI/CD]**: Integrated automatic `ASLM_Module.json` updates to synchronize module versions with the release tags generated during merge to main.

## Bug Fixes

- N/A

## API Changes

- N/A

## Known Issues

- N/A
