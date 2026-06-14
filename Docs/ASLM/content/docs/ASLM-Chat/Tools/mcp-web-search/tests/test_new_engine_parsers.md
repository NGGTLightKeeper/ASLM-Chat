---
title: "test_new_engine_parsers"
draft: false
---

## Module `test_new_engine_parsers`

`Tools/mcp-web-search/tests/test_new_engine_parsers.py` — ASLM Chat Python test module validating parsing logic across different search engine integrations (Qwant, Startpage, Yandex, Yep).

---

## Test methods

#### `def test_startpage_parses_embedded_web_google_block() -> None`

**Purpose:** Validates that Startpage search results properly extract and parse standard embedded web block segments.

#### `def test_startpage_captcha_is_blocked() -> None`

**Purpose:** Ensures Startpage API returns an identifiable blocked/captcha status when scraping restrictions hit.

#### `def test_startpage_missing_blob_is_changed() -> None`

**Purpose:** Verifies that missing required data blobs trigger a `ParseStatus.CHANGED` state to catch silent SERP drift.

#### `def test_startpage_sc_token_backs_off_after_failure() -> None`

**Purpose:** Asserts that a failing Startpage homepage scrape is not retried immediately on every subsequent search request, verifying the token cooldown mechanism (`_SC_RETRY_COOLDOWN`) prevents a serialization queue when blocked behind the global lock.

---

## Related

- [tests/_index](../../../_index/)
