# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""
Phase 2 — Harvest.

Runs web search for each query plan via the existing ``run_web_search``
service and collects raw results.  No new HTTP sessions are created; all
API keys, caches, and engine routing are reused from the search core.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from typing import Iterable, List

from core.fetch.camoufox_fetcher import fetch_batch_with_camoufox, is_camoufox_available
from core.fetch.page_fetcher import PageFetcher
from core.llm.semantic import chunk_text, compute_source_relevance, score_chunks
from core.models.search import SearchResult
from core.registry.domain_registry import get_registry
from services.read_page import run_read_page
from services.deep_research.models import (
    ExtractedSource,
    PhaseResult,
    QueryPlan,
    ResearchState,
)
from services.web_search import _cache as _search_cache
from services.web_search import run_web_search_structured


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _content_hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8", errors="replace")).hexdigest()


def _gliner_cuda_enabled(state: ResearchState) -> bool:
    from core.extract.gliner_wrapper import gliner_cuda_enabled
    def _log(msg: str) -> None:
        attr = "_gliner_runtime_logged" if "runtime:" in msg else "_gliner_hardware_skip_logged"
        if not getattr(state, attr, False):
            state.log(msg)
            setattr(state, attr, True)
    return gliner_cuda_enabled(_log)


def _clean_read_page_output(text: str) -> str:
    normalized = (text or "").strip()
    if not normalized or normalized.startswith("Error:"):
        return ""
    if normalized.startswith("Warning:"):
        parts = normalized.split("\n\n", 1)
        if len(parts) == 2:
            normalized = parts[1].strip()
    return normalized


def _fit_chunks_to_budget(chunks: list[str], ranked_indices: list[int], max_chars: int) -> str:
    selected: set[int] = set()
    budget = max(0, int(max_chars))
    for idx in ranked_indices:
        if idx < 0 or idx >= len(chunks) or idx in selected:
            continue
        chunk = chunks[idx].strip()
        if not chunk:
            continue
        cost = len(chunk) + (2 if selected else 0)
        if cost <= budget:
            selected.add(idx)
            budget -= cost
            continue
        if not selected and budget >= 500:
            selected.add(idx)
        break
    if not selected:
        return chunks[ranked_indices[0]][:max_chars] if ranked_indices else ""
    ordered = [chunks[idx] for idx in sorted(selected)]
    text = "\n\n".join(ordered).strip()
    return text[:max_chars].rstrip() if len(text) > max_chars else text


def _prepare_relevant_chunks(
    state: ResearchState,
    text: str,
) -> tuple[str, list[tuple[str, float]], list[dict]]:
    """Return context-ready source content.

    Small sources are kept whole, including a small tolerance over the target
    budget. Larger sources are densified by semantic relevance, with GLiNER
    entity-density boosting high-information chunks when enabled.
    """
    cfg = state.config
    max_chars = max(500, int(getattr(cfg, "harvest_relevant_chunks_max_chars", 3000)))
    tolerance = max(0, int(getattr(cfg, "harvest_full_text_tolerance_chars", 100)))
    if len(text) <= max_chars + tolerance:
        return text, [], []

    chunk_size = max(300, int(getattr(cfg, "harvest_chunk_size_chars", 900)))
    overlap = max(0, int(getattr(cfg, "harvest_chunk_overlap_chars", 120)))
    chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap)
    if not chunks:
        return text[:max_chars], [], []

    scored = score_chunks(state.question, chunks)
    semantic_by_text: dict[str, float] = {}
    for chunk, score in scored:
        semantic_by_text[chunk] = max(float(score), semantic_by_text.get(chunk, float("-inf")))
    semantic_scores = [semantic_by_text.get(chunk, 0.0) for chunk in chunks]
    semantic_max = max(semantic_scores) if semantic_scores else 0.0
    semantic_min = min(semantic_scores) if semantic_scores else 0.0
    span = semantic_max - semantic_min
    semantic_norm = [
        ((score - semantic_min) / span) if span > 0 else (1.0 if score > 0 else 0.0)
        for score in semantic_scores
    ]

    entities: list[dict] = []
    gliner_scores = [0.0] * len(chunks)
    used_gliner = False
    if (
        bool(getattr(cfg, "use_gliner", False))
        and cfg.depth in ("high", "extra")
        and _gliner_cuda_enabled(state)
    ):
        try:
            from core.extract.gliner_wrapper import (
                detect_language_and_adjust_threshold,
                get_labels_for_query,
                score_entity_density_with_entities,
            )

            candidate_limit = max(1, int(getattr(cfg, "harvest_gliner_chunk_limit", 32)))
            semantic_order = sorted(range(len(chunks)), key=lambda idx: semantic_scores[idx], reverse=True)
            candidate_indices: list[int] = []
            for idx in semantic_order[:candidate_limit]:
                if idx not in candidate_indices:
                    candidate_indices.append(idx)
            for idx in range(min(8, len(chunks))):
                if len(candidate_indices) >= candidate_limit:
                    break
                if idx not in candidate_indices:
                    candidate_indices.append(idx)

            threshold = detect_language_and_adjust_threshold(text[:500])
            labels = get_labels_for_query(state.question, state.query_type)
            candidate_chunks = [chunks[idx] for idx in candidate_indices]
            scored_entities = score_entity_density_with_entities(
                candidate_chunks,
                labels=labels,
                device="cuda",
                threshold=threshold,
                cpu_para_limit=candidate_limit,
            )
            for idx, (density, chunk_entities) in zip(candidate_indices, scored_entities):
                gliner_scores[idx] = float(density or 0.0)
                if chunk_entities:
                    entities.extend(chunk_entities)
            used_gliner = any(score > 0 for score in gliner_scores)
        except Exception as exc:
            state.log(f"  GLiNER densify skipped: {exc}")

    if used_gliner:
        combined_scores = [
            (0.60 * semantic_norm[idx]) + (0.40 * gliner_scores[idx])
            for idx in range(len(chunks))
        ]
    else:
        combined_scores = semantic_norm

    ranked_indices = sorted(range(len(chunks)), key=lambda idx: combined_scores[idx], reverse=True)
    dense_text = _fit_chunks_to_budget(chunks, ranked_indices, max_chars)
    if not dense_text:
        dense_text = scored[0][0][:max_chars] if scored else chunks[0][:max_chars]

    unique_entities: list[dict] = []
    seen_entities: set[tuple[str, str]] = set()
    for entity in entities:
        key = (
            str(entity.get("text", "")).strip().lower(),
            str(entity.get("label", "")).strip().lower(),
        )
        if not key[0] or key in seen_entities:
            continue
        seen_entities.add(key)
        unique_entities.append(entity)
        if len(unique_entities) >= 24:
            break

    return dense_text, scored, unique_entities


