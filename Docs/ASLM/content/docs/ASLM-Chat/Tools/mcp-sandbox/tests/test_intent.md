---
title: "test_intent"
draft: false
---

## Module `test_intent`

`Tools/mcp-sandbox/tests/test_intent.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools\mcp-sandbox\tests`. See **Related** for package index and callers.

---

## Test methods

#### `def test_open_variants()`

**Purpose:** All read-like commands classify as OPEN.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def test_open_line_ranges()`

**Purpose:** head/tail/sed extract line ranges.

#### `def test_locate_variants()`

**Purpose:** All search commands classify as LOCATE.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def test_survey_variants()`

**Purpose:** ls/tree/find classify as SURVEY.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def test_compound_cat_head()`

**Purpose:** cat file | head -n 20 → OPEN with line range.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def test_compound_cat_grep()`

**Purpose:** cat file | grep pattern → LOCATE.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def test_compound_head_grep()`

**Purpose:** head -n 50 file | grep pattern → LOCATE.

#### `def test_run_commands_return_none()`

**Purpose:** Execution commands return None (→ real bash).

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def test_chains_return_none()`

**Purpose:** &&, ||, ;, subshells, redirections → None (real bash).

**Steps:**

1. Iterate and transform or accumulate state.

#### `def test_locate_case_sensitivity()`

**Purpose:** grep -i → case_sensitive=False.

#### `def test_locate_rg_type_flag()`

**Purpose:** rg --type py → glob_pattern=*.py.

#### `def test_find_carries_name_and_type()`

**Purpose:** find -name '*.py' -type f → NormalizedCommand with name_pattern/find_type.

#### `def test_grep_context_carried()`

**Purpose:** grep -C 2 pattern file → context_before/after = 2.

#### `def test_ls_la_includes_hidden()`

**Purpose:** ls -la and combined short flags must enable include_hidden.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def test_du_falls_through_to_bash()`

**Purpose:** du is NOT routed as a directory listing — must reach real bash.

#### `def test_find_unsupported_flags_fall_back()`

**Purpose:** find with -exec / -mtime / etc. must fall back to real bash.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def test_grep_files_with_matches()`

**Purpose:** grep -l changes output format to filenames — not implemented, fall back to bash.

#### `def test_grep_inverted_falls_back()`

**Purpose:** grep -v changes semantics — fall back to real bash.

---

## Related

- [tests/_index](../../../_index/)
