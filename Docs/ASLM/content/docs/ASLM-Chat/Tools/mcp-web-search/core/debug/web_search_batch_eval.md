---
title: "web_search_batch_eval"
draft: false
---

## Module `web_search_batch_eval`

`Tools/mcp-web-search/core/debug/web_search_batch_eval.py` — ASLM Chat Python module.

---

## Public functions

#### `def build_parser() -> argparse.ArgumentParser`

**Purpose:** Build the batch-eval CLI argument parser.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def main(argv) -> int`

**Purpose:** CLI entry: asyncio driver for batch evaluation.

---

## Private functions

#### `def _top_pairs(mapping, limit) -> list[list[Any]]`

**Purpose:** Return top label/score pairs from a score mapping.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _class_mix(hybrid) -> dict[str, float]`

**Purpose:** Convert hybrid class mix tuples into a name→weight dict.

#### `def _weighted(values, mix, default) -> float`

**Purpose:** Weighted average of per-class values using the hybrid mix.

#### `def _trust_entry_for_url(trust_registry, url)`

**Purpose:** Look up trust registry entry by URL host pattern.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _domain_trace(url, mix) -> dict[str, Any]`

**Purpose:** Trace domain-registry scoring multipliers for one result URL.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _trust_trace(trust_registry, url, mix) -> dict[str, Any]`

**Purpose:** Trace trust-registry affinity for one result URL.

**Steps:**

1. Return the computed result to the caller.

#### `def _case_flags(expected, model_top, hybrid, rows) -> list[str]`

**Purpose:** Collect diagnostic flags when routing or previews miss expectations.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `async def _evaluate_case(case, *, query_model, source_model, model_session, service, opts, inspect_results) -> dict[str, Any]`

**Purpose:** Run live search + preview + scoring trace for one taxonomy case.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Iterate and transform or accumulate state.

#### `def _render_markdown(cases) -> str`

**Purpose:** Render batch-eval Markdown summary and per-case detail tables.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `async def _main_async(args) -> int`

**Purpose:** Run all selected taxonomy cases and write JSON/Markdown reports.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Await async I/O or subprocess work.
4. Handle errors and map them to a safe response.
5. Iterate and transform or accumulate state.
6. Parse or serialize JSON payloads.

---

## Related

- [debug/_index](../../../../_index/)
