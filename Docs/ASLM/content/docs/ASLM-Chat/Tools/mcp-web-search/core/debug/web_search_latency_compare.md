---
title: "web_search_latency_compare"
draft: false
---

## Module `web_search_latency_compare`

`Tools/mcp-web-search/core/debug/web_search_latency_compare.py` — ASLM Chat Python module.

---

## Public functions

#### `def build_parser() -> argparse.ArgumentParser`

**Purpose:** Build the latency-compare CLI argument parser.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def main() -> int`

**Purpose:** CLI entry: asyncio driver for latency comparison.

---

## Private functions

#### `def _percentile(values, pct) -> float`

**Purpose:** Compute a percentile from sorted elapsed-time samples.

**Steps:**

1. Return the computed result to the caller.

#### `async def _run_one(query, *, pipeline, args) -> dict[str, Any]`

**Purpose:** Run one live web_search_rich call under a temporary pipeline env override.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

#### `async def _run_pipeline(pipeline, queries, args) -> list[dict[str, Any]]`

**Purpose:** Benchmark every query for one pipeline across repeated runs.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Iterate and transform or accumulate state.

#### `def _summary(rows) -> dict[str, Any]`

**Purpose:** Aggregate mean/median/p90 timing stats per pipeline.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _render_markdown(rows) -> str`

**Purpose:** Render a Markdown table report from benchmark rows.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `async def _main_async(args) -> int`

**Purpose:** Run all pipelines, then write JSON and Markdown reports under output_dir.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Iterate and transform or accumulate state.
4. Parse or serialize JSON payloads.

---

## Related

- [debug/_index](../../../../_index/)
