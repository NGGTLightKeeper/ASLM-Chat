---
title: "test_browser_daemon"
draft: false
---

## Module `test_browser_daemon`

`Tools/mcp-web-search/tests/test_browser_daemon.py` — ASLM Chat Python module.

---

## Public functions

#### `def test_recycle_reason_priority(tmp_path, monkeypatch)`

**Purpose:** test_recycle_reason_priority defined in test_browser_daemon.py

**Steps:**

1. Asserts the `wc._recycle_reason()` returns `None` for fresh and down browsers.
2. Asserts correct behavior for `RecycleReason.REQUESTS`, `RecycleReason.AGE`, and `RecycleReason.RSS`.
3. Asserts burn streak priority over other reasons.

#### `def test_fetch_counts_and_marks_dirty(tmp_path)`

**Purpose:** test_fetch_counts_and_marks_dirty defined in test_browser_daemon.py

**Steps:**

1. Await a fetch result on a url.
2. Asserts fetch correctly updates request/total counters, sets dirty flag, and clears blocked streak.

#### `def test_blocked_increments_streak_then_resets(tmp_path)`

**Purpose:** test_blocked_increments_streak_then_resets defined in test_browser_daemon.py

**Steps:**

1. Await multiple fetch requests returning blocked results.
2. Asserts blocked streak increases for consecutive blocks.
3. Asserts streak correctly resets to 0 upon a valid ok fetch.

#### `def test_request_count_recycle_checkpoints_good(tmp_path)`

**Purpose:** test_request_count_recycle_checkpoints_good defined in test_browser_daemon.py

**Steps:**

1. Await enough requests to trigger threshold limit.
2. Asserts `_recycles` counter increments properly.
3. Asserts the recycle successfully checkpointed a good identity generation seedable on next start.

#### `def test_burn_recycle_rotates_identity(tmp_path)`

**Purpose:** test_burn_recycle_rotates_identity defined in test_browser_daemon.py

**Steps:**

1. Seed multiple checkpoint states to simulate history.
2. Await fetches to hit consecutive blocks.
3. Await `wc._recycle(RecycleReason.BURN)`.
4. Asserts recycle completes and correctly resets blocked streak.
5. Asserts identity falls back by discarding the burnt generation but still keeping a valid latest_good identity state.

#### `def test_rss_recycle_then_serves(tmp_path, monkeypatch)`

**Purpose:** test_rss_recycle_then_serves defined in test_browser_daemon.py

**Steps:**

1. Run a fetch to populate RSS limits mock properly.
2. Update mocked limit so next fetch trips cap.
3. Await second fetch and assert recycle triggering correctly occurs.

#### `def test_idle_checkpoint_persists_when_dirty(tmp_path)`

**Purpose:** test_idle_checkpoint_persists_when_dirty defined in test_browser_daemon.py

**Steps:**

1. Fake the context being active and dirty flag true.
2. Manually await loop checkpointing logic.
3. Assert dirty flag cleared and checkpointing succeeded properly into valid stores.

#### `def test_stop_final_checkpoints_and_tears_down(tmp_path)`

**Purpose:** test_stop_final_checkpoints_and_tears_down defined in test_browser_daemon.py

**Steps:**

1. Await an initial fetch.
2. Await `wc.stop()` method for shutdown sequence.
3. Assert teardown logic correctly sets contexts to closed, releases `_browser` reference, and checkpoints final valid storage states.

#### `def test_extraction_hang_is_capped_not_indefinite(tmp_path, monkeypatch)`

**Purpose:** test_extraction_hang_is_capped_not_indefinite defined in test_browser_daemon.py

**Steps:**

1. Patches mock timeout extraction limits smaller.
2. Wire fake extraction process designed to hang indefinitely on content().
3. Assert extraction cap forces a bounded timeout status return preventing permanent lock holds, and appropriately releasing lock inflight counts.

#### `def test_close_hang_flags_wedge_and_recycles(tmp_path, monkeypatch)`

**Purpose:** test_close_hang_flags_wedge_and_recycles defined in test_browser_daemon.py

**Steps:**

1. Patches mock timeout limit for closing operations.
2. Wire context faking extraction success, but close() hangs continuously.
3. Assert successful ok response, but close block flags the browser wedged, successfully tearing it down so flags/states clear for the next clean respawn.
4. Asserts best-effort checkpoint ensures live valid identity generation was correctly saved beforehand.
