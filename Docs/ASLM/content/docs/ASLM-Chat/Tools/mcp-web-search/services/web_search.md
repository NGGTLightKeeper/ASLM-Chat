---
title: "web_search"
draft: false
---

## Module `web_search`

`Tools/mcp-web-search/services/web_search.py` — ASLM Chat Python module.

---

## Overview

End-to-end `web_search` MCP tool: validate query → classify → parallel retrieval (DDGS, hosted APIs, academic) → rank/triage → optional preview fetch → shaped model/UI response. Effort controls timeouts and counts.


---

## Classes

### `class TriageResult`

**Purpose:** Type `TriageResult` defined in `web_search.py`.

### `class SearchCycleContext`

**Purpose:** Type `SearchCycleContext` defined in `web_search.py`.

### `class _OutputProfile`

**Purpose:** Type `_OutputProfile` defined in `web_search.py`.

### `class WebSearchOptions`

**Purpose:** Type `WebSearchOptions` defined in `web_search.py`.

### `class WebSearchService`

**Purpose:** Type `WebSearchService` defined in `web_search.py`.

---

## Public functions

#### `async def shutdown_web_search() -> None`

**Purpose:** Close shared HTTP connector on MCP server shutdown.

**Steps:**

1. Await async I/O or subprocess work.

#### `def validate_search_query(query) -> str | None`

**Purpose:** Validate query quality; return None or a BAD_QUERY rejection message.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def infer_query_language(query) -> str`

**Purpose:** Detect dominant script → 2-letter language code for DDGS region routing.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def infer_query_types(query) -> list[str]`

**Purpose:** Classify query into up to 3 routing types (rules-based profiles).

#### `def clear_shared_search_model_session() -> None`

**Purpose:** Release the optional process-wide neural model session.

#### `def WebSearchService.__init__(options) -> None`

**Purpose:** Implements `WebSearchService.__init__` in `web_search.py`.

#### `async def WebSearchService.search(query, deadline, model_session) -> str`

**Purpose:** Run web search and return formatted text for the MCP tool.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

#### `async def WebSearchService.search_structured(query, deadline, model_session) -> list[SearchResult]`

**Purpose:** Deep-research entry: ranked SearchResult list without preview formatting.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Iterate and transform or accumulate state.

#### `async def WebSearchService.search_rich(query, deadline, model_session) -> SearchRichResult`

**Purpose:** Structured payload for MCP structuredContent / UI clients.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

#### `async def run_web_search(query, max_results, fetch_previews, timelimit, time_range, hard_timeout, effort) -> str`

**Purpose:** MCP/CLI entry: formatted text search with hard timeout and timelimit inference.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.

#### `async def run_web_search_structured(query, max_results, timelimit, hard_timeout, time_range, effort) -> list[SearchResult]`

**Purpose:** Structured search returning ranked SearchResult items (no preview formatting).

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.

#### `async def run_web_search_rich(query, max_results, timelimit, hard_timeout, time_range, effort) -> dict[str, object]`

**Purpose:** Rich search payload for MCP structuredContent / UI.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

---

## Private functions

#### `def _shopping_intent_weight(class_mix, query_types) -> float`

**Purpose:** Calculate combined confidence for the "shopping" intent from class weights.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _should_run_shopping_core(class_mix, query_types) -> bool`

**Purpose:** Determine if shopping intent strength exceeds routing threshold.

**Steps:**

1. Return the computed result to the caller.

#### `def _shopping_limit_for_effort(effort, max_results) -> int`

**Purpose:** Select result count limit for the shopping worker based on normalized effort.

**Steps:**

1. Return the computed result to the caller.

#### `def _shopping_worker_timeout_for_effort(effort) -> float`

**Purpose:** Provide the hard-kill subprocess timeout for the shopping search per effort tier.

**Steps:**

1. Return the computed result to the caller.

#### `def _shopping_price_line(product) -> str`

**Purpose:** Condense strict monetary structures into simple price text for snippets.

**Steps:**

1. Return the computed result to the caller.

#### `def _shopping_source_from_product(product, rank, source_id) -> SearchSource | None`

**Purpose:** Hydrates standard `SearchSource` metadata citations directly from JSON shopping products.

**Steps:**

1. Return the computed result to the caller.

#### `def _shopping_product_json(product, citation_id, effort) -> dict[str, Any]`

**Purpose:** Serializes a single shopping result item, adjusting fidelity by effort limits.

**Steps:**

1. Return the computed result to the caller.

#### `def _build_shopping_payload(query, effort, raw_result, product_citation_ids) -> dict[str, Any]`

**Purpose:** Constructs the structured UI component JSON output for shopping items.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _append_shopping_context(model_context, shopping_payload) -> str`

