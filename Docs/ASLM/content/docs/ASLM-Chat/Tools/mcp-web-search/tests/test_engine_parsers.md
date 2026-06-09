---
title: "test_engine_parsers"
draft: false
---

## Module `test_engine_parsers`

`Tools/mcp-web-search/tests/test_engine_parsers.py` — ASLM Chat Python module.

---

## Test methods

#### `def test_google_payload_separates_duplicate_filter_from_safesearch() -> None`

**Purpose:** Verifies that Google engine's payload correctly separates the duplicate filter from the safe search setting.

#### `def test_google_detects_short_captcha_page() -> None`

**Purpose:** Checks if the Google engine correctly raises a `DDGSException` when it encounters a short CAPTCHA page.

#### `def test_brave_discards_partial_and_internal_ad_links() -> None`

**Purpose:** Ensures the Brave engine filters out partial URLs or internal ad-related links from the search results.

#### `def test_startpage_reuses_form_token(monkeypatch) -> None`

**Purpose:** Tests that the Startpage engine caches and reuses the generated form token across requests.

#### `def test_startpage_reports_missing_token_as_failure(monkeypatch) -> None`

**Purpose:** Validates that the Startpage engine raises a `DDGSException` when it fails to extract the form token.

#### `def test_startpage_discards_relative_tracking_links() -> None`

**Purpose:** Ensures the Startpage engine discards relative URLs containing tracking links.

#### `def test_stackoverflow_api_parser_returns_question_metadata() -> None`

**Purpose:** Checks that the StackOverflow engine correctly extracts metadata like answers from the JSON API response.

#### `def test_stackoverflow_payload_uses_string_query_params() -> None`

**Purpose:** Verifies that the StackOverflow payload uses string query parameters (e.g., `"page": "2"` instead of integers).

#### `def test_stackoverflow_reports_ip_block_as_rate_limit(monkeypatch) -> None`

**Purpose:** Tests that the StackOverflow engine correctly detects Stack Exchange IP blocks and raises a `RatelimitException` instead of encountering generic errors.

#### `def test_specialized_news_engines_parse_news_cards() -> None`

**Purpose:** Ensures specialized news engines like BraveNews can successfully parse news cards from the HTML snippet.

#### `def test_qwant_parser_keeps_only_web_results() -> None`

**Purpose:** Validates that the Qwant engine discards ad results and correctly parses out web results.

#### `def test_qwant_and_yep_enable_safe_search_in_payloads() -> None`

**Purpose:** Tests that both Qwant and Yep engines correctly set the safe search option in their outgoing payloads.

#### `def test_yep_parser_cleans_html_snippet_and_invalid_links() -> None`

**Purpose:** Verifies that the Yep engine cleans up HTML snippets and filters out invalid links from the results list.

#### `def test_json_engines_report_antibot_as_rate_limit(monkeypatch, engine, body: str) -> None`

**Purpose:** Checks that JSON-based engines (Qwant, Yep) correctly report anti-bot mechanisms like Cloudflare challenges as `RatelimitException`.

---

## Related

- [tests/_index](../_index/)
