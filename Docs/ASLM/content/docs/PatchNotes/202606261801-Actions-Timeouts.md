---
title: "GitHub Actions Updates and Timeout Increases"
date: 2026-06-26T18:01:19Z
draft: false
description: "Updates GitHub Actions versions and increases pipeline timeouts to prevent CI build failures."
---

## New Features

- N/A

## Bug Fixes

- **[CI/CD]**: Updated various GitHub Actions dependencies to their latest versions, including `actions/checkout@v7`, `actions/github-script@v9`, and `actions/cache@v6` across multiple workflows.
- **[CI/CD]**: Increased job `timeout-minutes` from 5 to 10 for Django tests (`Apps.Data`, `Apps.UI`), Tools tests, and the Hugo build job to prevent intermittent build timeouts.

## API Changes

- N/A

## Known Issues

- N/A