**Purpose:** Injects strict JSON-structured shopping arrays directly into the primary neural model context.

**Steps:**

1. Return the computed result to the caller.
2. Parse or serialize JSON payloads.

#### `def _is_redirect_status(status_code) -> bool`

**Purpose:** True for HTTP redirect status codes.

#### `async def _get_http_connector(concurrency) -> 'aiohttp.TCPConnector'`

**Purpose:** Return (or lazily create) the shared TCPConnector for preview fetches.

**Steps:**

1. Return the computed result to the caller.

#### `async def _aiohttp_get_text_checked(session, url, *, headers=…, content_tokens=…) -> str | None`

**Purpose:** aiohttp text fetch with per-redirect SSRF checks.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Iterate and transform or accumulate state.

#### `def _curl_get_text_checked(url, *, timeout, headers, content_tokens=…) -> str | None`

**Purpose:** curl_cffi text fetch with per-redirect SSRF checks.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _make_request_id() -> str`

**Purpose:** Generate a short hex request id for trace logs.

#### `def _trace(req_id, stage, **fields) -> None`

**Purpose:** Emit a structured trace line for web_search stages.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def _normalize_time_range(time_range) -> Optional[str]`

**Purpose:** Map a human-readable time range alias to a DDGS timelimit (d/w/m/y).

#### `def _auto_timelimit(query_types) -> Optional[str]`

**Purpose:** Infer DDGS timelimit from primary classified query type.

#### `def _stricter_timelimit(a, b) -> Optional[str]`

**Purpose:** Return the more restrictive of two timelimits (None = no restriction).

**Steps:**

1. Return the computed result to the caller.

#### `def _has_historical_year_anchor(query) -> bool`

**Purpose:** True when the query anchors to a year before last calendar year.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _resolve_auto_timelimit(query) -> Optional[str]`

**Purpose:** Combine query-type auto timelimit with historical-year override.

#### `def _year_hint_timelimit(query, mode, current, prev, older) -> Optional[str]`

**Purpose:** Map trailing year tokens in the query to a DDGS timelimit when mode is timelimit.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _apply_year_hint_policy(query, qcfg) -> tuple[str, Optional[str]]`

**Purpose:** Apply year_hint_mode: strip years and/or derive timelimit from config.

**Steps:**

1. Return the computed result to the caller.

#### `def _strip_trailing_year(query) -> str`

**Purpose:** Strip year tokens used as freshness hints (comma-trailing or with freshness words).

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _count_content_tokens(query) -> int`

**Purpose:** Count content words in a query (operators and quoted phrases excluded).

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _contains_spam_keyword(query, keyword) -> bool`

**Purpose:** True when a banned SEO keyword appears as a whole word or phrase.

**Steps:**

1. Return the computed result to the caller.

#### `def _spam_scan_text(query) -> str`

**Purpose:** Query text with operators removed, for SEO spam scanning.

#### `def _parse_query_profile(query) -> dict`

**Purpose:** Extract years, journalistic intent, and query terms for scoring helpers.

**Steps:**

1. Return the computed result to the caller.

#### `def _hub_penalty(url, title, snippet) -> float`

