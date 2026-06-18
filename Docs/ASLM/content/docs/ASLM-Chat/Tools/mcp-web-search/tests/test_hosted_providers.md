---
title: "test_hosted_providers"
draft: false
---

## Module `test_hosted_providers`

`Tools/mcp-web-search/tests/test_hosted_providers.py` — ASLM Chat Python module.

---

## Classes

### `class _FakeProvider`

**Purpose:** Mock hosted provider.

---

## Test methods

#### `def test_tavily_returns_content(monkeypatch) -> None`

**Purpose:** Verify Tavily search response handling.

#### `def test_firecrawl_returns_markdown_content(monkeypatch) -> None`

**Purpose:** Verify Firecrawl search response handling.

#### `def test_serpapi_family_is_google_and_no_content(monkeypatch) -> None`

**Purpose:** Verify SerpApi search response handling.

#### `def test_provider_soft_fails_on_http_error(monkeypatch) -> None`

**Purpose:** Verify HTTP error returns empty list without crashing.

#### `def test_hosted_stream_merges_providers(monkeypatch) -> None`

**Purpose:** Verify `hosted_search_stream` yields combined results.

#### `def test_hosted_stream_drops_nav_junk(monkeypatch) -> None`

**Purpose:** Verify hosted stream drops short/nav junk results.

---

## Private functions

#### `def _client(handler)`

**Purpose:** Provide an `httpx.AsyncClient` mocked with the given transport handler.

---

## Related

- [tests/_index](../../../_index/)
