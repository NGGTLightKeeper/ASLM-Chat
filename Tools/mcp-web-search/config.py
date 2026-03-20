# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# Project path settings.
MCP_WEB_SEARCH_ROOT = Path(__file__).resolve().parent
DEEP_RESEARCH_ROOT = MCP_WEB_SEARCH_ROOT / "deep-research"

ROOT_DIR = DEEP_RESEARCH_ROOT
CONFIG_DIR = DEEP_RESEARCH_ROOT / "config"
OUTPUT_DIR = MCP_WEB_SEARCH_ROOT.parents[1] / "task" / "deep-research"
TRUST_REGISTRY_PATH = CONFIG_DIR / "trust_registry.json"


# Infrastructure endpoints.
LM_STUDIO_URL = "http://localhost:1234/v1"

YACY_URL = "http://localhost:8090"
YACY_USER = "admin"
YACY_PASS = "admin123"


# DDGS settings.
DDGS_PROXIES: list[str] = []
DDGS_CACHE_DB: Optional[str] = str(ROOT_DIR / "_cache" / "ddgs_cache.db")
DDGS_REQUEST_DELAY = (1.0, 2.5)


# Domain learning databases.
DOMAIN_PERF_DB: str = str(ROOT_DIR / "_cache" / "domain_performance.db")
DISCOVERED_ENDPOINTS_DB: str = str(ROOT_DIR / "_cache" / "discovered_endpoints.db")


# Direct routing settings.
DIRECT_DOMAIN_MIN_RESULTS: int = 3
DIRECT_DOMAIN_MAX_PER_QUERY: int = 8


# Endpoint discovery settings.
ENDPOINT_DISCOVERY_ENABLED: bool = True
ENDPOINT_PROBE_CONCURRENCY: int = 4
ENDPOINT_PROBE_TIMEOUT: float = 6.0
ENDPOINT_PROBE_RECHECK_TTL_SEC: int = 86400
ENDPOINT_PROMOTION_SUCCESS_COUNT: int = 2
ENDPOINT_DEACTIVATE_FAILURE_COUNT: int = 3
ENDPOINT_DISCOVERY_MAX_DOMAINS_PER_RUN: int = 12


# Camoufox profile settings.
CAMOUFOX_WARMUP_URLS: list[str] = [
    "https://www.wikipedia.org/",
    "https://developer.mozilla.org/en-US/",
    "https://www.python.org/",
]
CAMOUFOX_WARMUP_COUNT: int = 2
CAMOUFOX_PROFILE_LOCALES: list[str] = [
    "en-US",
    "en-GB",
    "en-CA",
    "de-DE",
]
CAMOUFOX_PROFILE_OS_WEIGHTS = {
    "windows": 0.68,
    "macos": 0.22,
    "linux": 0.10,
}


# Stealth engine toggles.
STEALTH_ENABLE_NODRIVER: bool = False
STEALTH_ENABLE_CAMOUFOX: bool = True


# LLM model names.
LLM_MODEL_QUERY_GEN = "local-model"
LLM_MODEL_SUMMARIZE = "local-model"
LLM_MODEL_SYNTHESIS = "local-model"


# ML model settings.
EMBEDDING_MODEL = "intfloat/multilingual-e5-small"
EMBEDDING_FORCE_CPU = False
GLINER_MODEL = "urchade/gliner_small-v2.1"
GLINER_FORCE_CPU = False
GLINER_THRESHOLD = 0.35
GLINER_THRESHOLD_RU = 0.25
GLINER_MIN_ENTITIES = 2


# Web preview settings.
WEB_SEARCH_MODE = "semantic"
WEB_SEARCH_SEMANTIC_REQUIRE_CUDA = False
WEB_SEARCH_SEMANTIC_TOP_K = 3
WEB_SEARCH_SEMANTIC_MIN_SCORE = 0.20
WEB_SEARCH_SEMANTIC_INPUT_CHAR_LIMIT = 12000
WEB_SEARCH_PREVIEW_LIMIT = 10
WEB_SEARCH_PREVIEW_CHAR_BUDGET = 6000
WEB_SEARCH_FETCH_TIMEOUT = 8.0
WEB_SEARCH_PREVIEW_TOTAL_TIMEOUT = 12.0


# Source filtering thresholds.
SOURCE_RELEVANCE_THRESHOLD = 0.50


