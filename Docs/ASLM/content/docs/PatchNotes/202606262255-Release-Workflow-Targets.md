---
title: "Release Workflow Targets Update"
date: 2026-06-26T22:55:22Z
draft: false
description: "Updates the release workflow to trigger releases on pushes to main instead of closed pull requests."
---

## New Features

- N/A

## Bug Fixes

- **[CI/CD]**: Updated the release workflow to separate tasks by event triggers, using `pull_request` for staging versions and `push` to `main` for the release process.
- **[CI/CD]**: Added a step to resolve merged PR information for the corresponding commit during a push event using the GitHub API.

## API Changes

- N/A

## Known Issues

- N/A
