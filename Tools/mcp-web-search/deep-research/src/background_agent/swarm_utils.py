# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any, Dict, List, Optional

from src.endpoint_overlay import normalize_domain

try:
    from src.background_agent import EphemeralStore, ResearchTask, TaskOrchestrator
    from src.background_agent.research_task import _encode_query as _bg_encode_query
except Exception:
    EphemeralStore = None  # type: ignore
    ResearchTask = None  # type: ignore
    TaskOrchestrator = None  # type: ignore
    _bg_encode_query = None  # type: ignore

# Domains excluded from background crawl seeds regardless of query type.
_BACKGROUND_SWARM_DOMAIN_BLOCKLIST = {
    "reddit.com",
    "medium.com",
    "wikipedia.org",
    "quora.com",
}


# Validate a normalized domain name.
def _is_probably_valid_domain(domain: str) -> bool:
    import re

    d = normalize_domain(domain)
    if not d or " " in d or "." not in d:
        return False
    if not re.fullmatch(r"[a-z0-9.-]+", d):
        return False
    parts = [part for part in d.split(".") if part]
    if len(parts) < 2:
        return False
    tld = parts[-1]
    return len(tld) >= 2 and tld.isalpha()


# Check whether a seed is allowed for the background swarm.
def _is_background_seed_allowed(query_type: str, value: str) -> bool:
    domain = normalize_domain(value)
    if not _is_probably_valid_domain(domain):
        return False
    if query_type in {"technical", "academic", "medical", "finance"}:
        return domain not in _BACKGROUND_SWARM_DOMAIN_BLOCKLIST
    return True


# Domain seed collection.
def _collect_background_domains(state: Any, cfg: Any) -> List[str]:
    """Build a de-duplicated list of seed URLs for the background swarm.

    Returns a mix of domain roots (``https://domain``) and specific URLs
    discovered in the first-pass search results.
    """
    cap = max(6, int(getattr(cfg, "background_swarm_domains_cap", 32)))
    seed_urls_per_domain = max(
        1, int(getattr(cfg, "background_swarm_seed_urls_per_domain", 4))
    )
    domain_roots: List[str] = []
    specific_urls: List[str] = []
    seen_domains: set = set()
    seen_urls: set = set()
    per_domain_specific: Dict[str, int] = defaultdict(int)

    for plan in getattr(state, "query_plans", []):
        for item in plan.target_domains or []:
            domain = normalize_domain(item)
            if not _is_background_seed_allowed(state.query_type, domain):
                continue
            if not domain or domain in seen_domains:
                continue
            seen_domains.add(domain)
            domain_roots.append(domain)
            if len(domain_roots) >= cap:
                break
        if len(domain_roots) >= cap:
            break

    raw_limit = max(40, cap * seed_urls_per_domain * 4)
    for result in getattr(state, "raw_results", [])[:raw_limit]:
        url = getattr(result, "url", "")
        if not url or url in seen_urls:
            continue
        domain = normalize_domain(url)
        if not _is_background_seed_allowed(state.query_type, domain):
            continue
        if domain not in seen_domains and len(domain_roots) < cap:
            seen_domains.add(domain)
            domain_roots.append(domain)
        if per_domain_specific[domain] >= seed_urls_per_domain:
            continue
        seen_urls.add(url)
        specific_urls.append(url)
        per_domain_specific[domain] += 1

    combined = [f"https://{domain}" for domain in domain_roots]
    combined.extend(specific_urls)
    return combined