def _build_source(
    state: ResearchState,
    result: SearchResult,
    *,
    text: str,
    title: str,
    extraction_method: str,
    seen_hashes: set[str],
) -> ExtractedSource | None:
    normalized = (text or "").strip()
    if len(normalized) < 120:
        return None
    try:
        from core.extract.pdf_extractor import looks_like_decoded_binary, looks_like_pdf_text_dump

        if looks_like_pdf_text_dump(normalized):
            state.log(f"  PDF text dump rejected before source build: {result.url}")
            return None
        if looks_like_decoded_binary(normalized):
            state.log(f"  binary/text-garbage rejected before source build: {result.url}")
            return None
    except Exception:
        pass

    content_h = _content_hash(normalized)
    if content_h in seen_hashes:
        return None
    seen_hashes.add(content_h)

    try:
        relevant_chunks, _, entities = _prepare_relevant_chunks(state, normalized)
        relevance = compute_source_relevance(normalized[:12000], state.question)
    except Exception:
        relevant_chunks = normalized[:3000]
        entities = []
        relevance = 0.5

    # Apply source-type multiplier if the active content profile defines weights.
    _st_weights: dict[str, float] | None = getattr(state.config, "source_type_weights", None)
    if _st_weights:
        from services.deep_research.content_profiles import classify_source_type
        source_type = classify_source_type(result.url)
        weight = _st_weights.get(source_type, _st_weights.get("other", 1.0))
        if weight != 1.0:
            relevance = float(min(1.0, max(0.0, relevance * weight)))

    return ExtractedSource(
        url=result.url,
        title=(title or result.title or "").strip(),
        text=normalized,
        char_count=len(normalized),
        extraction_method=extraction_method,
        content_hash=content_h,
        relevant_chunks=relevant_chunks,
        entities=entities,
        relevance_score=float(relevance or 0.0),
    )


