---
title: "test_hosted_providers"
draft: false
---

## Module `test_hosted_providers`

`Tools/mcp-web-search/tests/test_hosted_providers.py` — ASLM Chat Python module.

---

## Overview

Hosted supplement layer: provider clients, key gating, content→cache feed, consensus.

---

## Classes

### `class _FakeProvider`

**Purpose:** Type `_FakeProvider` defined in `test_hosted_providers.py`.

#### `def _FakeProvider.__init__(results, name, family)`

**Purpose:** Implements `_FakeProvider.__init__` in `test_hosted_providers.py`.

#### `def _FakeProvider.key(keys)`

**Purpose:** Implements `_FakeProvider.key` in `test_hosted_providers.py`.

#### `def _FakeProvider.search(client, query)`

**Purpose:** Implements `_FakeProvider.search` in `test_hosted_providers.py`.

---

## Public functions

#### `def test_tavily_returns_content(monkeypatch)`

**Purpose:** Implements `test_tavily_returns_content` in `test_hosted_providers.py`.

#### `def test_firecrawl_returns_markdown_content(monkeypatch)`

**Purpose:** Implements `test_firecrawl_returns_markdown_content` in `test_hosted_providers.py`.

#### `def test_serpapi_family_is_google_and_no_content(monkeypatch)`

**Purpose:** Implements `test_serpapi_family_is_google_and_no_content` in `test_hosted_providers.py`.

#### `def test_provider_soft_fails_on_http_error(monkeypatch)`

**Purpose:** Implements `test_provider_soft_fails_on_http_error` in `test_hosted_providers.py`.

#### `def test_available_providers_gated_by_keys(monkeypatch)`

**Purpose:** Implements `test_available_providers_gated_by_keys` in `test_hosted_providers.py`.

#### `def test_stream_emits_events_and_feeds_cache(monkeypatch, tmp_path)`

**Purpose:** Implements `test_stream_emits_events_and_feeds_cache` in `test_hosted_providers.py`.

#### `def test_stream_dedup_emits_vote(monkeypatch, tmp_path)`

**Purpose:** Implements `test_stream_dedup_emits_vote` in `test_hosted_providers.py`.

---

## Private functions

#### `def _keys() -> ApiKeysConfig`

**Purpose:** Implements `_keys` in `test_hosted_providers.py`.

#### `def _client(handler)`

**Purpose:** Implements `_client` in `test_hosted_providers.py`.

---

## Related

- [core](../../_index/)
