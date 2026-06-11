---
title: "Parallel Venvs Installation"
date: 2026-06-11T16:51:55Z
draft: false
description: "Introduces parallel execution for virtual environment installation and model bootstrapping to improve startup times."
---

## New Features

- **[Installation]**: Parallelized virtual environment installation and setup (`ensure_all` in `venv_manager.py`) using `ThreadPoolExecutor`.
- **[Bootstrap]**: Parallelized the initialization tasks for web search and browser agents, including Playwright browser and Camoufox binary setup.
- **[Web Search]**: Embedding models (encoder and decoder) are now exported concurrently during bootstrapping to reduce startup latency.
- **[Documentation]**: Updated documentation for `venv_manager`, `first_run`, and `aslm_embedding_bootstrap` to reflect the new internal logic and parallel execution updates.

## Bug Fixes

- N/A

## API Changes

- **[Venv Manager]**: Added a new `log_prefix` parameter to internal logging and installation functions (`_run`, `_create_venv`, `_pip_install`, `_install_packages`, and `ensure_venv`) to support parallel log interleaving. Introduced internal `_log_message` and `_print_log` helper functions.

## Known Issues

- N/A
