---
title: "Automate Removal of Jules PRs"
date: 2026-06-04T02:50:00Z
draft: false
description: "Added a workflow to automatically close pull requests created for Jules automation branches."
---

## New Features

- **[CI/CD]**: Added a new GitHub Actions workflow (`jules-remove-pr.yml`) that automatically closes PRs created from `jules-docs-dev-*` and `jules-patchnotes-dev-*` branches, as these branches are merged by the Jules automation pipeline and do not require an open PR.

## Bug Fixes

- N/A

## API Changes

- N/A

## Known Issues

- N/A
