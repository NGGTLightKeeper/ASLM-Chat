---
title: "Fix Release Workflow PR Resolution"
date: 2026-06-26T23:10:43Z
draft: false
description: "Fixes the automated release workflow to accurately resolve and extract merged Pull Requests."
---

## New Features

- N/A

## Bug Fixes

- **[CI/CD]**: Fixed the `release.yml` workflow where merged pull requests weren't correctly identified. It now correctly looks up the original commit using `github.sha^2` and reliably sorts pull requests by `merged_at` to accurately pick the last merged PR targeting the `main` branch.

## API Changes

- N/A

## Known Issues

- N/A
