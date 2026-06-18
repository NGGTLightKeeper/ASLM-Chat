---
title: "triage"
draft: false
---

## Module `triage`

`Tools/mcp-web-search/core/search/triage.py` — ASLM Chat Python module.

---

## Overview

Incremental, model-free SERP triage.

Sources are scored the moment they arrive from search_stream. The session decides
per source: parse now, hold in queue, or skip. Consensus votes (the same URL
surfacing from another provider family) re-score an already-seen source and may
upgrade it from the queue into a parse slot.

No registries, no models, no I/O — pure functions over SERP fields, so a decision
costs well under a millisecond.

---

## Classes

### `class TriageAction`

**Purpose:** Type `TriageAction` defined in `triage.py`.

### `class TriageDecision`

**Purpose:** Type `TriageDecision` defined in `triage.py`.

### `class _SourceState`

**Purpose:** Type `_SourceState` defined in `triage.py`.

### `class TriageSession`

**Purpose:** Type `TriageSession` defined in `triage.py`.

#### `def TriageSession.__init__(query)`

**Purpose:** Implements `TriageSession.__init__` in `triage.py`.

#### `def TriageSession.ingest_source() -> TriageDecision`

**Purpose:** Implements `TriageSession.ingest_source` in `triage.py`.

#### `def TriageSession.ingest_vote()`

**Purpose:** Implements `TriageSession.ingest_vote` in `triage.py`.

#### `def TriageSession.score_of(url) -> float`

**Purpose:** Implements `TriageSession.score_of` in `triage.py`.

---

## Related

- [core](../../_index/)
