---
title: "test_identity_cookies"
draft: false
---

## Module `test_identity_cookies`

`Tools/mcp-web-search/tests/test_identity_cookies.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools/mcp-web-search/tests`.

---

## Public functions

#### `def test_merge_set_cookie_and_header_roundtrip(tmp_path)`

**Purpose:** Implements `test_merge_set_cookie_and_header_roundtrip`.

#### `def test_cookie_domain_scoping(tmp_path)`

**Purpose:** Implements `test_cookie_domain_scoping`.

#### `def test_expired_and_deleted_cookies_are_dropped(tmp_path)`

**Purpose:** Implements `test_expired_and_deleted_cookies_are_dropped`.

#### `def test_session_cookies_age_out(tmp_path)`

**Purpose:** Implements `test_session_cookies_age_out`.

#### `def test_transport_replay_merges_stored_cookies(tmp_path, monkeypatch)`

**Purpose:** Implements `test_transport_replay_merges_stored_cookies`.

#### `def test_transport_capture_writes_back(tmp_path, monkeypatch)`

**Purpose:** Implements `test_transport_capture_writes_back`.

#### `def test_no_identity_key_is_a_noop(tmp_path, monkeypatch)`

**Purpose:** Implements `test_no_identity_key_is_a_noop`.

---

## Private functions

#### `def _store(tmp_path) -> IdentityStore`

**Purpose:** Implements `_store`.

---

## Related

- [tests/_index](../../_index/)
