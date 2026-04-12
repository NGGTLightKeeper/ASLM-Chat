# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""
Central configuration for the deep research pipeline.

All tuneable constants live here — timeouts, depth presets, synthesis
limits, query validation bounds.  Phase modules import what they need;
nothing should be hardcoded in the phase files themselves.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Phase timeouts  (seconds)
# orchestrator._run_phase() uses these as the asyncio.wait_for ceiling.
# Keep each value ~20s above the corresponding model-side timeout so that
# the inner aiohttp timeout fires first (and logs the reason) before the
# phase wrapper silently cancels the coroutine.
# ---------------------------------------------------------------------------

PHASE_TIMEOUTS: dict[str, float] = {
    "plan":             30.0,
    "harvest":         120.0,
    "triage":           60.0,
    "dedup_filter":     90.0,   # embedding is CPU-bound and can block the loop
    # synthesis_timeout in ResearchConfig is the aiohttp/LLM ceiling;
    # these are the outer asyncio.wait_for ceilings (20s larger).
    "synthesize_low":  320.0,   # model timeout: 300s (medium/low default)
    "synthesize_high": 320.0,   # model timeout: 300s (high/extra)
}


# ---------------------------------------------------------------------------
# Synthesis output limits
# ---------------------------------------------------------------------------

SYNTH_MAX_TOKENS_SINGLE: int = 8192   # single-shot synthesis (low / medium)
SYNTH_MAX_TOKENS_MERGE: int = 12288   # hierarchical merge pass (high / extra)
SYNTH_CHAR_BUDGET_PER_SOURCE: int = 2000  # default chars per source block


# ---------------------------------------------------------------------------
# Triage concurrency
# LMS (and most local inference servers) are single-threaded: parallel
# requests queue up.  Cap concurrent triage batches so total wall-time
# stays within triage_timeout and the server is not overwhelmed.
# ---------------------------------------------------------------------------

TRIAGE_MAX_CONCURRENT_BATCHES: int = 3
# Conservative per-batch time budget used to compute dynamic phase timeout.
# Should be slightly above the observed p90 per-batch latency on a typical local LLM.
TRIAGE_BATCH_BUDGET_SEC: float = 35.0

# Cluster synthesis concurrency (high/extra depth).
# LMS is single-threaded, so requests queue server-side, but parallel dispatch
# reduces Python-side scheduling overhead and lets faster clusters complete sooner.
SYNTH_MAX_CONCURRENT_CLUSTERS: int = 3


# ---------------------------------------------------------------------------
# Query planning limits
# ---------------------------------------------------------------------------

# Validation applied to LLM-generated query strings.
PLAN_QUERY_MAX_WORDS: int = 8
PLAN_QUERY_MAX_CHARS: int = 80

# Validation applied to the raw question used as a fallback query.
PLAN_FALLBACK_MAX_WORDS: int = 6
PLAN_FALLBACK_MAX_CHARS: int = 70


# ---------------------------------------------------------------------------
# Research configuration (depth presets)
# ---------------------------------------------------------------------------

