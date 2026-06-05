---
title: "downloads_bridge"
draft: false
---

## Module `downloads_bridge`

`Services/downloads_bridge.py` — ASLM Chat Python module.

---

## Overview

Part of `Services`. See **Related** for package index and callers.

---

## Classes

### `class OllamaSearchQuery`

**Purpose:** Type `OllamaSearchQuery` defined in `downloads_bridge.py`.

---

## Public functions

#### `def dispatch(request) -> dict[str, Any]`

**Purpose:** Route a bridge request to the matching handler.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def run_cli() -> int`

**Purpose:** Execute the bridge in stdin/stdout mode.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Parse or serialize JSON payloads.

---

## Private functions

#### `def _response(*, success=…, categories=…, items=…, filters=…, item_detail=…, install_manifest=…, uninstall_manifest=…, warnings=…, error=…) -> dict[str, Any]`

**Purpose:** Build a standard bridge response payload.

**Steps:**

1. Return the computed result to the caller.

#### `def _read_request() -> dict[str, Any]`

**Purpose:** Read and validate the JSON request from stdin.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Parse or serialize JSON payloads.

#### `def _normalize_text(value) -> str`

**Purpose:** Normalize text into a single readable line.

#### `def _normalize_separator(value) -> str`

**Purpose:** Normalize bullet-style separators into the bridge format.

#### `def _normalize_filter_key(value) -> str`

**Purpose:** Normalize a filter key for comparisons.

#### `def _deduplicate_preserving_order(values) -> list[str]`

**Purpose:** Remove duplicates while keeping the first occurrence.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _parse_int(value) -> int`

**Purpose:** Parse an integer from mixed text.

#### `def _ensure_cache_dirs() -> None`

**Purpose:** Ensure that all cache directories exist.

#### `def _read_cache(path) -> Any | None`

**Purpose:** Read a JSON cache payload.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Parse or serialize JSON payloads.

#### `def _write_cache(path, payload) -> None`

**Purpose:** Write a JSON cache payload.

#### `def _write_text_file(path, content) -> None`

**Purpose:** Write a plain text cache file.

#### `def _variant_resource_key(slug, tag) -> str`

**Purpose:** Build a resource key for a model variant.

#### `def _resource_key_to_slug(resource_key) -> str`

**Purpose:** Extract the slug portion from a resource key.

**Steps:**

1. Return the computed result to the caller.

#### `def _detail_cache_path(slug) -> Path`

**Purpose:** Resolve the JSON detail cache path for a slug.

#### `def _detail_html_cache_path(slug, block_id, html_document) -> Path`

**Purpose:** Resolve the HTML detail cache path for a rendered block.

**Steps:**

1. Return the computed result to the caller.

#### `def _resolve_model_page_path(slug) -> str`

**Purpose:** Resolve the Ollama page path for a model slug.

**Steps:**

1. Return the computed result to the caller.

#### `def _resolve_model_page_url(slug) -> str`

**Purpose:** Resolve the absolute Ollama page URL for a model slug.

#### `def _search_cache_path(search_query) -> Path`

**Purpose:** Build the cache path for a search query.

**Steps:**

1. Return the computed result to the caller.
2. Parse or serialize JSON payloads.

#### `def _request_text(url, params) -> str`

**Purpose:** Request text content from a remote page.

**Steps:**

1. Return the computed result to the caller.

#### `def _make_soup(markup) -> Any`

**Purpose:** Build a BeautifulSoup parser lazily so metadata-only bridge calls stay cheap.

#### `def _absolutize_url(candidate, base_url) -> str`

**Purpose:** Resolve a relative URL against the current page.

#### `def _build_detail_line(pull_count, tag_count, updated_text) -> str`

**Purpose:** Build a standard item detail line.

#### `def _build_variant_line(parts) -> str`

**Purpose:** Build a standard variant detail line.

#### `def _build_ollama_category() -> dict[str, Any]`

**Purpose:** Build the static Ollama category payload.

**Steps:**

1. Return the computed result to the caller.

#### `def _build_default_filter_payloads(search_query) -> list[dict[str, Any]]`

**Purpose:** Build default Ollama filter payloads when live filter data is not available.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _build_html_document(inner_html, page_url, title) -> str`

**Purpose:** Build a standalone HTML document for preview blocks.

**Steps:**

1. Return the computed result to the caller.

#### `def _create_html_block_file(slug, block_id, title, node_html, page_url) -> str`

**Purpose:** Normalize and cache a rendered HTML block.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _normalize_search_query(query_text, filter_keys) -> OllamaSearchQuery`

**Purpose:** Normalize query text and selected filters.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _build_search_params(search_query) -> list[tuple[str, str]]`

**Purpose:** Build Ollama search parameters from the normalized query.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _parse_filter_payloads(soup, search_query) -> list[dict[str, Any]]`

**Purpose:** Parse filter payloads from the Ollama search page.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _parse_search_items(soup) -> list[dict[str, Any]]`

**Purpose:** Parse model cards from the Ollama search page.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _load_search_payload(query_text, filter_keys, prefer_cached, force_refresh) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]`

**Purpose:** Load search results with cache fallback.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _parse_variant_payloads(soup, slug) -> list[dict[str, Any]]`

**Purpose:** Parse available model variants from the model page.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _extract_readme_markdown(soup) -> str`

**Purpose:** Extract the raw markdown readme from the page.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _extract_readme_html_file(slug, soup, page_url) -> str`

**Purpose:** Extract and cache the rendered HTML readme block.

**Steps:**

1. Return the computed result to the caller.

#### `def _parse_item_detail(slug, html) -> dict[str, Any]`

**Purpose:** Parse full item details from the model page.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _sanitize_detail_payload(detail) -> dict[str, Any]`

**Purpose:** Sanitize detail payloads loaded from cache or network.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _load_item_detail(slug, prefer_cached, force_refresh) -> tuple[dict[str, Any], list[str]]`

**Purpose:** Load detail payloads with cache fallback.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _build_install_manifest(resource_key) -> dict[str, Any]`

**Purpose:** Build an install manifest for a selected resource.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Iterate and transform or accumulate state.

#### `def _build_uninstall_manifest(resource_key) -> dict[str, Any]`

**Purpose:** Build an uninstall manifest for a selected resource.

**Steps:**

1. Raise on invalid input or failure conditions.
2. Return the computed result to the caller.
3. Iterate and transform or accumulate state.

#### `def _handle_list_categories() -> dict[str, Any]`

**Purpose:** Handle the list_categories operation.

#### `def _handle_list_items(category_id, query_text, filter_keys, prefer_cached, force_refresh) -> dict[str, Any]`

**Purpose:** Handle the list_items operation.

**Steps:**

1. Return the computed result to the caller.

#### `def _handle_describe_item(category_id, resource_key, prefer_cached, force_refresh) -> dict[str, Any]`

**Purpose:** Handle the describe_item operation.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _handle_resolve_install(category_id, resource_key) -> dict[str, Any]`

**Purpose:** Handle the resolve_install operation.

**Steps:**

1. Return the computed result to the caller.

#### `def _handle_resolve_uninstall(category_id, resource_key) -> dict[str, Any]`

**Purpose:** Handle the resolve_uninstall operation.

**Steps:**

1. Return the computed result to the caller.

---

## Related

- [Services/_index](../_index/)
