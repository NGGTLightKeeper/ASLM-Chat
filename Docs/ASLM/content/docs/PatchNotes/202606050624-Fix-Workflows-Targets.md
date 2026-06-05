---
title: "Fix Workflows Targets"
date: 2026-06-05T06:24:00Z
draft: false
description: "Updated CI/CD workflows to optimize triggers and exclude automated branches from tests."
---

## New Features

- N/A

## Bug Fixes

- **[CI/CD]**: Optimized GitHub Actions workflows to reduce redundant runs. Test pipelines (Django, Docs, Tools) now ignore `jules-docs-dev-*` and `jules-patchnotes-dev-*` branches on push.
- **[CI/CD]**: Removed `issues` event triggers from test workflows and removed `edited` and `reopened` triggers from `jules-remove-pr`.
- **[CI/CD]**: Updated `jules-update-docs` to ignore commits from `github-actions[bot]` instead of checking commit message prefixes, and removed the prefix check from `jules-update-patchnotes`.

## API Changes

- N/A

## Known Issues

- N/A