**Purpose:** Penalize hub/listing URLs and generic index pages in triage scoring.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _pipeline_mode() -> str`

**Purpose:** Resolve pipeline mode from env or search_config (rules vs aslm_embedding).

**Steps:**

1. Return the computed result to the caller.

#### `def _models_config()`

**Purpose:** Cached models section from search_config.

#### `def _neural_stack_enabled(effort) -> bool`

**Purpose:** Neural stack runs only on high effort when pipeline is aslm_embedding.

#### `def _neural_encoder_enabled(effort) -> bool`

**Purpose:** True when ASLM encoder should load for this effort.

**Steps:**

1. Return the computed result to the caller.

#### `def _neural_decoder_enabled(effort) -> bool`

**Purpose:** True when ASLM decoder should load for this effort.

**Steps:**

1. Return the computed result to the caller.

#### `def _use_neural_pipeline(effort) -> bool`

**Purpose:** True when encoder or decoder is active for this effort.

#### `def _model_session_components(effort) -> tuple[bool, bool]`

**Purpose:** Which neural components (encoder, decoder) are enabled for this effort.

#### `def _format_model_label_top(top, limit) -> list[list[Any]]`

**Purpose:** Format top class scores for trace/debug output.

#### `def _component_load_status(*, enabled, requested, loaded, path, error) -> dict[str, Any]`

**Purpose:** Build encoder/decoder load status dict for neural session snapshots.

**Steps:**

1. Return the computed result to the caller.

#### `def _model_session_snapshot(model_session, effort) -> dict[str, Any]`

**Purpose:** Snapshot neural model session load state for tracing.

**Steps:**

1. Return the computed result to the caller.

#### `def _log_neural_usage(req_id, *, effort, model_session, class_debug=…) -> None`

**Purpose:** Log neural encoder/decoder usage and classification debug to trace.

**Steps:**

1. Iterate and transform or accumulate state.

#### `def _env_enabled(name, *, default) -> bool`

**Purpose:** Parse ASLM_WEB_SEARCH_* env flag (0/false/no/off → disabled).

**Steps:**

1. Return the computed result to the caller.

#### `def _keep_search_models_loaded() -> bool`

**Purpose:** True when neural models should stay loaded between searches.

**Steps:**

1. Return the computed result to the caller.

#### `def _search_model_device() -> str`

**Purpose:** Device string for ASLM models (env or config, default cpu).

#### `def _session_matches_components(session, *, load_encoder, load_decoder, device) -> bool`

**Purpose:** True when a cached session matches requested encoder/decoder/device.

**Steps:**

1. Return the computed result to the caller.

#### `def _get_shared_search_model_session(effort, *, load_encoder, load_decoder) -> SearchModelSession`

**Purpose:** Get or create the process-wide SearchModelSession (when keep_loaded).

**Steps:**

1. Return the computed result to the caller.

#### `def _search_model_session_scope(effort)`

**Purpose:** Implements `_search_model_session_scope` in `web_search.py`.

#### `def _class_mix_to_legacy_types(class_mix) -> list[str]`

**Purpose:** Convert class mix weights to legacy query type name list.

#### `def _build_legacy_class_mix(query) -> list[QueryClassWeight]`

**Purpose:** Build class mix from rules-only profile scoring.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _build_neural_class_mix(query, model_session, effort) -> tuple[list[QueryClassWeight], dict]`

**Purpose:** Build class mix via ASLM encoder with rules fallback and debug metadata.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _triage_soft_score(result, query, *, index, total) -> float`

**Purpose:** Cheap lexical/trust score used before preview fetching.

**Steps:**

1. Return the computed result to the caller.

#### `def _triage_one_result(result, query, *, index, total, trust_reg=…, rep_store=…) -> TriageResult`

**Purpose:** Run cheap triage for one SERP result (skip/fetch_policy/score).

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _triage_results(results, query) -> list[TriageResult]`

**Purpose:** Cheap per-result triage; populates result.trust_tier when missing.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _apply_domain_cap(results) -> list[SearchResult]`

**Purpose:** Enforce per-domain cap so one host cannot dominate the candidate pool.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _apply_registry_routing(results, class_mix) -> None`

**Purpose:** Attach domain-registry routing_score and debug to each result.

**Steps:**

1. Handle errors and map them to a safe response.
2. Iterate and transform or accumulate state.

#### `def _apply_snippet_decoder(results, query, model_session, effort, *, req_id=…) -> None`

**Purpose:** Score SERP snippets with ASLM decoder when enabled.

**Steps:**

1. Handle errors and map them to a safe response.
2. Iterate and transform or accumulate state.

#### `def _apply_parsed_decoder(results, payloads, query, model_session, effort, *, req_id=…) -> None`

**Purpose:** Score fetched preview bodies with ASLM decoder when enabled.

**Steps:**

1. Handle errors and map them to a safe response.
2. Iterate and transform or accumulate state.

#### `def _dedup_results(results) -> list[SearchResult]`

**Purpose:** Dedup by normalized URL, domain+title, and snippet signature.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _trust_blend_weights(query_type) -> tuple[float, float]`

**Purpose:** Static/dynamic trust blend weights for lexical scoring by query type.

#### `def _academic_engine_bonus(result, query_type) -> float`

**Purpose:** Small score boost for academic: engine results on academic/medical queries.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _year_match_score(text, years) -> float`

**Purpose:** Boost when preview/body years match query year anchors; penalize mismatch.

**Steps:**

1. Return the computed result to the caller.

#### `def _parsed_lexical_score(query, result, payload) -> float`

**Purpose:** Lexical overlap using SERP fields plus fetched preview body text.

**Steps:**

1. Return the computed result to the caller.

#### `def _result_score(result, payload, *, index, total, query, profile, query_type=…, rep_store=…) -> float`

