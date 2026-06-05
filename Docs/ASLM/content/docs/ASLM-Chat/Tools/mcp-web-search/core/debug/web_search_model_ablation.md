---
title: "web_search_model_ablation"
draft: false
---

## Module `web_search_model_ablation`

`Tools/mcp-web-search/core/debug/web_search_model_ablation.py` — ASLM Chat Python module.

---

## Public functions

#### `def build_parser() -> argparse.ArgumentParser`

**Purpose:** Build the model-ablation CLI argument parser.

**Steps:**

1. Return the computed result to the caller.

#### `def main() -> int`

**Purpose:** CLI entry: asyncio driver for model ablation benchmarks.

---

## Private functions

#### `def _summary(rows) -> dict[str, Any]`

**Purpose:** Aggregate timing stats grouped by ablation mode name.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _render_ablation_markdown(rows, modes) -> str`

**Purpose:** Render ablation-specific Markdown (mode column instead of pipeline).

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `async def _run_mode(mode, meta, queries, args) -> list[dict[str, Any]]`

**Purpose:** Run one ablation mode across queries with encoder/decoder env toggles.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Iterate and transform or accumulate state.

#### `async def _main_async(args) -> int`

**Purpose:** Execute selected ablation modes and write JSON/Markdown reports.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Await async I/O or subprocess work.
4. Iterate and transform or accumulate state.
5. Parse or serialize JSON payloads.

---

## Related

- [debug/_index](../../../../_index/)