# Swarm lifecycle helpers.
async def start_background_swarm(
    state: Any, task_id: str
) -> Optional[Dict[str, Any]]:
    """Spawn a background ResearchTask swarm and return its context dict.

    Returns ``None`` if the swarm is disabled, prerequisites are unavailable,
    or no seed domains were collected.
    """
    cfg = state.config
    if not bool(getattr(cfg, "enable_background_swarm", False)):
        return None
    if not (EphemeralStore and ResearchTask and TaskOrchestrator and _bg_encode_query):
        state.log("  WARN Background swarm requested but background_agent modules unavailable")
        return None

    domains = _collect_background_domains(state, cfg)
    if not domains:
        state.log("  WARN Background swarm skipped: no domains")
        return None

    swarm_id = f"{task_id}_swarm"
    try:
        store = EphemeralStore(
            default_ttl_sec=float(getattr(cfg, "background_swarm_ttl_sec", 1200.0))
        )
        store.start_cleanup_loop(interval_sec=90.0)
        orchestrator = TaskOrchestrator(max_concurrent=1)
        task = ResearchTask(
            task_id=swarm_id,
            query=state.question,
            domains=domains,
            store=store,
            ttl_sec=float(getattr(cfg, "background_swarm_ttl_sec", 1200.0)),
            max_urls_per_domain=max(
                2, int(getattr(cfg, "background_swarm_max_urls_per_domain", 4))
            ),
            max_concurrency=max(
                2, int(getattr(cfg, "background_swarm_max_concurrency", 8))
            ),
            discovery_depth=max(
                2, int(getattr(cfg, "background_swarm_discovery_depth", 3))
            ),
            crawl_timeout=max(
                20.0, float(getattr(cfg, "content_extract_timeout", 45.0))
            ),
            min_chunk_relevance=max(
                0.0, float(getattr(cfg, "background_swarm_min_chunk_relevance", 0.30))
            ),
            use_stealth=bool(getattr(cfg, "enable_stealth", True)),
            use_playwright=bool(getattr(cfg, "enable_playwright", False)),
            progress_callback=lambda m: state.log(f"  [swarm] {m}"),
        )
        await orchestrator.submit(
            task.run, task_id=swarm_id, max_retries=1, retry_base_delay=5.0
        )
        specific_seed_count = sum(
            1
            for item in domains
            if "/" in item.replace("https://", "", 1).replace("http://", "", 1)
        )
        root_seed_count = len(domains) - specific_seed_count
        state.log(
            f"Background swarm started: seeds={len(domains)} "
            f"(roots={root_seed_count}, specific={specific_seed_count}) "
            f"task_id={swarm_id}"
        )
        return {
            "task_id": swarm_id,
            "store": store,
            "orchestrator": orchestrator,
            "task": task,
            "seen_hashes": set(),
            "query_embedding": None,
            "poll_count": 0,
            "run_count": 1,
        }
    except Exception as exc:
        state.log(f"  WARN Background swarm start failed: {exc}")
        return None


# Decide whether the swarm should be drained on this iteration.
def swarm_should_poll(cfg: Any, iteration: int) -> bool:
    """Return True when it is time to drain the swarm on this iteration."""
    min_iter = max(1, int(getattr(cfg, "background_swarm_min_iteration", 2)))
    every = max(1, int(getattr(cfg, "background_swarm_poll_every", 2)))
    current = iteration + 1
    if current < min_iter:
        return False
    return ((current - min_iter) % every) == 0