**Purpose:** Combined rerank score: lexical, neural, trust, routing, and hub penalty.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _content_quality_signal(payload, result, query) -> float`

**Purpose:** Content quality signal for reputation recording (no rank/trust position).

**Steps:**

1. Return the computed result to the caller.

#### `def _resolve_result_trust_tier(result, url, *, trust_reg, rep_store) -> None`

**Purpose:** Fill trust_tier from static registry, then dynamic auto-promote.

**Steps:**

1. Handle errors and map them to a safe response.
2. Iterate and transform or accumulate state.

#### `def _get_prefetch_semaphore() -> asyncio.Semaphore`

**Purpose:** Semaphore limiting concurrent background prefetch tasks.

**Steps:**

1. Return the computed result to the caller.

#### `async def _prefetch_urls_background(urls, req_id) -> None`

**Purpose:** Fire-and-forget: prefetch uncached URLs into SourceCache (HTML only, no antibot).

**Steps:**

1. Await async I/O or subprocess work.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `async def _fetch_pdf_preview(url, query, loop, req_id) -> PreviewPayload`

**Purpose:** Download PDF, extract text, densify with GliNER (tight preview caps).

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

#### `async def _fetch_preview_one(session, result, query, settings, sem, loop, policy, fetch_timeout, req_id) -> PreviewPayload`

**Purpose:** Fetch one page preview (policy cheap = aiohttp only, race = aiohttp + curl_cffi).

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

#### `async def _fetch_previews(results, query, concurrency, fetch_timeout, total_timeout, preview_settings, loop, policies, early_return_threshold, req_id, deadline) -> list[PreviewPayload]`

**Purpose:** Fetch previews concurrently; optional early_return_threshold cancels stragglers.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

#### `def _preview_display_limit(query_type, *, low_effort) -> int`

**Purpose:** Max preview chars shown in formatted output by query type and effort.

**Steps:**

1. Return the computed result to the caller.

#### `def _configure_preview_settings(preview_settings, *, query_type) -> dict`

**Purpose:** Merge query-type chunk policy into preview extraction settings.

**Steps:**

1. Return the computed result to the caller.

#### `def _get_output_profile(query_types) -> _OutputProfile`

**Purpose:** Return depth-first or breadth-first output profile for the primary query type.

#### `def _normalize_search_effort(effort) -> str`

**Purpose:** Normalize effort aliases (normal/default → medium).

#### `def _is_low_effort(opts) -> bool`

**Purpose:** True when search effort is low (snippet-only, no previews).

#### `def _scale_output_profile(profile, multiplier) -> _OutputProfile`

**Purpose:** Scale max_results and preview limits for high effort.

**Steps:**

1. Return the computed result to the caller.

#### `def _apply_effort_to_output_profile(profile, opts) -> _OutputProfile`

**Purpose:** Apply low/high effort overrides to an output profile.

**Steps:**

1. Return the computed result to the caller.

#### `def _enforce_effort_after_adaptation(profile, opts) -> _OutputProfile`

**Purpose:** Re-apply low-effort caps after adaptive profile widening.

#### `def _effective_output_limit(profile, opts) -> int`

**Purpose:** Final model-visible result cap (profile vs opts.max_results).

#### `def _adapt_output_profile(results, triage, base_profile, *, query_types, payloads=…) -> tuple[_OutputProfile, dict[str, object]]`

**Purpose:** Widen technical/troubleshooting output when preview evidence is thin.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _badge_type(url) -> str`

**Purpose:** Short badge label for result URL type (VIDEO, PDF, WIKI, etc.).

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _infer_pdf_url(result) -> str`

**Purpose:** Resolve direct PDF URL from result metadata or arxiv abs link.

**Steps:**

1. Return the computed result to the caller.

#### `def _enrich_pdf_urls(results) -> list[SearchResult]`

**Purpose:** Populate pdf_url on each SearchResult when inferable.

#### `def _badge_engine(engine) -> str`

**Purpose:** Human-readable search engine / provider label for output.

**Steps:**

1. Return the computed result to the caller.

#### `def _display_text(text, limit) -> str`

**Purpose:** Collapse whitespace and truncate text for snippet/preview display.

**Steps:**

1. Return the computed result to the caller.

#### `def _semantic_duplicate_ratio(a, b) -> float`

**Purpose:** Token Jaccard + char similarity for snippet/preview de-duplication.

**Steps:**

1. Return the computed result to the caller.

#### `def _dedupe_preview_against_snippet(snippet, preview, threshold) -> str`

**Purpose:** Drop preview text that largely duplicates the SERP snippet.

**Steps:**

1. Return the computed result to the caller.

#### `def _source_domain(url) -> str`

**Purpose:** Normalized host from URL for display and favicons.

**Steps:**

1. Return the computed result to the caller.

#### `def _display_domain(domain) -> str`

**Purpose:** Short display label from domain (e.g. github.com → Github).

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _favicon_url(domain) -> str`