async def _recover_with_camoufox(
    state: ResearchState,
    failed_results: list[SearchResult],
    seen_hashes: set[str],
) -> tuple[list[ExtractedSource], set[str]]:
    if not failed_results or not is_camoufox_available():
        return [], set()

    registry = get_registry()
    camoufox_candidates = [
        result
        for result in failed_results
        if registry.needs_camoufox(result.url) or (result.method_hint or "").lower() in {"camoufox", "nodriver"}
    ]
    if not camoufox_candidates:
        return [], set()

    recovered: list[ExtractedSource] = []
    recovered_urls: set[str] = set()
    state.log(f"  Camoufox fallback: {len(camoufox_candidates)} URLs")
    results = await fetch_batch_with_camoufox(
        [result.url for result in camoufox_candidates],
        max_concurrency=2,
        timeout_sec=max(30.0, float(state.config.content_request_timeout) + 15.0),
        process_timeout=max(45.0, float(state.config.content_request_timeout) + 30.0),
    )
    by_url = {item.url: item for item in results}
    for result in camoufox_candidates:
        fetched = by_url.get(result.url)
        if fetched is None or not fetched.success:
            continue
        source = _build_source(
            state,
            result,
            text=fetched.text,
            title=fetched.title or result.title,
            extraction_method="camoufox",
            seen_hashes=seen_hashes,
        )
        if source is None:
            continue
        recovered.append(source)
        recovered_urls.add(result.url)
        _search_cache.cache_page(
            result.url,
            fetched.title or result.title,
            source.text,
            fetched.html,
            status="ok",
        )
    return recovered, recovered_urls


async def _recover_with_read_page(
    state: ResearchState,
    failed_results: list[SearchResult],
    seen_hashes: set[str],
) -> list[ExtractedSource]:
    if not failed_results:
        return []

    sem = asyncio.Semaphore(max(2, min(8, int(state.config.content_fetch_concurrency))))
    timeout = max(15.0, float(state.config.content_request_timeout) + 5.0)
    use_wayback = state.config.depth in ("high", "extra")

    async def _read_one(result: SearchResult) -> ExtractedSource | None:
        async with sem:
            text = await run_read_page(
                result.url,
                timeout=timeout,
                use_wayback_fallback=use_wayback,
                max_chars=40_000,
            )
        source = _build_source(
            state,
            result,
            text=_clean_read_page_output(text),
            title=result.title,
            extraction_method="read_page",
            seen_hashes=seen_hashes,
        )
        if source is not None:
            _search_cache.cache_page(
                result.url,
                source.title,
                source.text,
                raw_html="",
                status="ok",
            )
        return source

    state.log(f"  Read-page fallback: {len(failed_results)} URLs")
    recovered = await asyncio.gather(*[_read_one(result) for result in failed_results], return_exceptions=True)
    sources: list[ExtractedSource] = []
    for item in recovered:
        if isinstance(item, ExtractedSource):
            sources.append(item)
    return sources



# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def search_query_plans(
    state: ResearchState,
    query_plans: Iterable[QueryPlan],
    *,
    exclude_urls: set[str] | None = None,
) -> list[SearchResult]:
    """Search all query plans and append newly discovered raw results to state."""
    plans = [plan for plan in query_plans if plan.query.strip()]
    if not plans:
        return []

    cfg = state.config
    sem = asyncio.Semaphore(4)
    blocked_urls = set(state.raw_urls) | set(exclude_urls or set())

    async def _search_one(query: str) -> list[SearchResult]:
        async with sem:
            try:
                return await run_web_search_structured(
                    query=query,
                    max_results=cfg.max_results_per_query,
                    hard_timeout=min(
                        30.0,
                        max(10.0, cfg.search_timeout / max(1, len(plans))),
                    ),
                )
            except Exception as exc:
                state.log(f"  search failed for '{query}': {type(exc).__name__}: {exc}")
                return []

    batches = await asyncio.gather(*[_search_one(plan.query) for plan in plans])
    new_results: list[SearchResult] = []
    seen_urls = set(blocked_urls)
    for batch in batches:
        for result in batch:
            url = (result.url or "").strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            new_results.append(result)

    if new_results:
        state.raw_results.extend(new_results)
        state.raw_urls.update(result.url for result in new_results if result.url)
    state.log(f"  Search structured results: {len(new_results)} unique URLs from {len(plans)} queries")
    return new_results