@dataclass
class ResearchConfig:
    """Tuning knobs per research depth level.

    Instantiate via ``ResearchConfig.for_depth(depth)`` to get a fully
    configured object for a given depth preset.
    """

    depth: str = "medium"

    # Phase 1 — plan
    num_queries: int = 7
    query_model: str = "local-model"

    # Phase 2 — harvest
    max_results_per_query: int = 15
    max_urls_to_extract_per_pass: int = 80
    fetch_previews: bool = True
    search_timeout: float = 120.0
    content_fetch_concurrency: int = 6
    content_request_timeout: float = 10.0
    harvest_relevant_chunks_max_chars: int = 3000
    harvest_full_text_tolerance_chars: int = 100
    harvest_chunk_size_chars: int = 900
    harvest_chunk_overlap_chars: int = 120
    harvest_gliner_chunk_limit: int = 32

    # Phase 3 — triage
    enable_triage: bool = False       # legacy: initial + per-iteration triage (disabled)
    triage_before_synth: bool = False  # run triage once on final pool, just before synthesis
    triage_batch_size: int = 4
    triage_model: str = ""        # empty → use query_model
    triage_timeout: float = 60.0

    # Phase 4 — dedup / filter
    minhash_threshold: float = 0.70   # MinHash: removes near-exact text copies
    embedding_threshold: float = 0.93  # Cosine sim: only remove near-identical docs
    use_embeddings: bool = True
    use_gliner: bool = True
    min_entity_density: int = 2
    dedup_min_sources: int = 3         # never drop below this after dedup (unless we started with fewer)
    dedup_cooldown_ratio: float = 0.10 # only re-run iteration dedup when pool grew by ≥ this fraction
    dedup_min_new_sources: int = 3     # absolute: always run dedup if ≥ this many new sources added

    # Phase 5 — synthesize
    # synthesis_timeout is the aiohttp / LLM-side ceiling passed to call_llm();
    # the outer asyncio.wait_for ceiling is PHASE_TIMEOUTS["synthesize_*"].
    synthesis_model: str = ""     # empty → use query_model
    synthesis_batch_char_budget: int = 60_000
    synthesis_prompt_char_budget: int = 120_000
    synthesis_merge_grounding_source_fraction: float = 0.30
    synthesis_merge_grounding_char_ratio: float = 0.30
    synthesis_timeout: float = 300.0
    synthesis_source_cap: int = 48
    synthesis_min_source_quality: float = 0.55
    final_source_cleanup_enabled: bool = True
    final_source_rank_model: str = ""
    final_source_rank_batch_size: int = 8
    final_source_rank_timeout_sec: float = 90.0
    enable_source_summaries: bool = False

    # Orchestrator
    max_sources: int = 40
    max_iterations: int = 2
    max_sources_per_iteration: int = 15
    followup_queries_per_iteration: int = 4
    reflection_timeout_sec: float = 90.0
    reflection_prompt_char_budget: int = 15_000
    iteration_search_timeout_sec: float = 180.0
    inference_cpu_timeout_multiplier: float = 2.0
    total_hard_timeout: float = 600.0

    # LLM structured output / reasoning
    structured_output_enabled: bool = True
    structured_output_strict: bool = True
    reasoning_effort: str = "low"
    reasoning_tokens: int = 2048
    concise_reasoning_prompt: str = "Be concise. Think briefly before answering."

    # reflection_temperature: 0.0 means "not set" → uses 0.4 default in reflection.py
    reflection_temperature: float = 0.0

    @classmethod
    def for_depth(cls, depth: str) -> "ResearchConfig":
        """Return a ResearchConfig pre-configured for *depth*."""
        presets: dict[str, dict[str, Any]] = {
            "low": dict(
                num_queries=4,
                max_results_per_query=10,
                max_sources=25,
                max_iterations=2,
                max_sources_per_iteration=10,
                max_urls_to_extract_per_pass=40,
                use_embeddings=False,
                use_gliner=False,
                synthesis_timeout=240.0,
                total_hard_timeout=360.0,
            ),
            "medium": dict(
                num_queries=6,
                max_results_per_query=15,
                max_sources=45,
                max_iterations=4,
                max_sources_per_iteration=20,
                followup_queries_per_iteration=4,
                reflection_timeout_sec=90.0,
                reflection_prompt_char_budget=18_000,
                iteration_search_timeout_sec=180.0,
            ),
            "high": dict(
                num_queries=10,
                max_results_per_query=20,
                max_sources=80,
                max_iterations=10,
                max_sources_per_iteration=40,
                followup_queries_per_iteration=5,
                reflection_timeout_sec=120.0,
                reflection_prompt_char_budget=22_000,
                reflection_temperature=0.65,
                iteration_search_timeout_sec=360.0,
                max_urls_to_extract_per_pass=80,
                content_fetch_concurrency=12,
                content_request_timeout=18.0,
                triage_batch_size=6,
                synthesis_timeout=300.0,
                total_hard_timeout=1800.0,
                synthesis_source_cap=56,
                final_source_rank_batch_size=8,
                synthesis_batch_char_budget=70_000,
                synthesis_prompt_char_budget=140_000,
            ),
            "extra": dict(
                num_queries=14,
                max_results_per_query=25,
                max_sources=100,
                max_iterations=14,
                max_sources_per_iteration=60,
                followup_queries_per_iteration=7,
                reflection_timeout_sec=120.0,
                reflection_prompt_char_budget=28_000,
                reflection_temperature=0.70,
                iteration_search_timeout_sec=480.0,
                max_urls_to_extract_per_pass=100,
                content_fetch_concurrency=14,
                content_request_timeout=22.0,
                triage_batch_size=6,
                synthesis_timeout=300.0,
                total_hard_timeout=2400.0,
                synthesis_source_cap=64,
                final_source_rank_batch_size=10,
                synthesis_batch_char_budget=80_000,
                synthesis_prompt_char_budget=160_000,
            ),
        }
        cfg = cls(depth=depth)
        for key, value in presets.get(depth, {}).items():
            setattr(cfg, key, value)
        return cfg
