# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""
Phase 1 — Query Planning.

Generates a batch of diverse sub-queries from the user's research question
via structured LLM output.  Falls back to keyword-based queries if LLM fails.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from services.deep_research.config import (
    PLAN_FALLBACK_MAX_CHARS,
    PLAN_FALLBACK_MAX_WORDS,
    PLAN_QUERY_MAX_CHARS,
    PLAN_QUERY_MAX_WORDS,
)
from services.deep_research.models import (
    PhaseResult,
    QueryPlan,
    ResearchState,
)
from core.llm.llm_client import call_llm_json


# ---------------------------------------------------------------------------
# JSON schemas for structured output
# ---------------------------------------------------------------------------

def _query_plan_schema(count: int) -> Dict[str, Any]:
    # Array of plain query strings — no target_domains.
    # target_domains was never used by the harvester and caused the model to
    # hallucinate domain names, wasting tokens.
    # minItems=1: partial output is still useful; fallback fills missing slots.
    return {
        "type": "array",
        "minItems": 1,
        "maxItems": max(1, count),
        "items": {"type": "string", "minLength": 2, "maxLength": 80},
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_KEYWORD_CATEGORIES = {
    "technical": [
        "api", "code", "python", "javascript", "typescript", "library",
        "framework", "docker", "kubernetes", "git", "npm", "pip",
        "linux", "server", "database", "sql", "rust", "golang",
    ],
    "academic": [
        "paper", "research", "study", "experiment", "hypothesis",
        "arxiv", "pubmed", "journal", "dataset", "methodology",
    ],
    "medical": [
        "patient", "disease", "treatment", "clinical", "diagnosis",
        "gene", "protein", "biomarker", "cancer", "therapy", "drug",
    ],
    "finance": [
        "revenue", "market", "stock", "invest", "profit",
        "earnings", "valuation", "ipo", "fund", "crypto",
    ],
    "journalistic": [
        "latest", "news", "announced", "released", "launched",
        "update", "2024", "2025", "2026", "today", "yesterday",
    ],
    "shopping": [
        "buy", "price", "cheap", "discount", "review", "best",
        "purchase", "deal", "offer", "comparison", "recommend",
        "worth it", "vs", "alternative", "cost",
    ],
    "troubleshooting": [
        "error", "fix", "issue", "problem", "not working", "debug",
        "crash", "broken", "solution", "failed", "bug", "trouble",
        "how to fix", "resolve", "workaround", "exception",
    ],
    "forum": [
        "reddit", "forum", "discussion", "thread", "community",
        "opinion", "experience", "advice", "what do you think",
        "anyone know", "has anyone", "help me", "i need help",
    ],
}


def classify_query(question: str) -> str:
    """Infer the query category from keyword matching."""
    q = question.lower()
    scores = {cat: sum(1 for kw in kws if kw in q) for cat, kws in _KEYWORD_CATEGORIES.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "general"


# Common English words that are not useful as core search terms.
_EN_STOPWORDS: frozenset[str] = frozenset({
    "the", "and", "for", "are", "was", "were", "has", "have", "had",
    "how", "what", "why", "when", "where", "who", "which", "does",
    "did", "can", "could", "will", "would", "should", "its", "that",
    "this", "these", "those", "with", "from", "into", "than", "then",
    "they", "them", "their", "there", "here", "some", "such", "each",
    "also", "more", "most", "very", "just", "both", "only", "over",
    "after", "about", "above", "being", "been", "make", "made",
    "many", "other", "under", "used", "using", "use", "compare",
    "between", "versus", "difference", "explain", "describe",
})

# Standard aspects used to expand a core term into diverse queries.
# Ordered so the most broadly useful aspects come first — earlier entries are
# more likely to be included when target_count is small.
_FALLBACK_ASPECTS: List[str] = [
    "",                       # bare term (most direct search)
    "overview",
    "tutorial",
    "documentation",
    "examples",
    "how it works",
    "architecture",
    "benchmark",
    "comparison alternatives",
    "use cases",
    "limitations",
    "paper arxiv",
    "github",
    "installation guide",
]


def _keyword_fallback_queries(question: str, target_count: int) -> List[str]:
    """Build diverse English search queries when the LLM fails to produce plans.

    Extracts meaningful ASCII technical terms from the question (e.g. "GLiNER"
    from "что такое GLiNER" or ["nodriver", "playwright"] from "how does
    nodriver compare to playwright"), combines them with standard research
    aspects, and returns up to *target_count* validated queries.

    Falls back to the raw question (truncated) if no ASCII terms are found.
    """
    raw_tokens = re.findall(r'\b[A-Za-z][A-Za-z0-9\-\.]{2,}\b', question)
    # Drop short words (≤3 chars) and common English stopwords — keep only
    # meaningful domain terms like library names, proper nouns, technical jargon.
    en_tokens = [t for t in raw_tokens if len(t) >= 4 and t.lower() not in _EN_STOPWORDS]

    if not en_tokens:
        # Pure non-Latin question or all stopwords: use truncated raw question.
        validated = _validate_queries(
            [question],
            max_words=PLAN_FALLBACK_MAX_WORDS,
            max_chars=PLAN_FALLBACK_MAX_CHARS,
        )
        return validated[:target_count] or [question[:60].strip()]

    # Use first 3 meaningful tokens as the core search phrase.
    core = " ".join(en_tokens[:3])
    raw: List[str] = []
    for aspect in _FALLBACK_ASPECTS:
        if len(raw) >= target_count:
            break
        raw.append(f"{core} {aspect}".strip() if aspect else core)

    return _validate_queries(
        raw,
        max_words=PLAN_QUERY_MAX_WORDS,
        max_chars=PLAN_QUERY_MAX_CHARS,
    )[:target_count]


def _validate_queries(queries: List[str], max_words: int = 12, max_chars: int = 100) -> List[str]:
    valid: List[str] = []
    for q in queries:
        q = " ".join(q.split()).strip()
        if not q:
            continue
        words = q.split()
        if len(words) > max_words:
            q = " ".join(words[:max_words])
        if len(q) > max_chars:
            q = q[:max_chars].rsplit(" ", 1)[0]
        if len(q) >= 3:
            valid.append(q)
    return valid


def _parse_plans(
    payload: object,
    fallback_queries: List[str],
) -> List[QueryPlan]:
    """Parse LLM output into QueryPlan list, falling back to keywords."""
    plans: List[QueryPlan] = []

    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, str):
                plans.append(QueryPlan(query=item))
            elif isinstance(item, dict):
                query_text = str(item.get("query", ""))
                raw_td = item.get("target_domains")
                domains = (
                    [str(d.get("domain", "") if isinstance(d, dict) else d) for d in raw_td]
                    if isinstance(raw_td, list) else []
                )
                plans.append(QueryPlan(query=query_text, target_domains=domains))
    elif isinstance(payload, dict):
        for key in ("query_plans", "queries"):
            nested = payload.get(key)
            if isinstance(nested, list):
                return _parse_plans(nested, fallback_queries)

    # Validate
    valid_plans: List[QueryPlan] = []
    seen: set[str] = set()
    for p in plans:
        validated = _validate_queries([p.query], max_words=PLAN_QUERY_MAX_WORDS, max_chars=PLAN_QUERY_MAX_CHARS)
        if not validated:
            continue
        key = validated[0].strip().lower()
        if key in seen:
            continue
        seen.add(key)
        valid_plans.append(QueryPlan(query=validated[0], target_domains=p.target_domains))

    if not valid_plans:
        for q in fallback_queries:
            valid_plans.append(QueryPlan(query=q))
    return valid_plans


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def run_plan(state: ResearchState) -> PhaseResult:
    """Phase 1: generate research sub-queries via structured LLM output."""
    import time
    t0 = time.time()
    cfg = state.config

    state.query_type = classify_query(state.question)
    state.log(f"Query type: {state.query_type}")

    prompt = (
        f"Generate up to {cfg.num_queries} search queries for deep web research.\n\n"
        f"Question:\n\"{state.question}\"\n\n"
        "Return ONLY a JSON array of short English search strings.\n"
        "Example: [\"GLiNER named entity recognition\", \"GLiNER tutorial huggingface\", \"GLiNER documentation usage\"]\n\n"
        "Rules:\n"
        "- Each query: 2-6 words, English only, no punctuation\n"
        "- Each query must cover a DIFFERENT aspect or angle\n"
        "- No markdown, no extra keys, only the JSON array\n"
    )

    # Budget enough tokens for all queries: each item ≈ 60-80 tokens
    # (query text + target_domains + JSON structure overhead).
    _plan_max_tokens = max(512, cfg.num_queries * 80)

    # Use 5s less than the phase timeout so aiohttp fires first and the
    # fallback logic below (keyword queries) can still run gracefully.
    _plan_phase_timeout = 30.0  # must match PHASE_TIMEOUTS["plan"] in config.py
    raw = await call_llm_json(
        prompt=prompt,
        model=cfg.query_model,
        temperature=0.2,
        max_tokens=_plan_max_tokens,
        timeout=_plan_phase_timeout - 5.0,
        json_schema=_query_plan_schema(cfg.num_queries),
        schema_name="research_query_plans",
        structured_output=cfg.structured_output_enabled,
        strict=cfg.structured_output_strict,
        # Query planning is pure structured generation — reasoning tokens burn
        # output budget without adding value here.  Disable explicitly.
        reasoning_effort="",
        reasoning_tokens=0,
        concise_reasoning_prompt=cfg.concise_reasoning_prompt,
        debug_label="query-planning",
        debug_log=state.log,
    )

    fallback = _keyword_fallback_queries(state.question, cfg.num_queries)

    if raw is None:
        state.log("WARNING: LLM returned no parseable JSON for query planning — using keyword fallback")
    elif not isinstance(raw, list) or len(raw) == 0:
        state.log(f"WARNING: LLM query plan parse yielded {type(raw).__name__} — using keyword fallback")

    plans = _parse_plans(raw, fallback or ["research topic overview"])
    plans = plans[:max(2, cfg.num_queries)]

    if len(plans) < cfg.num_queries:
        state.log(f"WARNING: got {len(plans)}/{cfg.num_queries} query plans (some were invalid or LLM output was partial)")

    state.query_plans = plans
    state.log(f"Generated {len(plans)} query plans:")
    for i, p in enumerate(plans, 1):
        state.log(f"  {i}. {p.query}")

    dt = time.time() - t0
    state.completed_phases.append("plan")
    return PhaseResult(phase_name="plan", items_produced=len(plans), duration_sec=dt)
