# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

import asyncio
import hashlib
import json
import re
import socket
import sys
import time
import warnings
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import quote_plus, urlparse

import aiohttp

try:
    from urllib3.exceptions import InsecureRequestWarning
    warnings.simplefilter('ignore', InsecureRequestWarning)
except ImportError:
    pass

if sys.platform.startswith("win"):
    # Some external browser backends leak subprocess transports on shutdown on Windows.
    # Guard __del__ against ValueError to avoid noisy trace spam in final CLI output.
    try:
        import asyncio.proactor_events as _proactor_events
        import asyncio.base_subprocess as _base_subprocess

        _orig_pipe_del = _proactor_events._ProactorBasePipeTransport.__del__
        _orig_subproc_del = _base_subprocess.BaseSubprocessTransport.__del__

        # Silence transport cleanup noise on Windows shutdown.
        def _safe_pipe_del(self):
            try:
                _orig_pipe_del(self)
            except Exception:
                pass

        # Silence subprocess cleanup noise on Windows shutdown.
        def _safe_subproc_del(self):
            try:
                _orig_subproc_del(self)
            except Exception:
                pass

        _proactor_events._ProactorBasePipeTransport.__del__ = _safe_pipe_del
        _base_subprocess.BaseSubprocessTransport.__del__ = _safe_subproc_del
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import (
    DDGS_CACHE_DB,
    DDGS_PROXIES,
    DIRECT_DOMAIN_MAX_PER_QUERY,
    DIRECT_DOMAIN_MIN_RESULTS,
    OUTPUT_DIR,
    ResearchConfig,
)
from src.models import ExtractedSource, QueryPlan, ResearchState, SearchResult
from src.ddgs_client import async_ddgs_search, get_ddgs_client
from src.domain_performance import get_domain_performance
from src.domain_registry import get_registry
from src.endpoint_overlay import (
    ProbeCandidate,
    build_probe_candidates,
    get_endpoint_overlay,
    normalize_domain,
    validate_candidate_payload,
)
from src.llm_client import call_llm, call_llm_json, close_session as close_llm_session
from src.extractor import extract_content, DEFAULT_HTTP_HEADERS
from src.utils.text import sanitize_content, SAFETY_PREFIX
from src.probe_scheduler import EndpointProbeScheduler
from src.background_agent.swarm_utils import (
    start_background_swarm,
    drain_background_swarm,
    cleanup_background_swarm,
)

# Initialize the DDGS client and cache during import.
_cache_dir = Path(DDGS_CACHE_DB).parent if DDGS_CACHE_DB else None
if _cache_dir and not _cache_dir.exists():
    _cache_dir.mkdir(parents=True, exist_ok=True)
get_ddgs_client(proxies=DDGS_PROXIES, cache_db=DDGS_CACHE_DB)
_DOMAIN_REGISTRY = get_registry()
_ENDPOINT_OVERLAY = get_endpoint_overlay()


# Stage 1: Classification.

# Query classification helpers.
def classify_query(question: str) -> str:
    q = question.lower()
    keywords = {
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
    }
    scores = {cat: sum(1 for kw in kws if kw in q) for cat, kws in keywords.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "general"


# Query language helpers.
def _detect_language(text: str) -> str:
    cyrillic = sum(1 for c in text if 0x0400 <= ord(c) <= 0x04FF)
    return "ru" if cyrillic > len(text) * 0.3 else "en"


# Query language helpers.
def _strip_cyrillic(text: str) -> str:
    """Remove Cyrillic words from a query, keeping Latin/numeric terms.
    Used for site: scoped queries because DDG can fail on Cyrillic + site: combos."""
    import re
    words = text.split()
    latin_words = [
        w for w in words if not any(0x0400 <= ord(ch) <= 0x04FF for ch in w)
    ]
    return " ".join(latin_words)


# Query validation helpers.
def _validate_queries(queries: List[str], max_words: int = 12, max_chars: int = 100) -> List[str]:
    """Validate and trim generated search queries."""
    valid = []
    for q in queries:
        q = q.strip()
        if not q:
            continue
        # Remove line breaks.
        q = " ".join(q.split())
        # If the query is too long, keep only the first max_words words.
        words = q.split()
        if len(words) > max_words:
            q = " ".join(words[:max_words])
        # Hard character limit.
        if len(q) > max_chars:
            q = q[:max_chars].rsplit(" ", 1)[0]
        if len(q) >= 3:
            valid.append(q)
    return valid


_METHOD_HINTS = {
    "auto",
    "http",
    "xml_feed",
    "json_api",
    "official_api",
    "nodriver",
    "camoufox",
    "stealth",
}
_QUERY_TOKEN_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "how", "what", "when",
    "where", "into", "about", "over", "under", "using", "guide", "best", "latest",
}
_NO_HEURISTIC_DOMAINS = {
    # Domains with real API connectors where heuristic /?q= paths are irrelevant.
    "arxiv.org",
    "pubmed.ncbi.nlm.nih.gov",
    "ncbi.nlm.nih.gov",
    "semanticscholar.org",
    "wikipedia.org",
    "github.com",
    "wikidata.org",
    "pypi.org",
    "npmjs.com",
    "stackoverflow.com",
    "stackexchange.com",
    "huggingface.co",
    # News / media sites whose search is JS-rendered or returns empty HTML to bots
    "bbc.com",
    "bbc.co.uk",
    "tass.ru",
    "lenta.ru",
    "arstechnica.com",
    "theverge.com",
    "reuters.com",
    # Community sites where search is either API-only or JS-rendered.
    "news.ycombinator.com",
    "reddit.com",
    "medium.com",
    "habr.com",
    # Generic aggregators / paywalled sites
    "linkedin.com",
}


# Query planning helpers.
def _normalize_method_hint(value: Optional[str]) -> str:
    hint = (value or "auto").strip().lower()
    return hint if hint in _METHOD_HINTS else "auto"


# Query planning helpers.
def _unique_domains(values: Iterable[str], limit: int) -> List[str]:
    seen = set()
    result: List[str] = []
    for value in values:
        d = normalize_domain(value)
        if not d or d in seen:
            continue
        seen.add(d)
        result.append(d)
        if len(result) >= limit:
            break
    return result


# Query planning helpers.
def _query_tokens(query: str) -> List[str]:
    parts = re.findall(r"[A-Za-z0-9][A-Za-z0-9._+-]{1,}", (query or "").lower())
    tokens = [p for p in parts if p not in _QUERY_TOKEN_STOPWORDS and len(p) > 2]
    return tokens[:8]


# Query planning helpers.
def _is_direct_candidate_relevant(plan_query: str, result: SearchResult) -> bool:
    tokens = _query_tokens(plan_query)
    if not tokens:
        return True
    haystack = f"{result.title} {result.snippet} {result.url}".lower()
    hit_count = sum(1 for token in tokens if token in haystack)
    return hit_count >= 1


# NOTE: _normalize_domain was removed; use normalize_domain from endpoint_overlay.


# Query planning helpers.
def _parse_query_plans_payload(
    payload: object,
    fallback_queries: List[str],
    default_domains: List[str],
    max_target_domains: int,
) -> List[QueryPlan]:
    plans: List[QueryPlan] = []

    # Query planning helpers.
    def _append_plan(query_text: str, target_domains: Optional[List[str]], method_hint: Optional[str]) -> None:
        q = _validate_queries([query_text])
        if not q:
            return
        plans.append(
            QueryPlan(
                query=q[0],
                target_domains=_unique_domains(target_domains or default_domains, max_target_domains),
                method_hint=_normalize_method_hint(method_hint),
            )
        )

    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, str):
                _append_plan(item, default_domains, "auto")
            elif isinstance(item, dict):
                raw_td = item.get("target_domains")
                if isinstance(raw_td, list):
                    # LLM may return dicts like {"domain": "x.com"}, so extract string values.
                    target_domains = [
                        str(d.get("domain") or d.get("url") or next(iter(d.values()), ""))
                        if isinstance(d, dict) else str(d)
                        for d in raw_td
                    ]
                else:
                    target_domains = default_domains
                _append_plan(
                    str(item.get("query", "")),
                    target_domains,
                    item.get("method_hint"),
                )
    elif isinstance(payload, dict):
        raw_plans = payload.get("query_plans")
        if isinstance(raw_plans, list):
            return _parse_query_plans_payload(raw_plans, fallback_queries, default_domains, max_target_domains)

        raw_queries = payload.get("queries")
        if isinstance(raw_queries, list):
            return _parse_query_plans_payload(raw_queries, fallback_queries, default_domains, max_target_domains)

    if not plans:
        for q in fallback_queries:
            _append_plan(q, default_domains, "auto")

    deduped: List[QueryPlan] = []
    seen_queries = set()
    for p in plans:
        key = p.query.strip().lower()
        if not key or key in seen_queries:
            continue
        seen_queries.add(key)
        deduped.append(p)
    return deduped


