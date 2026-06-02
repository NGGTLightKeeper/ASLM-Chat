---
title: "test_job_cleanup"
draft: false
---

## Module `test_job_cleanup`

`Tools/mcp-sandbox/tests/test_job_cleanup.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools\mcp-sandbox\tests`. See **Related** for package index and callers.

---

## Classes

### `class TestShouldUseBackground`

**Purpose:** Type `TestShouldUseBackground` defined in `test_job_cleanup.py`.

### `class TestJobDirCleanupOnSyncCompletion`

**Purpose:** Type `TestJobDirCleanupOnSyncCompletion` defined in `test_job_cleanup.py`.

### `class TestJobDirKeptForTrulyBackgrounded`

**Purpose:** Type `TestJobDirKeptForTrulyBackgrounded` defined in `test_job_cleanup.py`.

### `class TestPurgeStaleFilesystemCleanup`

**Purpose:** Type `TestPurgeStaleFilesystemCleanup` defined in `test_job_cleanup.py`.

### `class TestStartupOrphanCleanup`

**Purpose:** Type `TestStartupOrphanCleanup` defined in `test_job_cleanup.py`.

---

## Test methods

#### `def TestShouldUseBackground.test_never_mode_always_false()`

**Purpose:** Implements `TestShouldUseBackground.test_never_mode_always_false` in `test_job_cleanup.py`.

#### `def TestShouldUseBackground.test_always_mode_always_true()`

**Purpose:** Implements `TestShouldUseBackground.test_always_mode_always_true` in `test_job_cleanup.py`.

#### `def TestShouldUseBackground.test_auto_high_timeout_triggers_background()`

**Purpose:** Implements `TestShouldUseBackground.test_auto_high_timeout_triggers_background` in `test_job_cleanup.py`.

#### `def TestShouldUseBackground.test_auto_low_timeout_no_background()`

**Purpose:** Implements `TestShouldUseBackground.test_auto_low_timeout_no_background` in `test_job_cleanup.py`.

#### `def TestShouldUseBackground.test_auto_long_running_pattern_triggers_background()`

**Purpose:** Implements `TestShouldUseBackground.test_auto_long_running_pattern_triggers_background` in `test_job_cleanup.py`.

#### `def TestShouldUseBackground.test_auto_plain_command_low_timeout_no_background()`

**Purpose:** Implements `TestShouldUseBackground.test_auto_plain_command_low_timeout_no_background` in `test_job_cleanup.py`.

#### `def TestJobDirCleanupOnSyncCompletion.setUp()`

**Purpose:** Implements `TestJobDirCleanupOnSyncCompletion.setUp` in `test_job_cleanup.py`.

#### `def TestJobDirCleanupOnSyncCompletion.tearDown()`

**Purpose:** Implements `TestJobDirCleanupOnSyncCompletion.tearDown` in `test_job_cleanup.py`.

#### `def TestJobDirCleanupOnSyncCompletion.test_quick_command_no_leftover_dir()`

**Purpose:** A command that finishes quickly leaves no .sandbox_jobs entry.

#### `def TestJobDirCleanupOnSyncCompletion.test_job_not_in_registry_after_dir_cleanup()`

**Purpose:** After sync completion no live job directory is retained.

#### `def TestJobDirCleanupOnSyncCompletion.test_multiple_quick_commands_no_accumulation()`

**Purpose:** Repeated quick commands don't accumulate dirs.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def TestJobDirCleanupOnSyncCompletion.test_failed_command_dir_also_cleaned()`

**Purpose:** Non-zero exit codes also clean up the dir.

#### `def TestJobDirKeptForTrulyBackgrounded.setUp()`

**Purpose:** Implements `TestJobDirKeptForTrulyBackgrounded.setUp` in `test_job_cleanup.py`.

#### `def TestJobDirKeptForTrulyBackgrounded.tearDown()`

**Purpose:** Implements `TestJobDirKeptForTrulyBackgrounded.tearDown` in `test_job_cleanup.py`.

#### `def TestJobDirKeptForTrulyBackgrounded.test_timed_out_job_keeps_dir()`

**Purpose:** A command that exceeds timeout_s returns error_type=backgrounded and keeps dir.

**Steps:**

1. Handle errors and map them to a safe response.
2. Iterate and transform or accumulate state.

#### `def TestPurgeStaleFilesystemCleanup.setUp()`

**Purpose:** Implements `TestPurgeStaleFilesystemCleanup.setUp` in `test_job_cleanup.py`.

#### `def TestPurgeStaleFilesystemCleanup.tearDown()`

**Purpose:** Implements `TestPurgeStaleFilesystemCleanup.tearDown` in `test_job_cleanup.py`.

#### `def TestPurgeStaleFilesystemCleanup.test_purge_stale_removes_done_dirs()`

**Purpose:** purge_stale with ttl=0 removes all done/killed jobs and their dirs.

#### `def TestPurgeStaleFilesystemCleanup.test_purge_stale_keeps_running_jobs()`

**Purpose:** purge_stale must not touch still-running jobs.

#### `def TestStartupOrphanCleanup.setUp()`

**Purpose:** Implements `TestStartupOrphanCleanup.setUp` in `test_job_cleanup.py`.

#### `def TestStartupOrphanCleanup.tearDown()`

**Purpose:** Implements `TestStartupOrphanCleanup.tearDown` in `test_job_cleanup.py`.

#### `def TestStartupOrphanCleanup.test_cleans_all_dirs_on_startup()`

**Purpose:** Orphaned dirs from previous sessions are removed.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def TestStartupOrphanCleanup.test_noop_when_no_jobs_dir()`

**Purpose:** No error if .sandbox_jobs doesn't exist yet.

---

## Private functions

#### `def _jobs_root() -> Path`

**Purpose:** Implements `_jobs_root` in `test_job_cleanup.py`.

#### `def _native_bash_available() -> bool`

**Purpose:** Implements `_native_bash_available` in `test_job_cleanup.py`.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Spawn or communicate with a child process.

---

## Related

- [tests/_index](../../../_index/)
