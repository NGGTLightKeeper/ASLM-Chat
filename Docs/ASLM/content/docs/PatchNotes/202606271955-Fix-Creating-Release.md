---
title: "Fix Release Workflow PR Resolution Logic"
date: 2026-06-27T19:55:47Z
draft: false
description: "Fixes the automated release workflow to accurately resolve pull requests."
---

## New Features

- N/A

## Bug Fixes

- **[CI/CD]**: Improved `release.yml` logic to first extract the PR number directly from the merge commit subject, with a fallback retry mechanism using the GitHub API. This ensures the automated release correctly identifies the associated merged PR even when the API index lags.

## API Changes

- N/A

## Known Issues

- N/A