# Query planning stage.
async def generate_query_plans(state: ResearchState) -> List[QueryPlan]:
    cfg = state.config
    topic = _DOMAIN_REGISTRY.topic_from_query_type(state.query_type)
    domain_perf = get_domain_performance(getattr(cfg, "domain_perf_db", None))
    default_domains = _DOMAIN_REGISTRY.rank_domains_for_topic(
        topic,
        limit=max(1, int(getattr(cfg, "direct_domain_max_per_query", DIRECT_DOMAIN_MAX_PER_QUERY))),
        domain_performance=domain_perf,
    )
    state.log(
        f"Query plans for topic='{topic}' default_domains={default_domains[:4]}"
    )

    prompt = (
        f"Generate EXACTLY {cfg.num_queries} structured search plans for deep web research.\n\n"
        f"Question:\n\"{state.question}\"\n\n"
        "Return ONLY valid JSON array. Each item:\n"
        "{\n"
        "  \"query\": \"short english search query\",\n"
        "  \"target_domains\": [\"example.org\", \"example.com\"]\n"
        "}\n\n"
        "Rules:\n"
        "- query: 2-6 words, English, no punctuation\n"
        "- target_domains: 1-3 domains directly relevant to THIS specific query subtopic\n"
        "  * Use the official project site, docs, or well-known communities for the topic\n"
        "  * Do NOT add generic aggregators (arxiv.org, medium.com, reddit.com) unless the query is specifically about discussions\n"
        "  * Do NOT invent domain names, only use real, well-known domains\n"
        "  * Do NOT use full URLs, only bare domain names (e.g. 'github.com', not 'github.com/user/repo')\n"
        "- no markdown, no explanations, only JSON array\n"
    )
    raw = await call_llm_json(prompt=prompt, model=cfg.query_model, temperature=0.4)

    fallback_queries = _validate_queries([state.question], max_words=6, max_chars=70)
    plans = _parse_query_plans_payload(
        payload=raw,
        fallback_queries=fallback_queries,
        default_domains=default_domains,
        max_target_domains=max(1, int(getattr(cfg, "direct_domain_max_per_query", DIRECT_DOMAIN_MAX_PER_QUERY))),
    )

    # Query planning helpers.
    def _plan_quality(plan: QueryPlan) -> bool:
        words = len((plan.query or "").split())
        return 2 <= words <= 8 and len(plan.query or "") <= 80

    plans = [p for p in plans if _plan_quality(p)]

    if len(plans) < max(2, cfg.num_queries // 2):
        generated_queries = await generate_search_queries(state)
        generated_plans = [
            QueryPlan(
                query=q,
                target_domains=list(default_domains),
                method_hint="auto",
            )
            for q in generated_queries
        ]
        merged: List[QueryPlan] = []
        seen = set()
        for p in (plans + generated_plans):
            key = p.query.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(p)
        plans = [p for p in merged if _plan_quality(p)]

    if not plans:
        safe_queries = _validate_queries([state.question], max_words=6, max_chars=70)
        safe_query = safe_queries[0] if safe_queries else "research topic overview"
        plans = [
            QueryPlan(
                query=safe_query,
                target_domains=list(default_domains),
                method_hint="auto",
            )
        ]

    plans = plans[: max(2, int(cfg.num_queries))]

    # Resolve method_hint from registry and overlay data instead of trusting the LLM.
    _resolve_plan_methods(plans)

    state.log(f"Query plans generated: {len(plans)}")
    for idx, plan in enumerate(plans, 1):
        domains_preview = ", ".join(plan.target_domains[:3]) if plan.target_domains else "-"
        state.log(f"   {idx}. {plan.query} | {plan.method_hint} | {domains_preview}")
    return plans


# Query planning helpers.
def _resolve_plan_methods(plans: List[QueryPlan]) -> None:
    """
    Fill method_hint for each plan based on domain_registry + endpoint_overlay.
    LLM is not involved; access method is determined by the registry and overlay data.

    Priority per domain (first one wins):
      1. endpoint_overlay (dynamically discovered APIs/feeds)
      2. domain_registry static entry
      3. fallback: "http"
    """
    overlay = get_endpoint_overlay()
    for plan in plans:
        if not plan.target_domains:
            plan.method_hint = "auto"
            continue

        # Use the primary (first) target domain to determine method.
        primary = plan.target_domains[0]
        domain = normalize_domain(primary)

        # 1. Check overlay first (discovered feeds/APIs take precedence).
        ep = overlay.lookup_validated(domain, primary)
        if ep is not None:
            plan.method_hint = ep.method
            continue

        # 2. Static registry.
        method = _DOMAIN_REGISTRY.choose_method(domain)
        plan.method_hint = method if method else "auto"


# EndpointProbeScheduler is now in src/probe_scheduler.py.


# All swarm functions are now in src/background_agent/swarm_utils.py.


# Stage 2: Multilingual sub-query generation.

# Query generation stage.
async def generate_search_queries(state: ResearchState) -> List[str]:
    cfg = state.config
    lang = _detect_language(state.question)
    state.log(f"Generating {cfg.num_queries} sub-queries (language: {lang})...")

    multilingual_instruction = """
- CRITICAL: ALL search queries MUST be in English only, translate topic if needed.
- Each query MUST be focused on the core topic of the question.
- Keep queries AS SHORT AS POSSIBLE (2-5 words max)."""

    prompt = f"""You are a research assistant. Generate {cfg.num_queries} diverse search queries \
to comprehensively research this question:

"{state.question}"

Requirements:
- Each query explores a DIFFERENT aspect (setup, benchmarks, comparison, troubleshooting, alternatives)
- No full sentences, no question marks
- Generate EXACTLY {cfg.num_queries} queries
{multilingual_instruction}

EXAMPLE: if the question was "How does PostgreSQL replication work?", correct output:
["PostgreSQL replication setup", "PostgreSQL streaming replication config", "PostgreSQL replication performance", "PostgreSQL logical vs physical replication", "PostgreSQL high availability tools", "PostgreSQL replication lag troubleshooting", "PostgreSQL replication alternatives"]

Return ONLY a valid JSON array with exactly {cfg.num_queries} string elements, no other text:
["query1", "query2", "query3", ...]"""

    result = await call_llm_json(prompt=prompt, model=cfg.query_model, temperature=0.5)

    if isinstance(result, list) and all(isinstance(q, str) for q in result):
        seen = set()
        unique = []
        for q in result:
            key = q.strip().lower()
            if key and key not in seen:
                seen.add(key)
                unique.append(q.strip())

        if len(unique) < max(2, cfg.num_queries // 2):
            aspects = ["overview", "technical specs", "pricing", "API", "comparison",
                       "benchmark", "tutorial", "pros cons", "alternatives"]
            # Use the first 5 words of the question as the fallback subject.
            words = state.question.strip().split()
            subject = " ".join(words[:5])
            for aspect in aspects:
                candidate = f"{subject} {aspect}"
                if candidate.lower() not in seen:
                    seen.add(candidate.lower())
                    unique.append(candidate)
                if len(unique) >= cfg.num_queries:
                    break

        state.log(f"{len(unique)} queries:")
        for i, q in enumerate(unique, 1):
            state.log(f"   {i}. {q}")

        # Validate and trim oversized queries.
        validated = _validate_queries(unique[:cfg.num_queries])
        return validated

    state.error("Failed to parse generated queries")
    fallback = _validate_queries([state.question], max_words=6, max_chars=70)
    return fallback or ["research topic overview"]


# Stage 3: Parallel search.

# Search planning helpers.
def _normalize_plan(plan: QueryPlan, query_type: str, cfg: ResearchConfig, domain_perf) -> QueryPlan:
    topic = _DOMAIN_REGISTRY.topic_from_query_type(query_type)
    default_domains = _DOMAIN_REGISTRY.rank_domains_for_topic(
        topic=topic,
        limit=max(1, int(getattr(cfg, "direct_domain_max_per_query", DIRECT_DOMAIN_MAX_PER_QUERY))),
        domain_performance=domain_perf,
    )
    validated = _validate_queries([plan.query])
    return QueryPlan(
        query=validated[0] if validated else "",
        target_domains=_unique_domains(
            plan.target_domains or default_domains,
            max(1, int(getattr(cfg, "direct_domain_max_per_query", DIRECT_DOMAIN_MAX_PER_QUERY))),
        ),
        method_hint=_normalize_method_hint(plan.method_hint),
    )


# Search planning helpers.
def _plans_from_input(state: ResearchState, queries: List) -> List[QueryPlan]:
    cfg = state.config
    domain_perf = get_domain_performance(getattr(cfg, "domain_perf_db", None))
    if not queries:
        return []

    raw_plans: List[QueryPlan] = []
    for item in queries:
        if isinstance(item, QueryPlan):
            raw_plans.append(item)
        elif isinstance(item, str):
            raw_plans.append(QueryPlan(query=item, target_domains=[], method_hint="auto"))
        elif isinstance(item, dict):
            raw_plans.append(
                QueryPlan(
                    query=str(item.get("query", "")),
                    target_domains=item.get("target_domains") if isinstance(item.get("target_domains"), list) else [],
                    method_hint=str(item.get("method_hint", "auto")),
                )
            )

    normalized: List[QueryPlan] = []
    for plan in raw_plans:
        p = _normalize_plan(plan, state.query_type, cfg, domain_perf)
        if p.query:
            normalized.append(p)

    deduped: List[QueryPlan] = []
    seen = set()
    for p in normalized:
        key = p.query.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(p)
    return deduped


# Direct routing helpers.
def _heuristic_domain_urls(domain: str, query: str) -> List[SearchResult]:
    encoded = quote_plus(query)
    base = f"https://{domain}"
    candidates = [
        f"{base}/search?q={encoded}",
        f"{base}/?q={encoded}",
    ]
    return [
        SearchResult(
            url=url,
            title=f"{domain} search results",
            snippet="",
            engine=f"direct:{domain}:heuristic",
        )
        for url in candidates
    ]


# Direct routing helpers.
def _overlay_domain_urls(domain: str) -> List[SearchResult]:
    strategy = _DOMAIN_REGISTRY.resolve_access_strategy(domain)
    urls: List[str] = []
    if strategy.endpoint_url:
        urls.append(strategy.endpoint_url)
    urls.extend(strategy.seed_urls)
    deduped: List[str] = []
    seen = set()
    for url in urls:
        if not url or url in seen:
            continue
        seen.add(url)
        deduped.append(url)
    results: List[SearchResult] = []
    for url in deduped:
        results.append(
            SearchResult(
                url=url,
                title=f"{domain} machine-readable endpoint",
                snippet="Validated endpoint overlay",
                engine=f"direct:{domain}:endpoint_overlay",
                method_hint=strategy.method,
            )
        )
    return results


# Connector helpers.
async def _connector_arxiv(query: str, session: aiohttp.ClientSession, limit: int) -> List[SearchResult]:
    api = (
        "https://export.arxiv.org/api/query?"
        f"search_query=all:{quote_plus(query)}&start=0&max_results={max(1, limit)}"
    )
    try:
        async with session.get(api, timeout=aiohttp.ClientTimeout(total=12)) as resp:
            if resp.status >= 400:
                return []
            text = await resp.text(errors="ignore")
    except Exception:
        return []

    results: List[SearchResult] = []
    try:
        root = ET.fromstring(text)
        ns = {"a": "http://www.w3.org/2005/Atom"}
        for entry in root.findall("a:entry", ns)[:limit]:
            link = entry.findtext("a:id", default="", namespaces=ns).strip()
            title = " ".join((entry.findtext("a:title", default="", namespaces=ns) or "").split())
            summary = " ".join((entry.findtext("a:summary", default="", namespaces=ns) or "").split())
            if not link:
                continue
            results.append(SearchResult(url=link, title=title or "arXiv paper", snippet=summary, engine="direct:arxiv:api"))
    except Exception:
        return []
    return results


# Connector helpers.
async def _connector_pubmed(query: str, session: aiohttp.ClientSession, limit: int) -> List[SearchResult]:
    api = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        f"?db=pubmed&retmode=json&retmax={max(1, limit)}&term={quote_plus(query)}"
    )
    try:
        async with session.get(api, timeout=aiohttp.ClientTimeout(total=12)) as resp:
            if resp.status >= 400:
                return []
            payload = await resp.json(content_type=None)
    except Exception:
        return []

    ids = (((payload or {}).get("esearchresult") or {}).get("idlist") or [])[:limit]
    results: List[SearchResult] = []
    for pmid in ids:
        pmid_str = str(pmid).strip()
        if not pmid_str:
            continue
        results.append(
            SearchResult(
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid_str}/",
                title=f"PubMed article {pmid_str}",
                snippet=query,
                engine="direct:pubmed:api",
            )
        )
    return results


# Connector helpers.
async def _connector_semanticscholar(query: str, session: aiohttp.ClientSession, limit: int) -> List[SearchResult]:
    api = (
        "https://api.semanticscholar.org/graph/v1/paper/search"
        f"?query={quote_plus(query)}&limit={max(1, limit)}&fields=title,url,abstract"
    )
    try:
        async with session.get(api, timeout=aiohttp.ClientTimeout(total=12)) as resp:
            if resp.status >= 400:
                return []
            payload = await resp.json(content_type=None)
    except Exception:
        return []

    items = (payload or {}).get("data") or []
    results: List[SearchResult] = []
    for item in items[:limit]:
        url = (item or {}).get("url") or ""
        title = (item or {}).get("title") or "Semantic Scholar paper"
        snippet = ((item or {}).get("abstract") or "")[:400]
        if not url:
            continue
        results.append(SearchResult(url=url, title=title, snippet=snippet, engine="direct:semanticscholar:api"))
    return results


# Connector helpers.
async def _connector_wikipedia(query: str, session: aiohttp.ClientSession, limit: int) -> List[SearchResult]:
    api = (
        "https://en.wikipedia.org/w/api.php"
        f"?action=query&list=search&format=json&srlimit={max(1, limit)}&srsearch={quote_plus(query)}"
    )
    try:
        async with session.get(api, timeout=aiohttp.ClientTimeout(total=12)) as resp:
            if resp.status >= 400:
                return []
            payload = await resp.json(content_type=None)
    except Exception:
        return []

    items = ((payload or {}).get("query") or {}).get("search") or []
    results: List[SearchResult] = []
    for item in items[:limit]:
        title = (item or {}).get("title") or ""
        snippet = re.sub(r"<[^>]+>", " ", (item or {}).get("snippet") or "")
        if not title:
            continue
        url = f"https://en.wikipedia.org/wiki/{quote_plus(title.replace(' ', '_'))}"
        results.append(SearchResult(url=url, title=title, snippet=snippet, engine="direct:wikipedia:api"))
    return results


# Connector helpers.
async def _connector_github(query: str, session: aiohttp.ClientSession, limit: int) -> List[SearchResult]:
    api = (
        "https://api.github.com/search/repositories"
        f"?q={quote_plus(query)}&sort=stars&order=desc&per_page={max(1, limit)}"
    )
    headers = {"Accept": "application/vnd.github+json"}
    try:
        async with session.get(api, headers=headers, timeout=aiohttp.ClientTimeout(total=12)) as resp:
            if resp.status >= 400:
                return []
            payload = await resp.json(content_type=None)
    except Exception:
        return []

    items = (payload or {}).get("items") or []
    results: List[SearchResult] = []
    for item in items[:limit]:
        url = (item or {}).get("html_url") or ""
        title = (item or {}).get("full_name") or "GitHub repository"
        snippet = (item or {}).get("description") or ""
        if not url:
            continue
        results.append(SearchResult(url=url, title=title, snippet=snippet, engine="direct:github:api"))
    return results