# Research runtime configuration.
# Mutable deep-research runtime settings.
@dataclass
class ResearchConfig:
    """Store mutable runtime configuration for the deep-research pipeline."""

    depth: str = "medium"
    num_queries: int = 6
    max_sources: int = 23
    max_urls_to_extract_per_pass: int = 80
    ddgs_results_per_query: int = 15
    yacy_results_per_query: int = 4
    yacy_max_queries_per_pass: int = 4
    yacy_concurrency: int = 2
    enable_yacy: bool = False
    min_content_length: int = 200
    content_fetch_concurrency: int = 0
    content_fetch_auto_cap: int = 24
    content_request_timeout: float = 15.0
    content_extract_timeout: float = 45.0
    content_http_stage_timeout: float = 12.0
    content_stealth_stage_timeout: float = 18.0
    content_browser_stage_timeout: float = 20.0
    content_selenium_stage_timeout: float = 25.0
    content_enable_dead_link_precheck: bool = True
    content_precheck_timeout: float = 6.0
    content_precheck_concurrency: int = 16
    domain_perf_db: str = DOMAIN_PERF_DB
    discovered_endpoints_db: str = DISCOVERED_ENDPOINTS_DB
    direct_domain_min_results: int = DIRECT_DOMAIN_MIN_RESULTS
    direct_domain_max_per_query: int = DIRECT_DOMAIN_MAX_PER_QUERY
    endpoint_discovery_enabled: bool = ENDPOINT_DISCOVERY_ENABLED
    endpoint_probe_concurrency: int = ENDPOINT_PROBE_CONCURRENCY
    endpoint_probe_timeout: float = ENDPOINT_PROBE_TIMEOUT
    endpoint_probe_recheck_ttl_sec: int = ENDPOINT_PROBE_RECHECK_TTL_SEC
    endpoint_promotion_success_count: int = ENDPOINT_PROMOTION_SUCCESS_COUNT
    endpoint_deactivate_failure_count: int = ENDPOINT_DEACTIVATE_FAILURE_COUNT
    endpoint_discovery_max_domains_per_run: int = ENDPOINT_DISCOVERY_MAX_DOMAINS_PER_RUN
    camoufox_warmup_urls: list[str] = field(default_factory=lambda: list(CAMOUFOX_WARMUP_URLS))
    camoufox_warmup_count: int = CAMOUFOX_WARMUP_COUNT
    camoufox_profile_locales: list[str] = field(default_factory=lambda: list(CAMOUFOX_PROFILE_LOCALES))
    camoufox_profile_os_weights: dict = field(default_factory=lambda: dict(CAMOUFOX_PROFILE_OS_WEIGHTS))
    ddgs_month_fallback_enabled: bool = True
    ddgs_month_fallback_min_sources: int = 8
    max_chars_per_source: int = 4000
    enable_gliner: bool = False
    gliner_min_entities: int = GLINER_MIN_ENTITIES
    semantic_top_k: int = 5
    semantic_min_score: float = 0.20
    semantic_drop_bottom_fraction: float = 0.30
    semantic_model_init_timeout: float = 0.0
    semantic_filter_timeout: float = 180.0
    enable_playwright: bool = False
    enable_seleniumbase: bool = False
    enable_stealth: bool = True
    stealth_proxies: list = None
    stealth_max_concurrency: int = 4
    stealth_memory_threshold: float = 85.0
    stealth_enable_nodriver: bool = STEALTH_ENABLE_NODRIVER
    stealth_enable_camoufox: bool = STEALTH_ENABLE_CAMOUFOX
    max_iterations: int = 1
    max_sources_per_iteration: int = 15
    followup_queries_per_iteration: int = 4
    reflection_timeout_sec: float = 120.0
    iteration_search_timeout_sec: float = 240.0
    search_fallback_stage_timeout_sec: float = 120.0
    query_model: str = LLM_MODEL_QUERY_GEN
    enable_source_summaries: bool = False
    summarize_model: str = LLM_MODEL_SUMMARIZE
    summarize_parallel_agents: int = 1
    synthesis_model: str = LLM_MODEL_SYNTHESIS
    llm_timeout: float = 900.0
    synthesis_max_tokens: int = 16384
    synthesis_source_cap: int = 48
    synthesis_prompt_char_budget: int = 120000
    enable_background_swarm: bool = False
    background_swarm_min_iteration: int = 2
    background_swarm_poll_every: int = 2
    background_swarm_domains_cap: int = 32
    background_swarm_seed_urls_per_domain: int = 4
    background_swarm_discovery_depth: int = 3
    background_swarm_top_k: int = 64
    background_swarm_attach_cap_per_poll: int = 16
    background_swarm_ttl_sec: float = 1800.0
    background_swarm_max_urls_per_domain: int = 8
    background_swarm_max_concurrency: int = 12
    background_swarm_chunk_merge_chars: int = 3200
    background_swarm_min_chunk_relevance: float = 0.30
    background_swarm_final_wait_timeout_sec: float = 15.0
    domain_scoped_min_results: int = 3
    domain_scoped_max_domains: int = 4

    # Preset builders.
    # Build a preset from a named depth level.
    @classmethod
    def for_depth(cls, depth: str) -> "ResearchConfig":
        """Build a config preset for the requested depth level."""

        presets = {
            "low": dict(
                num_queries=4,
                max_sources=25,
                ddgs_results_per_query=10,
                yacy_results_per_query=3,
                yacy_max_queries_per_pass=2,
                yacy_concurrency=1,
                enable_gliner=False,
                max_iterations=2,
                max_sources_per_iteration=5,
                background_swarm_min_chunk_relevance=0.30,
            ),
            "medium": dict(
                num_queries=6,
                max_sources=40,
                ddgs_results_per_query=15,
                yacy_results_per_query=4,
                yacy_max_queries_per_pass=3,
                yacy_concurrency=2,
                max_iterations=4,
                max_sources_per_iteration=15,
                followup_queries_per_iteration=4,
                reflection_timeout_sec=90.0,
                iteration_search_timeout_sec=180.0,
                search_fallback_stage_timeout_sec=90.0,
                background_swarm_min_chunk_relevance=0.30,
            ),
            "high": dict(
                num_queries=10,
                max_sources=100,
                ddgs_results_per_query=20,
                yacy_results_per_query=6,
                yacy_max_queries_per_pass=4,
                yacy_concurrency=2,
                max_iterations=10,
                max_sources_per_iteration=30,
                followup_queries_per_iteration=5,
                reflection_timeout_sec=120.0,
                iteration_search_timeout_sec=240.0,
                search_fallback_stage_timeout_sec=120.0,
                max_chars_per_source=5000,
                enable_playwright=True,
                enable_seleniumbase=True,
                synthesis_source_cap=56,
                synthesis_prompt_char_budget=140000,
                enable_background_swarm=True,
                background_swarm_min_iteration=1,
                background_swarm_domains_cap=28,
                background_swarm_seed_urls_per_domain=3,
                background_swarm_discovery_depth=3,
                background_swarm_top_k=56,
                background_swarm_attach_cap_per_poll=14,
                background_swarm_ttl_sec=1500.0,
                background_swarm_max_urls_per_domain=7,
                background_swarm_max_concurrency=12,
                background_swarm_chunk_merge_chars=3000,
                background_swarm_min_chunk_relevance=0.28,
                background_swarm_final_wait_timeout_sec=15.0,
            ),
            "extra": dict(
                num_queries=14,
                max_sources=160,
                max_urls_to_extract_per_pass=120,
                ddgs_results_per_query=24,
                yacy_results_per_query=8,
                yacy_max_queries_per_pass=5,
                yacy_concurrency=2,
                max_iterations=14,
                max_sources_per_iteration=40,
                followup_queries_per_iteration=7,
                reflection_timeout_sec=120.0,
                iteration_search_timeout_sec=300.0,
                search_fallback_stage_timeout_sec=180.0,
                max_chars_per_source=6000,
                content_fetch_auto_cap=32,
                enable_playwright=True,
                enable_seleniumbase=False,
                enable_stealth=True,
                synthesis_source_cap=64,
                synthesis_prompt_char_budget=160000,
                enable_background_swarm=True,
                background_swarm_min_iteration=1,
                background_swarm_poll_every=1,
                background_swarm_domains_cap=36,
                background_swarm_seed_urls_per_domain=5,
                background_swarm_discovery_depth=3,
                background_swarm_top_k=72,
                background_swarm_attach_cap_per_poll=18,
                background_swarm_ttl_sec=1800.0,
                background_swarm_max_urls_per_domain=10,
                background_swarm_max_concurrency=14,
                background_swarm_chunk_merge_chars=3600,
                background_swarm_min_chunk_relevance=0.28,
                background_swarm_final_wait_timeout_sec=15.0,
                domain_scoped_min_results=4,
                domain_scoped_max_domains=5,
            ),
        }

        kwargs = presets.get(depth, {})
        return cls(depth=depth, **kwargs)
