---
title: "mcp_contract"
draft: false
---

## Module `mcp_contract`

`Tools/mcp-web-search/core/mcp_contract.py` — ASLM Chat Python module.

---

## Overview

Model-facing MCP contract for the search tools (ported from the legacy adapter).

Two things the model sees: the parameter SCHEMA and the tool DESCRIPTIONS. Both are
instructions, not mechanics — the model is told *how to drive* the tool, never how the
pipeline works internally. The schema is deliberately minimal: the model controls only
the query, the effort, and the shopping opt-in. Region routing, recency/timelimit (parsed
from the query), safe-search and engine selection are all decided internally and are not
model-facing knobs.

---

## Public functions

#### `def sanitize_query(query) -> str`

**Purpose:** Implements `sanitize_query` in `mcp_contract.py`.

#### `def coerce_search_query(value) -> str`

**Purpose:** Implements `coerce_search_query` in `mcp_contract.py`.

#### `def coerce_search_effort(value) -> str`

**Purpose:** Implements `coerce_search_effort` in `mcp_contract.py`.

#### `def coerce_search_shopping(value) -> bool`

**Purpose:** Implements `coerce_search_shopping` in `mcp_contract.py`.

---

## Private functions

#### `def _try_parse_json(value) -> Any`

**Purpose:** Implements `_try_parse_json` in `mcp_contract.py`.

---

## Related

- [core](../../_index/)