# Direct routing helpers.
async def _direct_results_for_plan(
    state: ResearchState,
    plan: QueryPlan,
    session: aiohttp.ClientSession,
    limit_per_query: int,
) -> List[SearchResult]:
    if not plan.target_domains:
        return []

    connectors = {
        "arxiv.org": _connector_arxiv,
        "pubmed.ncbi.nlm.nih.gov": _connector_pubmed,
        "ncbi.nlm.nih.gov": _connector_pubmed,
        "semanticscholar.org": _connector_semanticscholar,
        "wikipedia.org": _connector_wikipedia,
        "github.com": _connector_github,
    }

    collected: List[SearchResult] = []
    seen_urls = set()
    for domain in plan.target_domains[:limit_per_query]:
        domain_results: List[SearchResult] = []
        domain_results.extend(_overlay_domain_urls(domain))
        connector = connectors.get(domain)
        if connector is not None:
            domain_results.extend(await connector(plan.query, session, max(2, limit_per_query // 2)))
        elif domain not in _NO_HEURISTIC_DOMAINS:
            domain_results.extend(_heuristic_domain_urls(domain, plan.query))

        for item in domain_results:
            if item.url in seen_urls:
                continue
            if not _is_direct_candidate_relevant(plan.query, item):
                continue
            seen_urls.add(item.url)
            if plan.method_hint and plan.method_hint != "auto":
                item.method_hint = plan.method_hint
            else:
                item.method_hint = _DOMAIN_REGISTRY.choose_method(item.url)
            collected.append(item)
    if collected:
        state.log(f"   direct[{plan.query}] -> {len(collected)} candidates")
    return collected


# Result ranking helpers.
def _result_ranking_score(result: SearchResult, topic: str, domain_perf) -> float:
    domain = normalize_domain(result.url)
    domain_info = _DOMAIN_REGISTRY.lookup(domain)
    learned = domain_perf.get_weighted_score(domain)

    trust_letter_weight = {"A": 0.35, "B": 0.20, "C": 0.05, "?": 0.0}
    tier_weight = {
        "friendly": 0.40,
        "moderate": 0.24,
        "hardened": 0.10,
        "fortress": -0.35,
        "unknown": 0.05,
    }
    topic_bonus = 0.20 if topic in (domain_info.topics or []) else 0.0
    direct_bonus = 0.10 if (result.engine or "").startswith("direct:") else 0.0
    base_score = max(0.0, float(result.score or 0.0)) * 0.05

    return (
        trust_letter_weight.get(result.trust_tier, 0.0)
        + tier_weight.get(domain_info.tier, 0.0)
        + min(0.45, learned * 0.45)
        + topic_bonus
        + direct_bonus
        + base_score
    )


# Search execution stage.
async def search_all(
    state: ResearchState,
    queries: List,
    exclude_urls: set = None,
    ddgs_timelimit: Optional[str] = None,
) -> List[SearchResult]:
    cfg = state.config
    exclude_urls = exclude_urls or set()
    lang = _detect_language(state.question)
    topic = _DOMAIN_REGISTRY.topic_from_query_type(state.query_type)
    domain_perf = get_domain_performance(getattr(cfg, "domain_perf_db", None))
    plans = _plans_from_input(state, queries)
    if not plans:
        return []

    engines = ["DDGS"]
    if cfg.enable_yacy:
        engines.append("YaCy")
    if ddgs_timelimit:
        state.log(f"   DDGS timelimit={ddgs_timelimit}")
    state.log(f"Searching across {len(plans)} queries ({' + '.join(engines)})...")

    seen_urls = set(exclude_urls)
    all_results: List[SearchResult] = []
    direct_total = 0

    # YaCy async search
    try:
        from src.yacy_client import async_yacy_search
        yacy_available = cfg.enable_yacy
    except ImportError:
        yacy_available = False

    fallback_plans: List[QueryPlan] = []
    min_direct_results = max(1, int(getattr(cfg, "direct_domain_min_results", DIRECT_DOMAIN_MIN_RESULTS)))
    max_direct_domains = max(1, int(getattr(cfg, "direct_domain_max_per_query", DIRECT_DOMAIN_MAX_PER_QUERY)))
    fallback_stage_timeout = max(15.0, float(getattr(cfg, "search_fallback_stage_timeout_sec", 120.0)))

    if ddgs_timelimit:
        fallback_plans = list(plans)
    else:
        state.log(f"   direct-domain phase: {len(plans)} plans")
        async with aiohttp.ClientSession(headers=DEFAULT_HTTP_HEADERS) as direct_session:
            for plan in plans:
                direct_results = await _direct_results_for_plan(
                    state=state,
                    plan=plan,
                    session=direct_session,
                    limit_per_query=max_direct_domains,
                )
                kept_for_plan = 0
                strong_hits = 0
                for item in direct_results:
                    if item.url in seen_urls:
                        continue
                    seen_urls.add(item.url)
                    all_results.append(item)
                    direct_total += 1
                    kept_for_plan += 1
                    if "heuristic" not in (item.engine or ""):
                        strong_hits += 1
                if strong_hits < min_direct_results:
                    fallback_plans.append(plan)
        state.log(f"   direct-domain done: {direct_total} URLs, fallback_plans={len(fallback_plans)}")

    if direct_total:
        state.log(f"   direct-domain phase: {direct_total} unique URLs")
    if fallback_plans:
        state.log(f"   fallback search for {len(fallback_plans)} queries")

    # Stage A: domain-scoped fallback (site:domain query) before broad web search.
    domain_scoped_min_results = max(1, int(getattr(cfg, "domain_scoped_min_results", min_direct_results)))
    domain_scoped_max_domains = max(1, int(getattr(cfg, "domain_scoped_max_domains", 4)))
    scoped_hit_counts: Dict[int, int] = {i: 0 for i in range(len(fallback_plans))}
    scoped_tasks = []
    scoped_meta: List[tuple] = []
    for i, plan in enumerate(fallback_plans):
        domains = _unique_domains(plan.target_domains or [], domain_scoped_max_domains)[:domain_scoped_max_domains]
        for domain in domains:
            query_part = _strip_cyrillic(plan.query) or plan.query
            scoped_query = f"site:{domain} {query_part}".strip()
            scoped_tasks.append(
                async_ddgs_search(
                    query=scoped_query,
                    max_results=max(3, cfg.ddgs_results_per_query // 2),
                    query_type=state.query_type,
                    lang=lang,
                    timelimit=ddgs_timelimit,
                )
            )
            scoped_meta.append((i, plan.query, domain, plan.method_hint or "auto"))

    scoped_ddgs_count = 0
    if scoped_tasks:
        state.log(
            f"   domain-scoped fallback start: tasks={len(scoped_tasks)} "
            f"timeout={fallback_stage_timeout:.0f}s"
        )
        # Use as_completed so progress is visible while tasks are still running.
        scoped_results: list = [None] * len(scoped_tasks)
        pending = {
            asyncio.ensure_future(t): idx
            for idx, t in enumerate(scoped_tasks)
        }
        deadline = asyncio.get_event_loop().time() + fallback_stage_timeout
        done_count = 0
        try:
            while pending:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    state.log(
                        f"   domain-scoped fallback timeout after "
                        f"{fallback_stage_timeout:.0f}s ({done_count}/{len(scoped_tasks)} done)"
                    )
                    for fut in pending:
                        fut.cancel()
                    break
                done, _ = await asyncio.wait(
                    pending, timeout=min(remaining, 15.0),
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for fut in done:
                    idx = pending.pop(fut)
                    try:
                        scoped_results[idx] = fut.result()
                    except Exception as exc:
                        scoped_results[idx] = exc
                    done_count += 1
                if done_count % 10 == 0 or done_count == len(scoped_tasks):
                    state.log(
                        f"   domain-scoped DDGS progress: {done_count}/{len(scoped_tasks)}"
                    )
        except asyncio.CancelledError:
            pass

        for task_idx, batch in enumerate(scoped_results):
            if batch is None or isinstance(batch, Exception):
                continue
            plan_idx, plan_query, domain, hint = scoped_meta[task_idx]
            for r in batch:
                if r.url in seen_urls:
                    continue
                if domain not in normalize_domain(r.url):
                    continue
                if not _is_direct_candidate_relevant(plan_query, r):
                    continue
                seen_urls.add(r.url)
                if not r.method_hint:
                    r.method_hint = hint
                all_results.append(r)
                scoped_hit_counts[plan_idx] = scoped_hit_counts.get(plan_idx, 0) + 1
                scoped_ddgs_count += 1
        if scoped_ddgs_count > 0:
            state.log(f"   domain-scoped DDGS: +{scoped_ddgs_count} URLs")

    broad_fallback_plans: List[QueryPlan] = []
    for i, plan in enumerate(fallback_plans):
        if scoped_hit_counts.get(i, 0) < domain_scoped_min_results:
            broad_fallback_plans.append(plan)
    if broad_fallback_plans:
        state.log(f"   broad fallback for {len(broad_fallback_plans)} queries")

    # Stage B: broad DDGS fallback only for plans still under target.
    # YaCy runs for ALL plans regardless - it is an independent index, not a fallback.
    tasks = []
    task_hints: List[str] = []
    for plan in broad_fallback_plans:
        tasks.append(async_ddgs_search(
            query=plan.query,
            max_results=cfg.ddgs_results_per_query,
            query_type=state.query_type,
            lang=lang,
            timelimit=ddgs_timelimit,
        ))
        task_hints.append(plan.method_hint or "auto")
    if yacy_available:
        yacy_plans = list(plans[: max(0, cfg.yacy_max_queries_per_pass)])
        if yacy_plans:
            yacy_limit = max(1, cfg.yacy_concurrency)
            yacy_sem = asyncio.Semaphore(yacy_limit)

            # Run one YaCy query under the shared concurrency gate.
            async def _limited_yacy_search(query: str) -> List[SearchResult]:
                async with yacy_sem:
                    return await async_yacy_search(
                        query=query,
                        max_results=cfg.yacy_results_per_query,
                    )

            state.log(
                f"   YaCy limited: {len(yacy_plans)} queries, "
                f"concurrency={yacy_limit}, results/query={cfg.yacy_results_per_query}"
            )
            for plan in yacy_plans:
                tasks.append(_limited_yacy_search(plan.query))
                task_hints.append(plan.method_hint or "auto")

    if tasks:
        state.log(
            f"   broad fallback start: tasks={len(tasks)} timeout={fallback_stage_timeout:.0f}s"
        )
        results_per_task: list = [None] * len(tasks)
        pending = {
            asyncio.ensure_future(t): idx
            for idx, t in enumerate(tasks)
        }
        deadline = asyncio.get_event_loop().time() + fallback_stage_timeout
        done_count = 0
        try:
            while pending:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    state.log(
                        f"   broad fallback timeout after "
                        f"{fallback_stage_timeout:.0f}s ({done_count}/{len(tasks)} done)"
                    )
                    for fut in pending:
                        fut.cancel()
                    break
                done, _ = await asyncio.wait(
                    pending, timeout=min(remaining, 15.0),
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for fut in done:
                    idx = pending.pop(fut)
                    try:
                        results_per_task[idx] = fut.result()
                    except Exception as exc:
                        results_per_task[idx] = exc
                    done_count += 1
                if done_count % 5 == 0 or done_count == len(tasks):
                    state.log(
                        f"   broad fallback progress: {done_count}/{len(tasks)}"
                    )
        except asyncio.CancelledError:
            pass
    else:
        results_per_task = []

    ddgs_count = scoped_ddgs_count  # domain-scoped DDGS results already collected above
    yacy_count = 0

    for idx, task_results in enumerate(results_per_task):
        method_hint = task_hints[idx] if idx < len(task_hints) else "auto"
        if isinstance(task_results, Exception):
            continue
        for r in task_results:
            if r.url not in seen_urls:
                seen_urls.add(r.url)
                if not r.method_hint:
                    r.method_hint = method_hint
                all_results.append(r)
                if "ddgs" in (r.engine or "").lower():
                    ddgs_count += 1
                elif "yacy" in (r.engine or "").lower():
                    yacy_count += 1

    state.log(
        f"{len(all_results)} unique URLs "
        f"(direct: {direct_total}, DDGS: {ddgs_count}, YaCy: {yacy_count})"
    )

    # Trust Registry
    try:
        from src.trust_registry import get_trust_registry
        registry = get_trust_registry()
        before = len(all_results)
        filtered = []
        for r in all_results:
            if registry.is_blacklisted(r.url):
                continue
            r.trust_tier = registry.get_tier(r.url) or "?"
            filtered.append(r)
        blocked = before - len(filtered)
        if blocked > 0:
            state.log(f"  Trust Registry filtered: -{blocked}")
        all_results = filtered
    except (ImportError, FileNotFoundError):
        pass

    all_results.sort(key=lambda r: _result_ranking_score(r, topic, domain_perf), reverse=True)
    return all_results


# Stage 4: Content extraction.

# Domains that are not worth extracting for research.
METADATA_ONLY_DOMAINS = {
    # Video and social platforms expose metadata only.
    "youtube.com", "youtu.be", "rutube.ru",
    "tiktok.com", "instagram.com", "facebook.com",
    "twitter.com", "x.com",
    "yandex.ru", "ya.ru",
    "pinterest.com", "pinterest.ru",
    "ok.ru",
    # Marketplaces are typically fully protected, even for Playwright.
    "ozon.ru", "ozon.by",
    "wildberries.ru", "wb.ru",
    "dns-shop.ru",
    "aliexpress.ru",
    "temu.com",
    "newegg.com",
    "ebay.com",
    "banggood.com",
}

VIDEO_ONLY_DOMAINS = {
    "youtube.com", "youtu.be", "m.youtube.com",
    "vimeo.com", "player.vimeo.com",
    "dailymotion.com", "dai.ly",
    "rutube.ru",
    "twitch.tv", "clips.twitch.tv",
    "tiktok.com",
    "bilibili.com", "b23.tv",
    "vkvideo.ru",
}

VIDEO_FILE_EXTENSIONS = (
    ".mp4", ".m4v", ".mkv", ".webm", ".mov", ".avi", ".wmv", ".flv",
    ".3gp", ".mpg", ".mpeg", ".ts", ".m3u8", ".mpd", ".ogv", ".f4v",
)

VIDEO_PATH_PATTERNS = [
    re.compile(r"^/video[-_/]", re.IGNORECASE),
    re.compile(r"/video(?:/|$)", re.IGNORECASE),
    re.compile(r"/watch(?:/|$)", re.IGNORECASE),
    re.compile(r"/shorts(?:/|$)", re.IGNORECASE),
    re.compile(r"/reels?(?:/|$)", re.IGNORECASE),
    re.compile(r"/clips?(?:/|$)", re.IGNORECASE),
    re.compile(r"/live(?:/|$)", re.IGNORECASE),
    re.compile(r"/stream(?:/|$)", re.IGNORECASE),
    re.compile(r"/embed(?:/|$)", re.IGNORECASE),
    re.compile(r"/player(?:/|$)", re.IGNORECASE),
]

# Extraction helpers.
def _is_metadata_only(url: str) -> bool:
    from urllib.parse import urlparse
    host = urlparse(url).netloc.lower().removeprefix("www.")
    return any(host == d or host.endswith("." + d) for d in METADATA_ONLY_DOMAINS)


# Extraction helpers.
def _is_video_like_url(url: str) -> bool:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    path = (parsed.path or "").lower()

    if any(host == d or host.endswith("." + d) for d in VIDEO_ONLY_DOMAINS):
        return True

    if any(path.endswith(ext) for ext in VIDEO_FILE_EXTENSIONS):
        return True

    if any(rx.search(path) for rx in VIDEO_PATH_PATTERNS):
        return True

    # Explicitly block VK video URLs while still allowing non-video vk.com pages.
    if host == "vk.com" and (
        path.startswith("/video")
        or "/video" in path
        or path.startswith("/clip")
        or "/clips" in path
    ):
        return True

    return False


DEAD_LINK_MARKERS = (
    "404 not found",
    "page not found",
    "not available",
    "sorry, this page",
    "this page does not exist",
)


# Extraction helpers.
async def _prefilter_dead_results(
    state: ResearchState,
    results: List[SearchResult],
    timeout_sec: float = 6.0,
    concurrency: int = 16,
) -> List[SearchResult]:
    if not results:
        return results

    from urllib.parse import urlparse

    dns_cache: dict = {}
    dns_cache_ttl_sec = 300.0

    sem = asyncio.Semaphore(max(1, concurrency))
    timeout = aiohttp.ClientTimeout(total=max(3.0, timeout_sec))
    connector = aiohttp.TCPConnector(
        limit=max(16, concurrency * 4),
        limit_per_host=max(4, concurrency),
        ttl_dns_cache=120,
    )

    async with aiohttp.ClientSession(
        timeout=timeout,
        connector=connector,
        headers=DEFAULT_HTTP_HEADERS,
    ) as session:
        # Cache DNS lookups during the prefilter pass.
        async def domain_resolves(host: str) -> bool:
            host = (host or "").lower().removeprefix("www.")
            if not host:
                return False

            now = time.monotonic()
            cached = dns_cache.get(host)
            if cached and cached[0] > now:
                return bool(cached[1])

            loop = asyncio.get_running_loop()
            try:
                await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
                ok = True
            except socket.gaierror:
                ok = False
            except Exception:
                ok = True  # Resolver/transient issue: do not hard-drop.

            dns_cache[host] = (now + dns_cache_ttl_sec, ok)
            return ok

        # Detect redirects from a deep URL to the site home page.
        def is_home_redirect(original_url: str, response: aiohttp.ClientResponse) -> bool:
            try:
                original = urlparse(original_url)
                final = urlparse(str(response.url))
                original_host = (original.netloc or "").lower().removeprefix("www.")
                final_host = (final.netloc or "").lower().removeprefix("www.")
                original_path = (original.path or "/").strip() or "/"
                final_path = (final.path or "/").strip() or "/"
                return (
                    bool(response.history)
                    and original_host
                    and original_host == final_host
                    and original_path != "/"
                    and final_path == "/"
                )
            except Exception:
                return False

        # Classify one result as alive, dead, or unknown.
        async def classify_http(result: SearchResult) -> str:
            req_timeout = aiohttp.ClientTimeout(total=max(3.0, timeout_sec))

            # HEAD first: lightweight check on most hosts.
            try:
                async with session.head(
                    result.url,
                    allow_redirects=True,
                    timeout=req_timeout,
                ) as head_resp:
                    if head_resp.status in (404, 410):
                        return "dead"
                    if head_resp.status in (405, 501):
                        # Method not allowed / not implemented -> GET fallback.
                        pass
                    elif head_resp.status >= 500 or head_resp.status in (408, 429):
                        return "unknown"
                    elif 400 <= head_resp.status < 500 and head_resp.status not in (401, 403):
                        return "dead"
                    elif is_home_redirect(result.url, head_resp):
                        return "dead"
                    else:
                        return "ok"
            except (aiohttp.ClientError, asyncio.TimeoutError, UnicodeDecodeError):
                pass

            # GET fallback (read only small response prefix).
            try:
                async with session.get(
                    result.url,
                    allow_redirects=True,
                    timeout=req_timeout,
                ) as get_resp:
                    if get_resp.status in (404, 410):
                        return "dead"
                    if get_resp.status >= 500 or get_resp.status in (408, 429):
                        return "unknown"
                    if 400 <= get_resp.status < 500 and get_resp.status not in (401, 403):
                        return "dead"
                    if is_home_redirect(result.url, get_resp):
                        return "dead"

                    head = await get_resp.content.read(4096)
                    snippet = head.decode("utf-8", errors="ignore").lower()
                    if any(marker in snippet for marker in DEAD_LINK_MARKERS):
                        return "dead"
                    title_match = re.search(
                        r"<title[^>]*>(.*?)</title>",
                        snippet,
                        flags=re.IGNORECASE | re.DOTALL,
                    )
                    if title_match:
                        title = " ".join(title_match.group(1).split())
                        if re.search(
                            r"\b404\b|not\s*found|page\s*(not|cannot)\s*(be\s*)?found|"
                            r"does\s*not\s*exist|no\s*longer\s*(available|exists)",
                            title,
                            flags=re.IGNORECASE,
                        ):
                            return "dead"
                    return "ok"
            except (aiohttp.ClientError, asyncio.TimeoutError, UnicodeDecodeError):
                return "unknown"

        # Classify one result under the shared concurrency gate.
        async def classify(result: SearchResult) -> str:
            async with sem:
                host = urlparse(result.url).netloc.lower().removeprefix("www.")
                if not host:
                    return "dead"
                if not await domain_resolves(host):
                    return "dead"
                try:
                    return await classify_http(result)
                except Exception:
                    return "unknown"

        statuses = await asyncio.gather(*[classify(r) for r in results], return_exceptions=True)

    filtered: List[SearchResult] = []
    dead = 0
    unknown = 0
    for r, st in zip(results, statuses):
        if isinstance(st, Exception):
            unknown += 1
            filtered.append(r)
            continue
        if st == "dead":
            dead += 1
            continue
        if st == "unknown":
            unknown += 1
        filtered.append(r)

    if dead > 0 or unknown > 0:
        state.log(f"  URL precheck: dead={dead}, unknown={unknown}, kept={len(filtered)}")
    return filtered


# Extraction stage.
async def extract_all(
    state: ResearchState,
    results: List[SearchResult],
    existing_hashes: set = None,
) -> List[ExtractedSource]:
    cfg = state.config
    existing_hashes = existing_hashes or set()
    seen_hashes = set(existing_hashes)

    before = len(results)
    results = [r for r in results if not _is_metadata_only(r.url)]
    skipped = before - len(results)
    if skipped:
        state.log(f"  Skipped {skipped} metadata-only sources (YouTube/TikTok/etc)")

    if bool(getattr(cfg, "content_enable_dead_link_precheck", True)):
        precheck_timeout = float(getattr(cfg, "content_precheck_timeout", 6.0))
        precheck_concurrency = int(getattr(cfg, "content_precheck_concurrency", 16))
        results = await _prefilter_dead_results(
            state,
            results,
            timeout_sec=precheck_timeout,
            concurrency=precheck_concurrency,
        )

    # Per-domain URL cap: friendly/known domains get more slots, aggregators fewer.
    from urllib.parse import urlparse
    _AGGREGATOR_DOMAINS = {"reddit.com", "medium.com", "quora.com", "stackexchange.com"}
    _DEFAULT_MAX = int(getattr(cfg, "max_urls_per_domain", 6))
    _AGGREGATOR_MAX = max(2, _DEFAULT_MAX // 3)
    domain_counts: dict = defaultdict(int)
    deduped = []
    for r in results:
        domain = urlparse(r.url).netloc.lower().removeprefix("www.")
        cap = _AGGREGATOR_MAX if domain in _AGGREGATOR_DOMAINS else _DEFAULT_MAX
        if domain_counts[domain] < cap:
            domain_counts[domain] += 1
            deduped.append(r)
    if len(deduped) < len(results):
        state.log(f"  Per-domain cap (default={_DEFAULT_MAX}, aggregators={_AGGREGATOR_MAX}): -{len(results)-len(deduped)}")
    results = deduped

    state.log(f"Extracting content from {len(results)} URLs...")

    extracted_count = 0
    failed_count = 0
    total = len(results)
    configured_fetch_concurrency = int(getattr(cfg, "content_fetch_concurrency", 0))
    auto_cap = max(1, int(getattr(cfg, "content_fetch_auto_cap", 24)))
    fetch_concurrency = (
        min(len(results), auto_cap) if configured_fetch_concurrency <= 0 else configured_fetch_concurrency
    )
    fetch_concurrency = max(1, fetch_concurrency)
    fetch_timeout = float(getattr(cfg, "content_request_timeout", 15.0))
    extract_timeout = float(getattr(cfg, "content_extract_timeout", max(45.0, fetch_timeout * 2.5)))
    state.log(
        f"  Async fetch: concurrency={fetch_concurrency}, timeout={fetch_timeout:.1f}s, "
        f"extract_timeout={extract_timeout:.1f}s (auto_cap={auto_cap})"
    )

    # Mark overlay failures after extraction misses.
    def _mark_overlay_failure(result_url: str, fetch_url: str) -> None:
        strategy = _DOMAIN_REGISTRY.resolve_access_strategy(result_url)
        if strategy.source != "overlay":
            return
        if not (strategy.rewritten_url or fetch_url == strategy.endpoint_url):
            return
        endpoint_type = "xml_feed"
        if strategy.transform_kind:
            endpoint_type = "prefix_transform"
        elif strategy.method == "json_api":
            endpoint_type = "json_endpoint"
        elif "sitemap" in (strategy.endpoint_url or "").lower():
            endpoint_type = "sitemap"
        elif (strategy.endpoint_url or "").lower().endswith("atom.xml"):
            endpoint_type = "atom"
        elif any(token in (strategy.endpoint_url or "").lower() for token in ("/feed", "/rss", "rss.xml", "feed.xml")):
            endpoint_type = "rss"
        candidate = ProbeCandidate(
            domain=strategy.domain or normalize_domain(result_url),
            endpoint_url=strategy.endpoint_url,
            endpoint_type=endpoint_type,
            scope=strategy.scope or "domain",
            path_pattern=strategy.path_pattern or "",
            transform_kind=strategy.transform_kind or "",
        )
        before = _ENDPOINT_OVERLAY.get_entry(candidate) or {}
        _ENDPOINT_OVERLAY.mark_endpoint_failure(strategy.domain or result_url, strategy.endpoint_url)
        after = _ENDPOINT_OVERLAY.get_entry(candidate) or {}
        if before.get("status") != "inactive" and after.get("status") == "inactive":
            state.log(f"endpoint_probe_deactivated: {strategy.domain} -> {strategy.endpoint_url}")

    # Extract one result into a normalized source.
    async def extract_single(
        result: SearchResult,
        session: aiohttp.ClientSession,
    ) -> Optional[ExtractedSource]:
        nonlocal extracted_count, failed_count
        short_url = result.url[:60] + "..." if len(result.url) > 60 else result.url
        try:
            # state.log(f"  In progress: {short_url}")  # Uncomment to log task start.
            strategy = _DOMAIN_REGISTRY.resolve_access_strategy(result.url)
            method_hint = result.method_hint or strategy.method
            fetch_url = strategy.rewritten_url or result.url
            result.extract_debug_stage = "prepare"
            result.extract_debug_timeout_sec = 0.0

            # Track the current extraction stage for timeout diagnostics.
            def _update_extract_stage(stage: str, timeout_sec: float) -> None:
                result.extract_debug_stage = stage
                result.extract_debug_timeout_sec = float(timeout_sec or 0.0)

            data = await extract_content(
                url=fetch_url,
                min_length=cfg.min_content_length,
                use_playwright=cfg.enable_playwright,
                use_seleniumbase=getattr(cfg, "enable_seleniumbase", False),
                enable_nodriver=getattr(cfg, "stealth_enable_nodriver", False),
                enable_camoufox=getattr(cfg, "stealth_enable_camoufox", True),
                session=session,
                request_timeout=fetch_timeout,
                method_hint=method_hint,
                # Priority for http_stage_timeout:
                #   1. Heuristic search URLs (fake /?q=) always uses 4s fast-fail.
                #   2. Per-domain measured latency from domain_registry (response_time_ms * 1.3 + 1s buffer).
                #   3. Global config default (content_http_stage_timeout, typically 12s).
                http_stage_timeout=(
                    4.0
                    if "heuristic" in (result.engine or "")
                    else (
                        round(strategy.response_time_ms / 1000 * 1.3 + 1.0, 1)
                        if getattr(strategy, "response_time_ms", None)
                        else float(getattr(cfg, "content_http_stage_timeout", min(fetch_timeout, 12.0)))
                    )
                ),
                stealth_stage_timeout=float(getattr(cfg, "content_stealth_stage_timeout", max(fetch_timeout, 18.0))),
                browser_stage_timeout=float(getattr(cfg, "content_browser_stage_timeout", max(fetch_timeout + 5.0, 20.0))),
                selenium_stage_timeout=float(getattr(cfg, "content_selenium_stage_timeout", max(fetch_timeout + 10.0, 25.0))),
                progress_callback=_update_extract_stage,
            )
            if not data:
                failed_count += 1
                _mark_overlay_failure(result.url, fetch_url)
                debug_stage = result.extract_debug_stage or "unknown"
                debug_timeout = result.extract_debug_timeout_sec
                debug_suffix = f" ({debug_stage}"
                if debug_timeout > 0:
                    debug_suffix += f", {debug_timeout:.0f}s"
                debug_suffix += ")"
                state.log(f"  FAILED [{extracted_count+failed_count}/{total}] Failed{debug_suffix}: {short_url}")
                return None
            if data["content_hash"] in seen_hashes:
                failed_count += 1
                state.log(f"  DUPLICATE [{extracted_count+failed_count}/{total}] Duplicate: {short_url}")
                return None
                
            seen_hashes.add(data["content_hash"])
            extracted_count += 1
            state.log(f"  OK [{extracted_count+failed_count}/{total}] Downloaded: {short_url}")
            
            # ---------------------------------------------------------
            # Hybrid mode: feed high-quality found pages into local YaCy.
            # ---------------------------------------------------------
            if cfg.enable_yacy:
                try:
                    from src.yacy_client import async_add_to_yacy_index
                    await async_add_to_yacy_index(result.url)
                except Exception:
                    pass
            
            return ExtractedSource(
                url=result.url,
                title=data.get("title") or result.title,
                text=data["text"],
                char_count=data["char_count"],
                extraction_method=data["method"],
                content_hash=data["content_hash"],
            )
        except Exception as e:
            failed_count += 1
            _mark_overlay_failure(result.url, strategy.rewritten_url or result.url)
            debug_stage = getattr(result, "extract_debug_stage", "") or "unknown"
            state.log(f"  WARN [{extracted_count+failed_count}/{total}] Error ({debug_stage}): {short_url}")
            return None

    sem = asyncio.Semaphore(fetch_concurrency)
    timeout = aiohttp.ClientTimeout(total=max(20.0, fetch_timeout + 5.0))
    connector = aiohttp.TCPConnector(
        limit=max(16, fetch_concurrency * 4),
        limit_per_host=max(4, fetch_concurrency),
        ttl_dns_cache=300,
    )

    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        # Run one extraction under the shared semaphore and timeout.
        async def limited(r: SearchResult):
            nonlocal failed_count, extracted_count
            async with sem:
                short_url = r.url[:60] + "..." if len(r.url) > 60 else r.url
                try:
                    return await asyncio.wait_for(extract_single(r, session), timeout=extract_timeout)
                except asyncio.TimeoutError:
                    failed_count += 1
                    strategy = _DOMAIN_REGISTRY.resolve_access_strategy(r.url)
                    _mark_overlay_failure(r.url, strategy.rewritten_url or r.url)
                    debug_stage = getattr(r, "extract_debug_stage", "") or "unknown"
                    debug_timeout = float(getattr(r, "extract_debug_timeout_sec", 0.0) or 0.0)
                    debug_suffix = f" ({debug_stage}"
                    if debug_timeout > 0:
                        debug_suffix += f", {debug_timeout:.0f}s stage"
                    debug_suffix += ")"
                    state.log(f"  TIMEOUT [{extracted_count+failed_count}/{total}] Extraction timeout{debug_suffix}: {short_url}")
                    return None

        raw = await asyncio.gather(*[limited(r) for r in results])
    sources = [s for s in raw if s is not None]
    method_stats: dict = defaultdict(int)
    for s in sources:
        method_stats[(s.extraction_method or "unknown")] += 1
    if method_stats:
        details = ", ".join(
            f"{name}={count}" for name, count in sorted(method_stats.items(), key=lambda kv: (-kv[1], kv[0]))
        )
        state.log(f"  Methods: {details}")
    state.log(f"Final extraction count: {len(sources)} of {total}")
    return sources


# Stage 5: Semantic filtering.

# Filtering stage.
async def filter_and_rank(
    state: ResearchState,
    sources: List[ExtractedSource],
) -> List[ExtractedSource]:
    cfg = state.config

    # 5a. GLiNER
    if cfg.enable_gliner:
        state.log("GLiNER...")
        try:
            from src.gliner_wrapper import (
                extract_entities, get_labels_for_query,
                detect_language_and_adjust_threshold,
            )
            labels = get_labels_for_query(state.question, state.query_type)
            filtered = []
            for source in sources:
                threshold = detect_language_and_adjust_threshold(source.text)
                entities = extract_entities(source.text[:3000], labels, threshold=threshold)
                if len(entities) >= cfg.gliner_min_entities:
                    source.entities = entities
                    filtered.append(source)
            rej = len(sources) - len(filtered)
            if rej > 0:
                state.log(f"  GLiNER filtered: -{rej}")
            sources = filtered
        except ImportError:
            state.log("  GLiNER unavailable")

    # 5b. Source-level + chunk-level
    state.log("Semantic filter...")

    # Run semantic scoring in the executor.
    def _run_semantic_sync(sources_texts):
        """Synchronous section executed in the executor to avoid blocking the event loop."""
        import math
        from src.semantic import compute_source_relevance, extract_relevant_content
        semantic_input_char_limit = int(getattr(cfg, "semantic_input_char_limit", 12000))
        results = []
        for text, title in sources_texts:
            semantic_text = text[:semantic_input_char_limit] if semantic_input_char_limit > 0 else text
            try:
                rel = compute_source_relevance(semantic_text, state.question)
            except Exception as e:
                rel = 0.5
                state.log(f"  WARN Semantic error: {type(e).__name__}: {e}")
            if not math.isfinite(rel):
                state.log(f"  WARN Semantic non-finite relevance -> fallback 0.0 ({title[:60]})")
                rel = 0.0
            try:
                chunk, _ = extract_relevant_content(
                    text=semantic_text, query=state.question,
                    max_chars=cfg.max_chars_per_source,
                    top_k=cfg.semantic_top_k, min_score=cfg.semantic_min_score,
                )
            except Exception as e:
                chunk = text[:cfg.max_chars_per_source]
                state.log(f"  WARN Semantic chunk error: {type(e).__name__}: {e}")
            results.append((rel, chunk))
        return results

    try:
        try:
            from src.semantic import prepare_embedding_vram

            has_headroom, free_gb = prepare_embedding_vram(1.0)
            if free_gb > 0:
                state.log(f"  VRAM before embeddings: {free_gb:.2f} GB free")
            if free_gb > 0 and not has_headroom:
                state.log("  Low VRAM: fallback chain CUDA -> offload -> CPU is enabled")
        except Exception:
            pass

        loop = asyncio.get_running_loop()
        timeout_stage = "init"
        semantic_init_timeout = float(getattr(cfg, "semantic_model_init_timeout", 0.0))
        semantic_filter_timeout = float(getattr(cfg, "semantic_filter_timeout", 180.0))

        # Initialize the semantic model inside the executor.
        def _ensure_semantic_ready_sync():
            from src.semantic import ensure_embedder_ready
            return ensure_embedder_ready()

        # Keep model load timeout separate from semantic scoring timeout.
        if semantic_init_timeout > 0:
            state.log(f"  Semantic model init (timeout={semantic_init_timeout:.0f}s)...")
            await asyncio.wait_for(
                loop.run_in_executor(None, _ensure_semantic_ready_sync),
                timeout=semantic_init_timeout,
            )
        else:
            state.log("  Semantic model init (no timeout)...")
            await loop.run_in_executor(None, _ensure_semantic_ready_sync)

        timeout_stage = "scoring"
        inputs = [(s.text, s.title) for s in sources]
        sem_results = await asyncio.wait_for(
            loop.run_in_executor(None, _run_semantic_sync, inputs),
            timeout=semantic_filter_timeout,
        )
        drop_bottom_fraction = float(getattr(cfg, "semantic_drop_bottom_fraction", 0.30))
        drop_bottom_fraction = min(0.95, max(0.0, drop_bottom_fraction))
        scored = []
        for source, (rel, chunk) in zip(sources, sem_results):
            source._relevance = rel
            source.relevant_chunks = chunk
            scored.append(source)

        if scored and drop_bottom_fraction > 0:
            sorted_scores = sorted(getattr(s, "_relevance", 0.0) for s in scored)
            cut_idx = int(len(sorted_scores) * drop_bottom_fraction)
            if cut_idx >= len(sorted_scores):
                cut_idx = len(sorted_scores) - 1
            cut_idx = max(0, cut_idx)
            rel_threshold = sorted_scores[cut_idx]
            kept = [s for s in scored if getattr(s, "_relevance", 0.0) >= rel_threshold]
            dropped = len(scored) - len(kept)
            state.log(
                f"  Source-level quantile drop={drop_bottom_fraction:.2f} "
                f"threshold={rel_threshold:.3f} dropped={dropped}"
            )
            sources = kept
        else:
            sources = scored

        sources.sort(key=lambda s: getattr(s, '_relevance', 0), reverse=True)
        state.log(f"After filtering: {len(sources)}")

    except asyncio.TimeoutError:
        if 'timeout_stage' in locals() and timeout_stage == "init":
            state.log(
                f"Semantic model init timeout ({semantic_init_timeout:.0f}s) - skip semantic filter, use full text"
            )
        else:
            state.log(
                f"Semantic filter timeout ({semantic_filter_timeout:.0f}s) - use full text"
            )
        for source in sources:
            source._relevance = 0.0
            source.relevant_chunks = source.text[:cfg.max_chars_per_source]
    except (ImportError, Exception) as e:
        state.log(f"  WARN Semantic filter unavailable / error: {e}")
        for source in sources:
            source._relevance = 0.0
            source.relevant_chunks = source.text[:cfg.max_chars_per_source]

    return sources


# Stage 6: Per-source summarization.

# Summary helpers.
def _compact_text(text: str) -> str:
    return " ".join((text or "").replace("\r", " ").replace("\n", " ").split()).strip()


# Summary helpers.
def _source_evidence_brief(source: ExtractedSource, max_chars: int = 500) -> str:
    summary = _compact_text(source.summary or "")
    if summary and not summary.lower().startswith("failed"):
        return summary[:max_chars]

    evidence = _compact_text(source.relevant_chunks or source.text or "")
    return evidence[:max_chars]


# Summary helpers.
def _populate_deterministic_briefs(
    sources: List[ExtractedSource],
    max_chars: int = 500,
) -> List[ExtractedSource]:
    for source in sources:
        source.summary = _source_evidence_brief(source, max_chars=max_chars)
    return sources


def _merge_unique_sources(
    sources: List[ExtractedSource],
    additions: List[ExtractedSource],
) -> List[ExtractedSource]:
    merged = list(sources)
    seen_keys = {
        (
            source.url,
            source.content_hash or hashlib.md5((source.text or "").encode("utf-8", "ignore")).hexdigest(),
        )
        for source in merged
    }
    for source in additions:
        source_key = (
            source.url,
            source.content_hash or hashlib.md5((source.text or "").encode("utf-8", "ignore")).hexdigest(),
        )
        if source_key in seen_keys:
            continue
        seen_keys.add(source_key)
        merged.append(source)
    return merged


def _build_reflection_context(
    state: ResearchState,
    *,
    prompt_char_budget: int,
    snippet_char_limit: int = 220,
) -> tuple[str, dict[str, int]]:
    budget = max(4000, int(prompt_char_budget))
    blocks: list[str] = []
    used_chars = 0
    extracted_added = 0
    snippet_added = 0
    budget_reached = 0

    def _try_add(block: str) -> bool:
        nonlocal used_chars, budget_reached
        if not block:
            return False
        remaining = budget - used_chars
        if remaining <= 0:
            budget_reached = 1
            return False
        if len(block) <= remaining:
            blocks.append(block)
            used_chars += len(block)
            return True
        if not blocks:
            truncated = block[:remaining].rstrip() + "\n"
            blocks.append(truncated)
            used_chars += len(truncated)
        budget_reached = 1
        return False

    extracted_blocks: list[str] = []
    snippet_blocks: list[str] = []
    previous_iteration_sources = list(state.last_iteration_sources)

    for i, source in enumerate(previous_iteration_sources, 1):
        content = sanitize_content(source.text or source.relevant_chunks or source.summary or "")
        if not content.strip():
            continue
        extracted_blocks.append(
            f"\n[EXTRACTED {i}]\n"
            f"Title: {source.title}\n"
            f"URL: {source.url}\n"
            f"Content:\n{content}\n"
        )

    seen_snippet_urls: set[str] = set()
    snippet_index = 1
    for result in state.raw_results:
        if result.url in seen_snippet_urls:
            continue
        seen_snippet_urls.add(result.url)
        snippet = _compact_text(result.snippet or "")[:max(120, snippet_char_limit)]
        if not snippet:
            continue
        snippet_blocks.append(
            f"\n[SEARCH {snippet_index}]\n"
            f"Title: {result.title}\n"
            f"URL: {result.url}\n"
            f"Snippet: {snippet}\n"
        )
        snippet_index += 1

    for source in state.extracted_sources:
        if source.url in seen_snippet_urls:
            continue
        seen_snippet_urls.add(source.url)
        snippet = _compact_text(
            source.summary or source.relevant_chunks or source.text or ""
        )[:max(120, snippet_char_limit)]
        if not snippet:
            continue
        snippet_blocks.append(
            f"\n[SEARCH {snippet_index}]\n"
            f"Title: {source.title}\n"
            f"URL: {source.url}\n"
            f"Snippet: {snippet}\n"
        )
        snippet_index += 1

    if extracted_blocks:
        if _try_add("\n=== PREVIOUS ITERATION FULL CONTENT ===\n"):
            pass
        for block in extracted_blocks:
            if _try_add(block):
                extracted_added += 1
            else:
                break

    if snippet_blocks and used_chars < budget:
        _try_add("\n=== DISCOVERED SOURCES (SNIPPETS ONLY) ===\n")
        for block in snippet_blocks:
            if _try_add(block):
                snippet_added += 1
            else:
                break

    return "".join(blocks), {
        "extracted_added": extracted_added,
        "snippet_added": snippet_added,
        "used_chars": used_chars,
        "budget_chars": budget,
        "budget_reached": budget_reached,
    }

# Summary stage.
async def summarize_sources(
    state: ResearchState,
    sources: List[ExtractedSource],
) -> List[ExtractedSource]:
    cfg = state.config
    if not bool(getattr(cfg, "enable_source_summaries", False)):
        state.log(f"Source summaries disabled; using evidence briefs for {len(sources)} sources")
        return _populate_deterministic_briefs(sources)

    state.log(f"Summarizing {len(sources)} sources (sequential mode)...")

    try:
        from src.semantic import park_embedder_on_cpu

        if park_embedder_on_cpu():
            state.log("  VRAM: semantic embedder moved to CPU before LLM calls")
    except Exception:
        pass

    # Summarize one extracted source.
    async def summarize_one(i: int, source: ExtractedSource) -> ExtractedSource:
        content = source.relevant_chunks or source.text[:cfg.max_chars_per_source]
        content = sanitize_content(content)

        relevance_info = ""
        if hasattr(source, "_relevance"):
            relevance_info = f"\n(Source relevance score: {source._relevance:.3f})"

        is_technical = state.query_type in ("technical", "academic")
        code_instruction = """
STEP 1 - CODE/CONFIGS FIRST: If the source contains ANY configuration examples, commands, code snippets, or config files - copy them VERBATIM and IN FULL inside code blocks. Do this BEFORE writing any text. This is MANDATORY.
STEP 2 - FACTS: After the code blocks, write key technical facts, specific values, version numbers relevant to the question.
STEP 3 - GAPS: Note what the source does NOT cover that the question asks about.""" if is_technical else """
Write key facts and findings relevant to the question. Note gaps."""

        prompt = f"""{SAFETY_PREFIX}

Extract technical information from this source for the research question: \"{state.question}\"
{relevance_info}

Source [{i}]: {source.url}
Content:
---
{content}
---

If and ONLY if the source contains absolutely NO useful technical information related to ANY part of the question, respond with ONLY the exact word: REJECT
{code_instruction}
Write in the same language as the research question. Do not start your summary with \"REJECT\" unless that is the entire message."""

        state.log(f"  [llm] [{i}/{len(sources)}] summary: {source.title[:60]}")

        summary = await call_llm(
            prompt=prompt,
            model=cfg.summarize_model,
            temperature=0.2,
            timeout=min(cfg.llm_timeout, 120.0),
        )

        if summary is None:
            state.log(f"  [llm] [{i}/{len(sources)}] timeout/error")
        source.summary = summary or "Failed to summarize"

        rel_str = f" (rel={source._relevance:.2f})" if hasattr(source, "_relevance") else ""
        state.log(f"  [llm] [{i}/{len(sources)}]{rel_str} done: {source.title[:60]}")
        return source

    completed: List[ExtractedSource] = []
    for i, source in enumerate(sources, 1):
        try:
            item = await summarize_one(i, source)
            completed.append(item)
        except Exception as e:
            state.log(f"  [{i}/{len(sources)}] llm failed: {e}")
            source.summary = "Failed to summarize"
            completed.append(source)

    before = len(completed)
    relevant = [s for s in completed if s.summary and not s.summary.strip().upper().startswith("REJECT")]
    dropped = before - len(relevant)
    if dropped > 0:
        state.log(f"  LLM rejected: -{dropped}")
    return relevant


# Stage 7: Reflection.

# Reflection stage.
async def reflect_and_generate_followup(
    state: ResearchState,
    failed_queries: List[str] = None,
) -> List[str]:
    cfg = state.config
    state.log("Reflection...")
    reflection_timeout = max(15.0, float(getattr(cfg, "reflection_timeout_sec", min(cfg.llm_timeout, 120.0))))
    state.log(f"  [llm] reflection timeout={reflection_timeout:.0f}s")
    reflection_context, reflection_meta = _build_reflection_context(
        state,
        prompt_char_budget=int(getattr(cfg, "reflection_prompt_char_budget", 60000)),
    )
    state.log(
        "  Reflection context: "
        f"extracted={reflection_meta['extracted_added']} "
        f"snippets={reflection_meta['snippet_added']} "
        f"chars={reflection_meta['used_chars']}/{reflection_meta['budget_chars']}"
    )
    if reflection_meta.get("budget_reached"):
        state.log("  Reflection context budget reached")

    lang = _detect_language(state.question)
    lang_instruction = """
- CRITICAL: ALL follow-up queries MUST be in English only!
- Queries should be AS SHORT AS POSSIBLE (1-3 words max, preferably single keywords)."""

    failed_block = ""
    if failed_queries:
        failed_block = "\nThese queries returned nothing - DO NOT repeat:\n"
        for q in failed_queries:
            failed_block += f"  - {q}\n"

    prompt = f"""You are a research quality reviewer.

Original question: "{state.question}"

Extracted source contents and unextracted search snippets:
{reflection_context}
{failed_block}
If findings are comprehensive, return empty followup_queries.
Otherwise generate 3-6 follow-up queries.

RULES for queries:
- NO questions, NO sentences
- GOOD: "GLiNER tutorial", "benchmark"
- BAD: "What are the performance metrics of GLiNER?"
{lang_instruction}

Return JSON:
{{
  "gaps": ["gap1", "gap2"],
  "followup_queries": ["query1", "query2"],
  "coverage_assessment": "brief"
}}"""

    result = await call_llm_json(
        prompt=prompt,
        model=cfg.query_model,
        temperature=0.4,
        timeout=reflection_timeout,
    )

    if not isinstance(result, dict):
        state.log("  WARN Failed to parse reflection output, generating fallback follow-up")
        failed_set = {q.strip().lower() for q in (failed_queries or []) if q and q.strip()}
        target_n = max(1, int(getattr(cfg, "followup_queries_per_iteration", 4)))
        subject = ""
        for candidate in (state.search_queries or []):
            cleaned = " ".join((candidate or "").split()).strip()
            if not cleaned:
                continue
            latin_ratio = sum(1 for c in cleaned if "a" <= c.lower() <= "z") / max(1, len(cleaned))
            if latin_ratio >= 0.35:
                subject = " ".join(cleaned.split()[:5]).strip()
                break
        if not subject:
            words = state.question.strip().split()
            subject = " ".join(words[:5]).strip() or state.question.strip()[:60]
        aspects = [
            "comparison",
            "specs",
            "review",
            "alternatives",
            "problems",
            "benchmarks",
            "buy guide",
        ]
        candidates = []
        for aspect in aspects:
            q = f"{subject} {aspect}".strip()
            if q.lower() in failed_set:
                continue
            candidates.append(q)
            if len(candidates) >= target_n:
                break
        fallback = _validate_queries(candidates, max_words=6, max_chars=70)
        if fallback:
            for q in fallback:
                state.log(f"  fallback: {q}")
            return fallback[:target_n]
        return []

    gaps = result.get("gaps", [])
    followup = result.get("followup_queries", [])
    assessment = result.get("coverage_assessment", "N/A")

    state.log(f"  {assessment}")
    if gaps:
        for g in gaps:
            state.log(f"  Gap: {g}")
    if followup:
        for q in followup:
            state.log(f"  Follow-up: {q}")
    else:
        state.log("  Coverage is sufficient")

    # Validate and trim oversized follow-up queries.
    return _validate_queries(followup)


# Stage 9: Final synthesis.

def _source_synthesis_content(source: ExtractedSource, cfg: ResearchConfig) -> str:
    return sanitize_content(source.relevant_chunks or source.text[:cfg.max_chars_per_source] or "")


def _build_synthesis_source_batches(
    state: ResearchState,
    *,
    batch_char_budget: int,
) -> List[List[Dict[str, Any]]]:
    cfg = state.config
    budget = max(12000, int(batch_char_budget))
    batches: List[List[Dict[str, Any]]] = []
    current_batch: List[Dict[str, Any]] = []
    current_chars = 0

    for index, source in enumerate(state.extracted_sources, 1):
        content = _source_synthesis_content(source, cfg)
        if not content.strip():
            continue
        header = (
            f"\n[SOURCE {index}]\n"
            f"Title: {source.title}\n"
            f"URL: {source.url}\n"
            "Content:\n"
        )
        max_content_chars = max(1000, budget - len(header) - 10)
        if len(content) > max_content_chars:
            content = content[:max_content_chars].rstrip()
        block = f"{header}{content}\n"
        if current_batch and current_chars + len(block) > budget:
            batches.append(current_batch)
            current_batch = []
            current_chars = 0
        current_batch.append(
            {
                "index": index,
                "title": source.title,
                "url": source.url,
                "block": block,
            }
        )
        current_chars += len(block)

    if current_batch:
        batches.append(current_batch)
    return batches


def _format_source_range(items: List[Dict[str, Any]]) -> str:
    indices = [int(item["index"]) for item in items]
    if not indices:
        return "none"
    if len(indices) == 1:
        return str(indices[0])
    return f"{indices[0]}-{indices[-1]}"


def _fallback_batch_report(
    state: ResearchState,
    batch: List[Dict[str, Any]],
    batch_index: int,
    total_batches: int,
) -> str:
    findings = []
    for item in batch[:12]:
        source = state.extracted_sources[int(item["index"]) - 1]
        findings.append(
            f"- [{item['index']}] **{item['title']}**: {_source_evidence_brief(source, max_chars=420)}"
        )
    return (
        f"# Batch Report {batch_index}/{total_batches}\n\n"
        f"## Scope\nSources: {_format_source_range(batch)}\n\n"
        "## Key Findings\n"
        + ("\n".join(findings) if findings else "- No findings extracted.")
        + "\n\n## Notes\nGenerated from deterministic fallback because batch synthesis failed.\n"
    )


async def _synthesize_batch_report(
    state: ResearchState,
    batch: List[Dict[str, Any]],
    *,
    batch_index: int,
    total_batches: int,
) -> str:
    cfg = state.config
    sources_block = "".join(item["block"] for item in batch)
    prompt = f"""{SAFETY_PREFIX}

You are an expert research analyst preparing one partial report for a larger hierarchical deep-research run.

Research question: "{state.question}"
Batch: {batch_index}/{total_batches}
Source coverage: {_format_source_range(batch)}

Use ONLY the sources below. Each source is labeled as [SOURCE N].
When citing facts, preserve the original source ids as [N].
Do not write a final polished conclusion for the whole research topic. Focus on dense extraction and organization of this batch's evidence.

Sources:
{sources_block}

=== REQUIRED OUTPUT ===

# Batch Report {batch_index}/{total_batches}

## Batch Scope
Briefly explain what this batch covers.

## Detailed Findings
Capture all concrete facts, dates, numbers, benchmarks, product names, policy details, and technical claims from this batch.

## Contradictions and Open Questions
List uncertainties, disagreements, and missing pieces visible inside this batch.

## Fact Inventory
Use a flat bullet list of compact fact statements with citations.

=== RULES ===
1. Preserve source citations as [N].
2. Prefer high information density over elegance.
3. Use the same language as the research question.
4. Do not invent cross-batch facts.
5. Keep as much useful detail as possible from this batch.

=== BEGIN BATCH REPORT ==="""

    report = await call_llm(
        prompt=prompt,
        model=cfg.synthesis_model,
        temperature=0.2,
        max_tokens=cfg.synthesis_max_tokens,
        timeout=cfg.llm_timeout,
    )
    if report:
        return report
    state.error(f"Synthesis batch {batch_index}/{total_batches} failed, using fallback")
    return _fallback_batch_report(state, batch, batch_index, total_batches)


def _build_merge_groups(
    reports: List[Dict[str, Any]],
    *,
    prompt_char_budget: int,
) -> List[List[Dict[str, Any]]]:
    budget = max(20000, int(prompt_char_budget))
    groups: List[List[Dict[str, Any]]] = []
    current_group: List[Dict[str, Any]] = []
    current_chars = 0

    for report in reports:
        text = sanitize_content(report["text"] or "")
        if not text.strip():
            continue
        header = (
            f"\n[BATCH REPORT {report['batch_index']}]\n"
            f"Coverage: {report['coverage']}\n"
            "Report:\n"
        )
        max_report_chars = max(3000, budget - len(header) - 10)
        if len(text) > max_report_chars:
            text = text[:max_report_chars].rstrip()
        block = f"{header}{text}\n"
        wrapped = dict(report)
        wrapped["block"] = block
        if current_group and current_chars + len(block) > budget:
            groups.append(current_group)
            current_group = []
            current_chars = 0
        current_group.append(wrapped)
        current_chars += len(block)

    if current_group:
        groups.append(current_group)
    return groups


def _fallback_merged_report(
    state: ResearchState,
    reports: List[Dict[str, Any]],
    *,
    level: int,
    group_index: int,
) -> str:
    excerpts = []
    for report in reports:
        text = _compact_text(report["text"] or "")[:1200]
        excerpts.append(f"### Batch {report['batch_index']} ({report['coverage']})\n{text}")
    return (
        f"# Merged Report Level {level} Group {group_index}\n\n"
        "## Combined Batch Notes\n\n"
        + "\n\n".join(excerpts)
    )


async def _merge_batch_reports_hierarchically(
    state: ResearchState,
    leaf_reports: List[Dict[str, Any]],
) -> str:
    cfg = state.config
    prompt_char_budget = max(20000, int(getattr(cfg, "synthesis_prompt_char_budget", 120000)))
    current_reports = list(leaf_reports)
    level = 1

    while len(current_reports) > 1:
        groups = _build_merge_groups(current_reports, prompt_char_budget=prompt_char_budget)
        state.log(
            f"  Synthesis merge level {level}: {len(current_reports)} reports -> {len(groups)} groups"
        )
        next_reports: List[Dict[str, Any]] = []
        for group_index, group in enumerate(groups, 1):
            reports_block = "".join(item["block"] for item in group)
            prompt = f"""{SAFETY_PREFIX}

You are an expert research analyst merging multiple partial reports into a unified research report.

Research question: "{state.question}"
Merge level: {level}
Group: {group_index}/{len(groups)}

The batch reports below already contain citations like [N] that refer to original sources.
Preserve and reuse those source citations.
Deduplicate repeated facts across batches, reconcile contradictions, and keep the report detailed.

Batch reports:
{reports_block}

=== REQUIRED OUTPUT ===

# [Descriptive Title]

## Executive Summary
2-4 paragraphs with concrete facts.

## Main Findings
Organize the strongest themes and evidence.

## Technical and Factual Details
Keep important numbers, dates, and comparisons.

## Contradictions and Information Gaps

## Conclusions

=== RULES ===
1. Preserve original citations [N].
2. Use ONLY information present in the batch reports.
3. Deduplicate aggressively, but do not collapse useful detail.
4. Use the same language as the research question.

=== BEGIN MERGED REPORT ==="""
            merged = await call_llm(
                prompt=prompt,
                model=cfg.synthesis_model,
                temperature=0.2,
                max_tokens=cfg.synthesis_max_tokens,
                timeout=cfg.llm_timeout,
            )
            if not merged:
                state.error(
                    f"Synthesis merge level {level} group {group_index} failed, using fallback"
                )
                merged = _fallback_merged_report(
                    state,
                    group,
                    level=level,
                    group_index=group_index,
                )
            next_reports.append(
                {
                    "batch_index": group_index,
                    "coverage": f"{group[0]['coverage']} -> {group[-1]['coverage']}",
                    "text": merged,
                }
            )
        current_reports = next_reports
        level += 1

    return current_reports[0]["text"] if current_reports else ""


# Synthesis stage.
async def synthesize_final_report(state: ResearchState):
    cfg = state.config
    state.log(f"Synthesizing from {len(state.extracted_sources)} sources...")
    state.synthesis_batch_reports = []

    if not state.extracted_sources:
        state.final_report = (
            f"# Research: {state.question}\n\n"
            "No relevant sources were found."
        )
        return

    source_batches = _build_synthesis_source_batches(
        state,
        batch_char_budget=int(getattr(cfg, "synthesis_batch_char_budget", 60000)),
    )
    if not source_batches:
        state.final_report = (
            f"# Research: {state.question}\n\n"
            "No synthesis-ready source content was available after filtering."
        )
        return

    state.log(
        f"  Hierarchical synthesis: {len(source_batches)} source batches "
        f"(target {int(getattr(cfg, 'synthesis_batch_char_budget', 60000))} chars each)"
    )

    leaf_reports: List[Dict[str, Any]] = []
    for batch_index, batch in enumerate(source_batches, 1):
        state.log(
            f"  Synthesis batch {batch_index}/{len(source_batches)}: "
            f"{len(batch)} sources ({_format_source_range(batch)})"
        )
        report = await _synthesize_batch_report(
            state,
            batch,
            batch_index=batch_index,
            total_batches=len(source_batches),
        )
        state.synthesis_batch_reports.append(report)
        leaf_reports.append(
            {
                "batch_index": batch_index,
                "coverage": _format_source_range(batch),
                "text": report,
            }
        )

    if len(leaf_reports) == 1:
        state.final_report = leaf_reports[0]["text"]
        return

    report = await _merge_batch_reports_hierarchically(state, leaf_reports)
    if report:
        state.final_report = report
        return

    state.error("Hierarchical synthesis failed, using concatenated batch fallback")
    state.final_report = "\n\n".join(
        f"## Batch {i}\n\n{report}" for i, report in enumerate(state.synthesis_batch_reports, 1)
    )


# Artifact saving.

# Artifact helpers.
def save_artifacts(state: ResearchState, task_id: str):
    output_dir = OUTPUT_DIR / task_id
    output_dir.mkdir(parents=True, exist_ok=True)

    # report.md
    sources_footer = "\n\n---\n\n## Sources\n\n"
    for i, s in enumerate(state.extracted_sources, 1):
        sources_footer += f"{i}. [{s.title}]({s.url})\n"
    meta_footer = (
        f"\n\n---\n*{state.elapsed:.1f}s | {state.config.depth} | "
        f"{len(state.extracted_sources)} sources | "
        f"{datetime.now().strftime('%Y-%m-%d %H:%M')}*\n"
    )
    (output_dir / "report.md").write_text(
        state.final_report + sources_footer + meta_footer, encoding="utf-8"
    )

    # sources.md
    lines = [
        f"# Research Sources\n",
        f"**Question:** {state.question}",
        f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**Sources:** {len(state.extracted_sources)}\n",
        "---\n",
    ]
    for i, s in enumerate(state.extracted_sources, 1):
        entities_str = ""
        if s.entities:
            entities_str = ", ".join(f"`{e['text']}` ({e['label']})" for e in s.entities[:10])
        rel = f"{s._relevance:.3f}" if hasattr(s, '_relevance') else "N/A"
        lines.append(f"## [{i}] {s.title}\n")
        lines.append(f"- **URL:** {s.url}")
        lines.append(f"- **Method:** {s.extraction_method}")
        lines.append(f"- **Size:** {s.char_count} characters")
        lines.append(f"- **Relevance:** {rel}")
        lines.append(f"- **Hash:** {s.content_hash}")
        if entities_str:
            lines.append(f"- **Entities:** {entities_str}")
        lines.append(f"\n### Summary\n\n{_source_evidence_brief(s, max_chars=1200)}\n")
        lines.append(f"### Content\n\n```\n{(s.relevant_chunks or s.text[:2000])[:3000]}\n```\n")
        lines.append("---\n")
    (output_dir / "sources.md").write_text("\n".join(lines), encoding="utf-8")

    # execution.log
    log = "\n".join(state.log_lines)
    if state.errors:
        log += "\n\n=== ERRORS ===\n" + "\n".join(state.errors)
    (output_dir / "execution.log").write_text(log, encoding="utf-8")

    # meta.json
    meta = {
        "question": state.question,
        "query_type": state.query_type,
        "depth": state.config.depth,
        "search_queries": state.search_queries,
        "query_plans": [
            {
                "query": p.query,
                "target_domains": p.target_domains,
                "method_hint": p.method_hint,
            }
            for p in getattr(state, "query_plans", [])
        ],
        "total_raw_results": len(state.raw_results),
        "total_extracted": len(state.extracted_sources),
        "elapsed_seconds": round(state.elapsed, 1),
        "timestamp": datetime.now().isoformat(),
        "sources": [
            {
                "url": s.url, "title": s.title, "chars": s.char_count,
                "relevance": round(s._relevance, 3) if hasattr(s, '_relevance') else None,
            }
            for s in state.extracted_sources
        ],
    }
    (output_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    state.log(f"{output_dir}/")


# Main pipeline.

# Pipeline entry points.
async def run_research(
    question: str,
    depth: str = "medium",
    task_id: str = "",
) -> str:
    """Top-level entry point.  Delegates to _first_pass / _iterate / _finalize."""
    config = ResearchConfig.for_depth(depth)
    state = ResearchState(question=question, config=config)

    if not task_id:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        short_q = "".join(
            c if c.isalnum() or c in " _-" else "" for c in question[:40]
        ).strip().replace(" ", "_")
        task_id = f"{ts}_{short_q}"

    output_dir = OUTPUT_DIR / task_id
    output_dir.mkdir(parents=True, exist_ok=True)
    state.log_file = str(output_dir / "execution.log")

    state.log(f"Deep Research v5: '{question}'")
    state.log(
        f"   depth={depth} | max_sources={config.max_sources} "
        f"| iterations={config.max_iterations}"
    )
    state.log(f"   Search: DDGS + {'YaCy' if config.enable_yacy else 'no YaCy'}")
    extract_batch_limit = max(1, int(getattr(config, "max_urls_to_extract_per_pass", 80)))
    state.log(f"   extract_batch_limit={extract_batch_limit} URLs/pass")
    state.log(f"   ID: {task_id}")

    state.query_type = classify_query(question)
    state.log(f"Type: {state.query_type}")

    state.query_plans = await generate_query_plans(state)
    state.search_queries = [p.query for p in state.query_plans]
    if not state.search_queries:
        state.search_queries = await generate_search_queries(state)
        state.query_plans = [
            QueryPlan(query=q, target_domains=[], method_hint="auto")
            for q in state.search_queries
        ]

    probe_scheduler = EndpointProbeScheduler(state)

    all_processed_urls, all_content_hashes = await _first_pass(
        state, probe_scheduler, extract_batch_limit
    )
    swarm_ctx = await start_background_swarm(state, task_id)
    await _iterate(
        state, probe_scheduler, swarm_ctx,
        all_processed_urls, all_content_hashes, extract_batch_limit,
    )
    return await _finalize(state, probe_scheduler, swarm_ctx, all_content_hashes, task_id)


# Phase helpers.

# Pipeline helpers.
async def _first_pass(
    state: ResearchState,
    probe_scheduler: EndpointProbeScheduler,
    extract_batch_limit: int,
) -> tuple[set, set]:
    """Search -> extract -> DDGS month fallback -> filter -> summarize.

    Returns (all_processed_urls, all_content_hashes) for use by _iterate.
    """
    config = state.config

    state.raw_results = await search_all(state, state.query_plans)
    probe_scheduler.enqueue_results(state.raw_results)

    sources = await extract_all(state, state.raw_results[:extract_batch_limit])
    probe_scheduler.enqueue_sources(sources)

    if bool(getattr(config, "ddgs_month_fallback_enabled", True)):
        min_sources = max(1, int(getattr(config, "ddgs_month_fallback_min_sources", 8)))
        if len(sources) < min_sources:
            state.log(
                f"  INFO Too few extracted sources ({len(sources)} < {min_sources}), "
                "running fresh DDGS fallback (timelimit='m')"
            )
            seen_urls = {r.url for r in state.raw_results}
            fresh_results = await search_all(
                state, state.search_queries,
                exclude_urls=seen_urls, ddgs_timelimit="m",
            )
            if fresh_results:
                state.log(f"  INFO Fresh fallback found {len(fresh_results)} extra URLs")
                state.raw_results.extend(fresh_results)
                probe_scheduler.enqueue_results(fresh_results)
                existing_hashes = {s.content_hash for s in sources}
                fresh_sources = await extract_all(
                    state, fresh_results[:extract_batch_limit],
                    existing_hashes=existing_hashes,
                )
                if fresh_sources:
                    state.log(f"  INFO Fresh fallback extracted +{len(fresh_sources)} sources")
                    sources.extend(fresh_sources)
                    probe_scheduler.enqueue_sources(fresh_sources)
            else:
                state.log("  INFO Fresh fallback returned no additional URLs")

    sources = await filter_and_rank(state, sources)
    summaries_enabled = bool(getattr(config, "enable_source_summaries", False))
    max_before_summarize = max(1, int(getattr(config, "max_sources_before_summarize", 35)))
    if summaries_enabled and len(sources) > max_before_summarize:
        sources.sort(key=lambda s: getattr(s, "_relevance", 0), reverse=True)
        dropped = len(sources) - max_before_summarize
        state.log(f"  Pre-LLM cap: keep {max_before_summarize}, drop {dropped}")
        sources = sources[:max_before_summarize]
    if summaries_enabled:
        try:
            from src.semantic import park_embedder_on_cpu
            if park_embedder_on_cpu():
                state.log("  VRAM: embedder parked on CPU before summarize stage")
        except Exception:
            pass

    sources = await summarize_sources(state, sources)
    state.extracted_sources = sources
    state.last_iteration_sources = list(sources)
    state.log(f"First pass complete: {len(state.extracted_sources)} sources")

    all_processed_urls: set = {s.url for s in state.extracted_sources}
    all_processed_urls.update(r.url for r in state.raw_results)
    all_content_hashes: set = {s.content_hash for s in state.extracted_sources}
    return all_processed_urls, all_content_hashes


# Pipeline helpers.
async def _iterate(
    state: ResearchState,
    probe_scheduler: EndpointProbeScheduler,
    swarm_ctx,
    all_processed_urls: set,
    all_content_hashes: set,
    extract_batch_limit: int,
) -> None:
    """Iterative refinement: reflection -> follow-up search -> extract -> filter -> summarize."""
    config = state.config
    summaries_enabled = bool(getattr(config, "enable_source_summaries", False))
    max_before_summarize = max(1, int(getattr(config, "max_sources_before_summarize", 35)))
    consecutive_failures = 0
    failed_queries: List[str] = []

    for iteration in range(config.max_iterations):
        if len(state.extracted_sources) >= config.max_sources:
            state.log(f"Source limit reached ({config.max_sources}), stopping iterations")
            break

        state.log(f"\n{'='*60}")
        state.log(
            f"ITERATION {iteration + 1}/{config.max_iterations} "
            f"| {len(state.extracted_sources)} sources"
        )
        state.log(f"{'='*60}")

        swarm_sources = await drain_background_swarm(
            state=state, swarm_ctx=swarm_ctx,
            iteration=iteration, existing_hashes=all_content_hashes,
        )
        if swarm_sources:
            state.extracted_sources.extend(swarm_sources)
            all_content_hashes.update(s.content_hash for s in swarm_sources)
            state.last_iteration_sources = _merge_unique_sources(
                state.last_iteration_sources,
                swarm_sources,
            )
            state.log(f"  +{len(swarm_sources)} sources from background swarm")
            if len(state.extracted_sources) >= config.max_sources:
                state.log(f"Source limit reached via swarm ({config.max_sources})")
                break

        followup = await reflect_and_generate_followup(state, failed_queries=failed_queries)
        if not followup:
            state.log("Coverage sufficient")
            break

        iteration_search_timeout = max(
            30.0, float(getattr(config, "iteration_search_timeout_sec", 240.0))
        )
        state.log(
            f"  Follow-up search: queries={len(followup)} "
            f"timeout={iteration_search_timeout:.0f}s"
        )
        try:
            new_results = await asyncio.wait_for(
                search_all(state, followup, exclude_urls=all_processed_urls),
                timeout=iteration_search_timeout,
            )
        except asyncio.TimeoutError:
            state.log(f"  Follow-up search timeout after {iteration_search_timeout:.0f}s")
            failed_queries.extend(followup)
            state.last_iteration_sources = []
            consecutive_failures += 1
            if consecutive_failures >= 3:
                state.log("  3 consecutive timeouts, stopping")
                break
            continue

        state.log(f"  Follow-up search done: +{len(new_results)} URLs")
        probe_scheduler.enqueue_results(new_results)
        all_processed_urls.update(r.url for r in new_results)

        if not new_results:
            state.log("  No new results")
            failed_queries.extend(followup)
            state.last_iteration_sources = []
            consecutive_failures += 1
            if consecutive_failures >= 3:
                state.log("  3 empty iterations, stopping")
                break
            continue

        new_sources = await extract_all(
            state, new_results[:extract_batch_limit],
            existing_hashes=all_content_hashes,
        )
        probe_scheduler.enqueue_sources(new_sources)
        if not new_sources:
            failed_queries.extend(followup)
            state.last_iteration_sources = []
            consecutive_failures += 1
            if consecutive_failures >= 3:
                break
            continue

        new_sources = await filter_and_rank(state, new_sources)
        if summaries_enabled and len(new_sources) > max_before_summarize:
            new_sources.sort(key=lambda s: getattr(s, "_relevance", 0), reverse=True)
            dropped = len(new_sources) - max_before_summarize
            state.log(
                f"  Iteration pre-LLM cap: keep {max_before_summarize}, drop {dropped}"
            )
            new_sources = new_sources[:max_before_summarize]
        if summaries_enabled:
            try:
                from src.semantic import park_embedder_on_cpu
                if park_embedder_on_cpu():
                    state.log("  VRAM: embedder parked on CPU before iterative summarize")
            except Exception:
                pass

        new_sources = await summarize_sources(state, new_sources)
        if new_sources:
            consecutive_failures = 0
            state.log(f"  +{len(new_sources)} sources")
            state.extracted_sources.extend(new_sources)
            state.last_iteration_sources = list(new_sources)
            all_content_hashes.update(s.content_hash for s in new_sources)
        else:
            failed_queries.extend(followup)
            state.last_iteration_sources = []
            consecutive_failures += 1
            if consecutive_failures >= 3:
                break


# Pipeline helpers.
async def _finalize(
    state: ResearchState,
    probe_scheduler: EndpointProbeScheduler,
    swarm_ctx,
    all_content_hashes: set,
    task_id: str,
) -> str:
    """Drain final swarm chunks, synthesize report, save artifacts."""
    config = state.config

    if swarm_ctx:
        final_wait_timeout = max(
            0.0, float(getattr(config, "background_swarm_final_wait_timeout_sec", 15.0))
        )
        orchestrator = swarm_ctx.get("orchestrator")
        swarm_task_id = str(swarm_ctx.get("task_id", ""))
        if final_wait_timeout > 0.0 and orchestrator and swarm_task_id:
            status = orchestrator.get_status(swarm_task_id) or {}
            if status.get("status") in {"running", "pending"}:
                state.log(
                    f"  [swarm] final wait up to {final_wait_timeout:.1f}s before synthesis"
                )
                try:
                    await orchestrator.wait_ready(swarm_task_id, timeout=final_wait_timeout)
                except Exception as exc:
                    state.log(f"  [swarm] final wait error: {exc}")

    final_swarm_sources = await drain_background_swarm(
        state=state, swarm_ctx=swarm_ctx,
        iteration=max(0, config.max_iterations),
        existing_hashes=all_content_hashes,
        force=True, allow_restart=False,
    )
    if final_swarm_sources:
        state.extracted_sources.extend(final_swarm_sources)
        all_content_hashes.update(s.content_hash for s in final_swarm_sources)
        state.log(f"  Final swarm import: +{len(final_swarm_sources)}")

    await cleanup_background_swarm(state, swarm_ctx)

    max_for_synthesis = config.max_sources
    if len(state.extracted_sources) > max_for_synthesis:
        state.extracted_sources.sort(key=lambda s: getattr(s, "_relevance", 0), reverse=True)
        dropped = len(state.extracted_sources) - max_for_synthesis
        state.log(f"Trimming to {max_for_synthesis} sources (-{dropped} least relevant)")
        state.extracted_sources = state.extracted_sources[:max_for_synthesis]

    await synthesize_final_report(state)
    await probe_scheduler.finalize()

    state.log(f"\nDone in {state.elapsed:.1f}s | Sources: {len(state.extracted_sources)}")
    save_artifacts(state, task_id)
    return state.final_report


# CLI entry points.

# CLI entry points.
def main():
    import argparse
    parser = argparse.ArgumentParser(description="Deep Research v5 (DDGS + YaCy)")
    parser.add_argument("query", help="Research question")
    parser.add_argument("--depth", default="medium", choices=["low", "medium", "high", "extra"])
    parser.add_argument("--id", default="", help="Task ID")
    parser.add_argument("--no-yacy", action="store_true", help="Disable YaCy backend")
    args = parser.parse_args()

    if args.no_yacy:
        # Patch config to force-disable YaCy
        original = ResearchConfig.for_depth

        # Build a depth preset with YaCy disabled.
        def patched(depth):
            cfg = original(depth)
            cfg.enable_yacy = False
            return cfg
        ResearchConfig.for_depth = classmethod(lambda cls, d: patched(d))

    # Run the pipeline and always close the LLM session.
    async def _run_with_cleanup() -> str:
        try:
            return await run_research(args.query, args.depth, args.id)
        finally:
            await close_llm_session()

    result = asyncio.run(_run_with_cleanup())
    # Report goes to stderr for logging
    print(result, file=sys.stderr)
    # Report file path goes to stdout for the calling process
    output_dir = OUTPUT_DIR / args.id if args.id else None
    if output_dir:
        report_file = output_dir / "report.md"
        if report_file.exists():
            print(f"REPORT_PATH:{report_file}", file=sys.stdout)


if __name__ == "__main__":
    main()