**Purpose:** DuckDuckGo favicon URL for a domain.

#### `def _source_from_result(result, rank, *, source_id=…, score=…, preview=…, snippet_limit=…, preview_limit=…) -> SearchSource`

**Purpose:** Build SearchSource struct from a ranked result and optional preview.

**Steps:**

1. Return the computed result to the caller.

#### `def _shopping_source_from_product(product: dict[str, Any], rank: int, source_id: str) -> SearchSource | None`

**Purpose:** Build SearchSource struct from a shopping product.

**Steps:**

1. Return the computed result to the caller.

#### `def _build_model_context(query, sources, total_char_budget) -> str`

**Purpose:** Citation-oriented context block for the model from SearchSource list.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _citation_source_id(search_id, rank) -> str`

**Purpose:** Stable citation handle id for a source rank within a search_id.

**Steps:**

1. Return the computed result to the caller.

#### `def _build_compact_ui(query, sources, limit) -> dict[str, object]`

**Purpose:** Compact UI chip payload for rich search responses.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _rich_result_to_dict(result) -> dict[str, object]`

**Purpose:** Serialize SearchRichResult for MCP structuredContent.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _normalize_date(raw) -> str`

**Purpose:** Normalize engine date strings to 'Mon DD, YYYY' (empty if unparseable).

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _format_results(results, payloads, query, query_profile, output_profile, snippet_char_budget, preview_char_budget, total_char_budget, query_type, query_types, rep_store, max_results_override) -> str`

**Purpose:** Build final MCP text output with depth-first vs breadth-first selection.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.
4. Parse or serialize JSON payloads.

#### `def _select_output_sources(results, payloads, query, *, query_profile, output_profile, query_type=…, query_types=…, rep_store=…, max_results_override=…) -> list[tuple[SearchResult, PreviewPayload]]`

**Purpose:** Select rich sources parsed-first while preserving requested volume.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.
4. Parse or serialize JSON payloads.

#### `async def WebSearchService._run_search_pipeline(query, lang, query_types, query_type, out_profile, opts, req_id, class_mix, source_budget, model_session) -> tuple[list[SearchResult], list]`

**Purpose:** DDGS + hosted + academic fetch, merge, dedup, triage.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Handle errors and map them to a safe response.
4. Iterate and transform or accumulate state.

#### `def WebSearchService._fallback_query_variants(query) -> list[str]`

**Purpose:** Implements `WebSearchService._fallback_query_variants` in `web_search.py`.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `async def WebSearchService._run_with_zero_result_fallback(*, provider_query, analysis_query, query_types, out_profile, opts, req_id, class_mix=…, source_budget=…, model_session=…) -> tuple[list[SearchResult], list[_TriageResult], str]`

**Purpose:** Run search pipeline; retry with simpler query variants if empty.

**Steps:**

1. Return the computed result to the caller.
2. Await async I/O or subprocess work.
3. Iterate and transform or accumulate state.

#### `def _fallback_timeout_window(hard_timeout) -> float`

**Purpose:** Hard wall-clock limit for the entire search lifecycle. When exceeded, the coroutine is cancelled → subprocesses are killed via their finally blocks in async_ddgs_search(), aiohttp sessions are closed by their async context managers, and executor threads run to natural completion (they have internal timeouts so they won't hang indefinitely). Short timeout budget for degraded fallback attempts after hard timeout.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _format_timeout_fallback_text(query, results, limit) -> str`

**Purpose:** Compact snippet-only fallback text after search timeout.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _timeout_fallback_rich_payload(query, results) -> dict[str, object]`

**Purpose:** Rich JSON payload when search times out but snippet fallback succeeded.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

#### `def _rejected_search_payload(query, rejection) -> dict[str, object]`

**Purpose:** Rich JSON payload for BAD_QUERY validation rejections.

**Steps:**

1. Return the computed result to the caller.

#### `def _effort_hard_timeout(effort, hard_timeout) -> float`

**Purpose:** Wall-clock limit for a search from effort tier or explicit override.

**Steps:**

1. Return the computed result to the caller.

#### `def _build_effort_options(cfg, *, effort, max_results, fetch_previews, timelimit) -> WebSearchOptions`

**Purpose:** WebSearchOptions tuned for low/medium/high effort from config.

**Steps:**

1. Return the computed result to the caller.

---

## Related

- [services/_index](../../../_index/)
