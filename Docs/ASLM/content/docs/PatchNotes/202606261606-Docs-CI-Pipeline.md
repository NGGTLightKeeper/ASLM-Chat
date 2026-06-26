---
title: "Docs CI pipeline"
date: 2026-06-26T16:06:00Z
draft: false
description: "Updated CI pipelines to cap diff sizes and use temporary files for Jules prompts to avoid shell and API limits."
---

## New Features

- N/A

## Bug Fixes

- **[CI/CD]**: Fixed `jules-update-docs` and `jules-update-patchnotes` workflows by capping the sizes of `CHANGED_FILES` and `COMMIT_DIFF` to prevent exceeding Jules API and shell string limits.
- **[CI/CD]**: Updated both workflows to write the prompt to a temporary file (`$RUNNER_TEMP/jules_prompt.txt`) and read it via `jq --rawfile` instead of using multi-line GitHub Actions step outputs.

## API Changes

- N/A

## Known Issues

- N/A