# Pull newly available sources from the background swarm.
async def drain_background_swarm(
    state: Any,
    swarm_ctx: Optional[Dict[str, Any]],
    iteration: int,
    existing_hashes: set,
    force: bool = False,
    allow_restart: bool = True,
) -> list:
    """Pull newly crawled chunks from the swarm store and return as sources.

    Optionally restarts the swarm when it finishes so crawling continues
    during subsequent iterations.
    """
    from src.models import ExtractedSource

    if not swarm_ctx:
        return []
    cfg = state.config
    if not force and not swarm_should_poll(cfg, iteration):
        return []
    if _bg_encode_query is None:
        return []

    task_id = str(swarm_ctx["task_id"])
    store = swarm_ctx["store"]
    orchestrator = swarm_ctx["orchestrator"]
    swarm_ctx["poll_count"] = int(swarm_ctx.get("poll_count", 0)) + 1
    status = orchestrator.get_status(task_id) or {}
    if status:
        state.log(
            f"  [swarm] status={status.get('status')} progress={status.get('progress')}"
        )

    # Restart the swarm as soon as it finishes so it keeps collecting
    if allow_restart and status.get("status") in ("done", "failed"):
        task_obj = swarm_ctx.get("task")
        if task_obj is not None:
            run_num = swarm_ctx.get("run_count", 1) + 1
            swarm_ctx["run_count"] = run_num
            try:
                refreshed_domains = _collect_background_domains(state, cfg)
                if refreshed_domains:
                    task_obj.domains = refreshed_domains
                    state.log(f"  [swarm] refreshed seeds: {len(refreshed_domains)}")
                await orchestrator.submit(
                    task_obj.run, task_id=task_id, max_retries=1, retry_base_delay=5.0
                )
                state.log(f"  [swarm] restarted (run #{run_num})")
            except Exception as exc:
                state.log(f"  [swarm] restart failed: {exc}")

    query_embedding = swarm_ctx.get("query_embedding")
    if query_embedding is None:
        query_embedding = await _bg_encode_query(state.question)
        swarm_ctx["query_embedding"] = query_embedding
    if query_embedding is None:
        return []

    top_k = max(8, int(getattr(cfg, "background_swarm_top_k", 32)))
    attach_cap = max(2, int(getattr(cfg, "background_swarm_attach_cap_per_poll", 8)))
    max_chars = max(
        900, int(getattr(cfg, "background_swarm_chunk_merge_chars", 2200))
    )

    try:
        swarm_hits = await store.search(task_id, query_embedding, top_k=top_k)
    except Exception as exc:
        state.log(f"  [swarm] search error: {exc}")
        return []
    if not swarm_hits:
        return []

    grouped: Dict[str, list] = defaultdict(list)
    for hit in swarm_hits:
        meta = hit.metadata or {}
        url = str(meta.get("url") or "").strip()
        if not url:
            continue
        grouped[url].append(hit)

    merged_sources: List[ExtractedSource] = []
    seen_hashes = swarm_ctx.setdefault("seen_hashes", set())

    ranked_urls = sorted(
        grouped.keys(),
        key=lambda u: max(float(getattr(h, "score", 0.0)) for h in grouped[u]),
        reverse=True,
    )
    for url in ranked_urls:
        hits = sorted(
            grouped[url],
            key=lambda h: float(getattr(h, "score", 0.0)),
            reverse=True,
        )
        chunks: List[str] = []
        char_count = 0
        for hit in hits:
            chunk = " ".join((hit.chunk or "").split())
            if not chunk or chunk in chunks:
                continue
            if char_count + len(chunk) > max_chars:
                break
            chunks.append(chunk)
            char_count += len(chunk)
        if not chunks:
            continue

        merged_text = "\n\n".join(chunks)
        content_hash = hashlib.sha256(
            f"{url}\n{merged_text}".encode("utf-8", errors="ignore")
        ).hexdigest()[:16]
        if content_hash in existing_hashes or content_hash in seen_hashes:
            continue

        meta0 = hits[0].metadata or {}
        title = str(meta0.get("title") or url)
        method = str(meta0.get("method") or "background_swarm")
        avg_score = sum(
            float(getattr(h, "score", 0.0)) for h in hits[:4]
        ) / max(1, min(4, len(hits)))

        source = ExtractedSource(
            url=url,
            title=title,
            text=merged_text,
            char_count=len(merged_text),
            extraction_method=f"background_swarm/{method}",
            content_hash=content_hash,
            relevant_chunks=merged_text[:1500],
        )
        source._relevance = max(0.0, min(1.0, avg_score))  # type: ignore[attr-defined]
        merged_sources.append(source)
        seen_hashes.add(content_hash)
        if len(merged_sources) >= attach_cap:
            break

    if not merged_sources:
        return []

    state.log(
        f"  [swarm] attached {len(merged_sources)} sources from background context"
    )
    try:
        # Lazy import to avoid circular dependency.
        from scripts.deep_research import summarize_sources

        merged_sources = await summarize_sources(state, merged_sources)
    except Exception as exc:
        state.log(f"  [swarm] summarize error: {exc}")
    return merged_sources


# Stop the swarm and release its resources.
async def cleanup_background_swarm(
    state: Any, swarm_ctx: Optional[Dict[str, Any]]
) -> None:
    """Cancel the swarm task and purge the ephemeral store."""
    if not swarm_ctx:
        return
    try:
        task_id = str(swarm_ctx.get("task_id", ""))
        orchestrator = swarm_ctx.get("orchestrator")
        store = swarm_ctx.get("store")
        if orchestrator and task_id:
            status = orchestrator.get_status(task_id) or {}
            state.log(
                f"  [swarm] final status={status.get('status')} "
                f"elapsed={status.get('elapsed_sec')}"
            )
            if status.get("status") in {"running", "pending"}:
                orchestrator.cancel(task_id)
        if store:
            try:
                await store.purge(task_id)
            except Exception:
                pass
            try:
                store.stop_cleanup_loop()
            except Exception:
                pass
    except Exception as exc:
        state.log(f"  [swarm] cleanup error: {exc}")
