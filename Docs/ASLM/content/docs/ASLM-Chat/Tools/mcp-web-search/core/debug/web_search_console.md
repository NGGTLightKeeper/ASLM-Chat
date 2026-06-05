---
title: "web_search_console"
draft: false
---

## Module `web_search_console`

`Tools/mcp-web-search/core/debug/web_search_console.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools\mcp-web-search\core\debug`. See **Related** for package index and callers.

---

## Classes

### `class _ConsoleTraceHandler`

**Purpose:** Type `_ConsoleTraceHandler` defined in `web_search_console.py`.

### `class WebSearchDebugConsole`

**Purpose:** Type `WebSearchDebugConsole` defined in `web_search_console.py`.

---

## Public functions

#### `def _ConsoleTraceHandler.emit(record) -> None`

**Purpose:** Implements `_ConsoleTraceHandler.emit` in `web_search_console.py`.

#### `def WebSearchDebugConsole.__init__(args) -> None`

**Purpose:** Wire service options and optionally load ASLM embedding models.

#### `def WebSearchDebugConsole.close() -> None`

**Purpose:** Release the model session and clear model handles.

#### `async def WebSearchDebugConsole.run_query(raw_query) -> None`

**Purpose:** Run one query: classify, search, fetch previews, and print trace JSON.

**Steps:**

1. Await async I/O or subprocess work.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.
4. Parse or serialize JSON payloads.

#### `def WebSearchDebugConsole.set_option(key, value) -> None`

**Purpose:** Update a runtime console flag from a :set command.

#### `def build_parser() -> argparse.ArgumentParser`

**Purpose:** Build the web_search debug console CLI argument parser.

**Steps:**

1. Return the computed result to the caller.

#### `def main(argv) -> int`

**Purpose:** CLI entry: asyncio driver for the debug console.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

---

## Private functions

#### `def _install_trace_logging() -> None`

**Purpose:** Attach a stdout handler to trace.web_search when --trace is set.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def _domain_from_url(url) -> str`

**Purpose:** Strip www. prefix from URL host for display.

#### `def _trust_entry_for_url(trust_registry, url)`

**Purpose:** Look up trust registry entry by URL host pattern.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _class_mix(hybrid) -> dict[str, float]`

**Purpose:** Convert hybrid class mix tuples into a name→weight dict.

#### `def _weighted_map_value(values, class_mix, default) -> float`

**Purpose:** Weighted average of per-class values using the hybrid mix.

#### `def _domain_debug(url, class_mix) -> dict[str, Any]`

**Purpose:** Build domain-registry debug payload for one result URL.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _trust_debug(trust_registry, url, class_mix) -> dict[str, Any]`

**Purpose:** Build trust-registry debug payload for one result URL.

**Steps:**

1. Return the computed result to the caller.

#### `def _print_json(title, value) -> None`

**Purpose:** Pretty-print a titled JSON block to stdout.

#### `def _top_pairs(mapping, limit) -> list[list[Any]]`

**Purpose:** Return top label/score pairs from a score mapping.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def WebSearchDebugConsole._load_models() -> None`

**Purpose:** Open a SearchModelSession and bind encoder/decoder handles.

#### `async def _main_async(args) -> int`

**Purpose:** REPL loop or single --once query, then tear down the console.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

---

## Related

- [debug/_index](../../../../_index/)
