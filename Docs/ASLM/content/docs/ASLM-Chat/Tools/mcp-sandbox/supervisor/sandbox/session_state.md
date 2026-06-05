---
title: "session_state"
draft: false
---

## Module `session_state`

`Tools/mcp-sandbox/supervisor/sandbox/session_state.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools\mcp-sandbox\supervisor\sandbox`. See **Related** for package index and callers.

---

## Classes

### `class ExplorationState`

**Purpose:** Type `ExplorationState` defined in `session_state.py`.

---

## Public functions

#### `def ExplorationState.record_touch(path, intent, window, representation) -> None`

**Purpose:** Record that a path was accessed with a given intent.

#### `def ExplorationState.record_search(pattern, path, hit_count) -> None`

**Purpose:** Record a search query.

#### `def ExplorationState.record_survey(data) -> None`

**Purpose:** Cache a repo survey result.

#### `def ExplorationState.invalidate_survey_cache() -> None`

**Purpose:** Invalidate the survey cache after a filesystem mutation.

#### `def ExplorationState.should_break_loop(path, intent, threshold) -> bool`

**Purpose:** Return True when the same intent+path has been hit too many times.

**Steps:**

1. Return the computed result to the caller.

#### `def ExplorationState.get_read_overlap(path, start_line, end_line) -> float`

**Purpose:** Return fraction of [start, end] already covered by prior reads.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def ExplorationState.get_best_representation(path, intent) -> str`

**Purpose:** Suggest the next representation to serve for this path. If the model has already seen "raw" multiple times, switch to "map". If it has seen "map", switch to "outline" or "search_hits".

**Steps:**

1. Return the computed result to the caller.

#### `def ExplorationState.has_survey_cache(max_age_s) -> bool`

**Purpose:** Return True if a recent survey is cached.

#### `def ExplorationState.get_unread_windows(path, total_lines, min_gap) -> list[tuple[int, int]]`

**Purpose:** Return contiguous unread line ranges for a file.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def ExplorationState.compact_context(max_items) -> str | None`

**Purpose:** Build a compact exploration summary for injection into responses. Returns None if the state is too sparse to be useful.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def ExplorationState.update_task_cwd(final_cwd_container) -> bool`

**Purpose:** Update task_cwd if final_cwd is inside task_root. final_cwd_container: absolute container path from bash wrapper (e.g. '/workspace/_sandbox/src'). Returns True if task_cwd was updated, False if it stayed the same.

**Steps:**

1. Return the computed result to the caller.

#### `def ExplorationState.get_effective_cwd(explicit_cwd) -> str`

**Purpose:** Resolve the effective cwd for a bash command. Contract: cwd absent or None → use persisted task_cwd; cwd == "." → use persisted task_cwd; cwd == explicit → one-shot override (does not mutate state).

#### `def ExplorationState.format_execution_ended_in(final_cwd_container) -> str | None`

**Purpose:** Format execution_ended_in for display. Returns None if the command stayed in task_cwd (no need to show). Returns relative path if inside task-space. Returns 'container:/path' if outside task-space.

**Steps:**

1. Return the computed result to the caller.

#### `def get_session_state() -> ExplorationState`

**Purpose:** Return the current session state, creating it if needed.

**Steps:**

1. Return the computed result to the caller.

#### `def reset_session_state() -> None`

**Purpose:** Reset the session state (for testing).

---

## Private functions

#### `def _trim_dict_oldest(mapping, max_items) -> None`

**Purpose:** Keep singleton state bounded during long-lived supervisor sessions.

**Steps:**

1. Iterate and transform or accumulate state.

---

## Related

- [sandbox/_index](../../../../_index/)