async def extract_search_results(
    state: ResearchState,
    results: Iterable[SearchResult],
    *,
    existing_hashes: set[str] | None = None,
) -> list[ExtractedSource]:
    """Fetch and normalize full-page content for ranked search results."""
    cfg = state.config
    ranked_results = [result for result in results if (result.url or "").strip()]
    if not ranked_results:
        return []

    # Respect the search service's cheap pre-parse triage: low-score skipped
    # items are only used if the query returned nothing better.
    extraction_budget = max(1, int(cfg.max_urls_to_extract_per_pass))
    to_extract = ranked_results[:extraction_budget]
    state.log(
        f"  Primary extraction: {len(to_extract)}/{len(ranked_results)} URLs "
        f"(concurrency={max(1, int(cfg.content_fetch_concurrency))}, "
        f"timeout={max(1.0, float(cfg.content_request_timeout)):.1f}s)"
    )
    fetcher = PageFetcher(
        cache=_search_cache,
        max_concurrent=max(1, int(cfg.content_fetch_concurrency)),
        timeout=max(1.0, float(cfg.content_request_timeout)),
    )
    fetch_t0 = time.time()
    fetched = await fetcher.fetch_and_cache([result.url for result in to_extract], budget=len(to_extract))
    state.log(
        f"  Primary fetch/cache done: {sum(1 for item in fetched.values() if item is not None)}/"
        f"{len(to_extract)} cached in {time.time() - fetch_t0:.1f}s"
    )

    seen_hashes = set(existing_hashes or set())
    sources: list[ExtractedSource] = []
    failed_results: list[SearchResult] = []
    page_fetcher_hits = 0
    camoufox_hits = 0
    read_page_hits = 0
    build_t0 = time.time()
    slow_builds: list[tuple[float, str]] = []
    for result in to_extract:
        cached = fetched.get(result.url) or _search_cache.get_cached(result.url)
        if cached is None or cached.status != "ok":
            failed_results.append(result)
            continue
        one_t0 = time.time()
        source = _build_source(
            state,
            result,
            text=cached.clean_text,
            title=cached.title or result.title,
            extraction_method="page_fetcher",
            seen_hashes=seen_hashes,
        )
        one_dt = time.time() - one_t0
        if one_dt >= 2.0:
            slow_builds.append((one_dt, result.url))
        if source is None:
            failed_results.append(result)
            continue
        if cached.char_count:
            source.char_count = int(cached.char_count)
        sources.append(source)
        page_fetcher_hits += 1
    state.log(
        f"  Source build done: ok={page_fetcher_hits} failed={len(failed_results)} "
        f"in {time.time() - build_t0:.1f}s"
    )
    for one_dt, url in sorted(slow_builds, reverse=True)[:8]:
        state.log(f"    slow source build: {one_dt:.1f}s {url[:120]}")

    if failed_results and state.config.depth in ("high", "extra"):
        fallback_budget = min(
            len(failed_results),
            max(12, int(state.config.max_urls_to_extract_per_pass * 0.5)),
        )
        fallback_candidates = failed_results[:fallback_budget]
        state.log(
            f"  Extraction fallback queued: {len(fallback_candidates)}/{len(failed_results)} failed URLs"
        )
        fallback_t0 = time.time()
        camoufox_sources, recovered_urls = await _recover_with_camoufox(
            state,
            fallback_candidates,
            seen_hashes,
        )
        sources.extend(camoufox_sources)
        camoufox_hits = len(camoufox_sources)
        read_page_candidates = [
            result for result in fallback_candidates if result.url not in recovered_urls
        ]
        read_page_sources = await _recover_with_read_page(state, read_page_candidates, seen_hashes)
        sources.extend(read_page_sources)
        read_page_hits = len(read_page_sources)
        state.log(
            f"  Extraction fallback done: camoufox={camoufox_hits} "
            f"read_page={read_page_hits} in {time.time() - fallback_t0:.1f}s"
        )

    if failed_results:
        state.log(
            "  Extraction summary: "
            f"page_fetcher_ok={page_fetcher_hits} "
            f"camoufox_ok={camoufox_hits} "
            f"read_page_ok={read_page_hits} "
            f"failed_initial={len(failed_results)}"
        )
    return sources


async def harvest_query_plans(
    state: ResearchState,
    query_plans: Iterable[QueryPlan],
    *,
    exclude_urls: set[str] | None = None,
    existing_hashes: set[str] | None = None,
) -> tuple[list[SearchResult], list[ExtractedSource]]:
    """Search structured results, then extract full page content."""
    raw_results = await search_query_plans(state, query_plans, exclude_urls=exclude_urls)
    sources = await extract_search_results(state, raw_results, existing_hashes=existing_hashes)
    return raw_results, sources


async def run_harvest(
    state: ResearchState,
    query_plans: Iterable[QueryPlan] | None = None,
) -> PhaseResult:
    """Phase 2: first-pass structured search + full-content extraction."""
    t0 = time.time()
    cfg = state.config
    plans = list(query_plans or state.query_plans)
    if not plans:
        state.error("No query plans to harvest")
        return PhaseResult(phase_name="harvest", success=False, error="No query plans")

    state.log(
        f"Harvesting {len(plans)} queries, max_results={cfg.max_results_per_query}, "
        f"extract_limit={cfg.max_urls_to_extract_per_pass}"
    )
    _, sources = await harvest_query_plans(
        state,
        plans,
        existing_hashes={s.content_hash for s in state.extracted_sources},
    )
    state.extracted_sources.extend(sources)
    state.log(f"Harvested {len(sources)} extracted sources from {len(state.raw_results)} raw results")

    dt = time.time() - t0
    state.completed_phases.append("harvest")
    return PhaseResult(phase_name="harvest", items_produced=len(sources), duration_sec=dt)
