# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any, Dict, List, Optional

from src.endpoint_overlay import normalize_domain
from src.llm_client import call_llm_json

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


def _normalize_swarm_query(raw: Any) -> str:
    if not isinstance(raw, str):
        return ""
    query = " ".join(raw.strip().split())
    if len(query) > 96:
        query = query[:96].strip()
    return query


def _normalize_swarm_task(
    raw: Any,
    fallback_label: str,
    query_type: str,
) -> Optional[Dict[str, Any]]:
    if isinstance(raw, str):
        query = _normalize_swarm_query(raw)
        if not query:
            return None
        return {
            "label": fallback_label,
            "query": query,
            "target_domains": [],
            "goal": "",
        }

    if not isinstance(raw, dict):
        return None

    query = _normalize_swarm_query(raw.get("query"))
    if not query:
        return None

    label = " ".join(str(raw.get("label") or fallback_label).strip().split())[:64].strip()
    if not label:
        label = fallback_label
    goal = " ".join(str(raw.get("goal") or "").strip().split())[:180].strip()

    target_domains: List[str] = []
    for item in raw.get("target_domains") or []:
        domain = normalize_domain(str(item))
        if not _is_background_seed_allowed(query_type, domain):
            continue
        if domain and domain not in target_domains:
            target_domains.append(domain)
        if len(target_domains) >= 4:
            break

    return {
        "label": label,
        "query": query,
        "target_domains": target_domains,
        "goal": goal,
    }


def _validate_swarm_tasks(
    tasks: List[Any],
    *,
    limit: int,
    query_type: str,
) -> List[Dict[str, Any]]:
    cleaned: List[Dict[str, Any]] = []
    seen_queries: set[str] = set()
    for index, raw in enumerate(tasks, 1):
        task = _normalize_swarm_task(raw, fallback_label=f"Task {index}", query_type=query_type)
        if not task:
            continue
        key = str(task["query"]).lower()
        if key in seen_queries:
            continue
        seen_queries.add(key)
        cleaned.append(task)
        if len(cleaned) >= limit:
            break
    return cleaned


async def _generate_background_swarm_tasks(
    state: Any,
    cfg: Any,
    seed_domains: List[str],
) -> List[Dict[str, Any]]:
    query_limit = max(1, int(getattr(cfg, "background_swarm_query_count", 4)))
    domain_preview = ", ".join(
        normalize_domain(item) for item in seed_domains[:8] if normalize_domain(item)
    )
    prompt = (
        f"Generate EXACTLY {query_limit} focused crawler tasks for a background deep-research agent.\n\n"
        f"Main question:\n\"{state.question}\"\n\n"
        f"Seed domains:\n{domain_preview or '-'}\n\n"
        "Return ONLY valid JSON array. Each item must be an object:\n"
        "{\n"
        '  "label": "short task label",\n'
        '  "query": "focused crawler subquery",\n'
        '  "target_domains": ["example.com", "docs.example.com"],\n'
        '  "goal": "what evidence this crawler task should look for"\n'
        "}\n\n"
        "Rules:\n"
        "- Each task must target a distinct angle that is useful for crawling and evidence gathering\n"
        "- query: 2-8 words, concrete and crawl-friendly\n"
        "- label: 2-6 words\n"
        "- goal: one short sentence\n"
        "- target_domains: 0-3 real domains relevant to that specific task\n"
        "- Use English unless the topic is clearly local-language specific\n"
        "- No site operators, no quotes, no punctuation-heavy text\n"
        "- No duplicate or near-duplicate tasks\n"
    )
    raw = await call_llm_json(prompt=prompt, model=cfg.query_model, temperature=0.3)
    if isinstance(raw, list):
        validated = _validate_swarm_tasks(raw, limit=query_limit, query_type=state.query_type)
        if validated:
            return validated

    fallback_candidates: List[Any] = []
    for plan in getattr(state, "query_plans", []) or []:
        if getattr(plan, "query", None):
            fallback_candidates.append(
                {
                    "label": plan.query[:40],
                    "query": plan.query,
                    "target_domains": list(getattr(plan, "target_domains", []) or []),
                    "goal": "",
                }
            )
    fallback_candidates.extend(getattr(state, "search_queries", []) or [])
    fallback_candidates.append(
        {
            "label": "Background overview",
            "query": state.question,
            "target_domains": [],
            "goal": "Collect broad background evidence.",
        }
    )
    validated = _validate_swarm_tasks(
        fallback_candidates,
        limit=query_limit,
        query_type=state.query_type,
    )
    return validated or [
        {
            "label": "Background overview",
            "query": "background research overview",
            "target_domains": [],
            "goal": "Collect broad background evidence.",
        }
    ]


def _compose_swarm_task_domains(
    base_domains: List[str],
    task_spec: Dict[str, Any],
) -> List[str]:
    preferred = []
    seen = set()
    for domain in task_spec.get("target_domains") or []:
        normalized = normalize_domain(str(domain))
        if normalized and normalized not in seen:
            seen.add(normalized)
            preferred.append(f"https://{normalized}")
    merged: List[str] = []
    for item in preferred + list(base_domains):
        if not item or item in merged:
            continue
        merged.append(item)
    return merged


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
    swarm_tasks = await _generate_background_swarm_tasks(state, cfg, domains)
    current_task = swarm_tasks[0]
    current_query = str(current_task["query"]).strip()
    current_domains = _compose_swarm_task_domains(domains, current_task)

    swarm_id = f"{task_id}_swarm"
    try:
        store = EphemeralStore(
            default_ttl_sec=float(getattr(cfg, "background_swarm_ttl_sec", 1200.0))
        )
        store.start_cleanup_loop(interval_sec=90.0)
        orchestrator = TaskOrchestrator(max_concurrent=1)
        task = ResearchTask(
            task_id=swarm_id,
            query=current_query,
            domains=current_domains,
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
            max_total_chunks=max(
                0, int(getattr(cfg, "background_swarm_max_total_chunks", 1000))
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
            f"task_id={swarm_id} task='{current_task['label']}' query='{current_query}'"
        )
        return {
            "task_id": swarm_id,
            "store": store,
            "orchestrator": orchestrator,
            "task": task,
            "base_domains": domains,
            "tasks": swarm_tasks,
            "task_index": 0,
            "seen_hashes": set(),
            "query_embedding": None,
            "poll_count": 0,
            "run_count": 1,
            "global_chunk_cap_reached": False,
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

    result = orchestrator.get_result(task_id)
    task_obj = swarm_ctx.get("task")
    max_total_chunks = int(getattr(task_obj, "max_total_chunks", 0) or 0)
    if (
        result is not None
        and max_total_chunks > 0
        and int(getattr(result, "chunks_stored", 0) or 0) >= max_total_chunks
    ):
        swarm_ctx["global_chunk_cap_reached"] = True

    # Restart the swarm as soon as it finishes so it keeps collecting
    if allow_restart and status.get("status") in ("done", "failed"):
        if swarm_ctx.get("global_chunk_cap_reached"):
            state.log("  [swarm] auto-restart skipped: global chunk cap reached")
        else:
            task_specs = swarm_ctx.get("tasks") or []
            next_task_index = int(swarm_ctx.get("task_index", 0)) + 1
            if next_task_index >= len(task_specs):
                state.log("  [swarm] auto-restart skipped: no pending swarm tasks")
            elif task_obj is not None:
                next_task = dict(task_specs[next_task_index])
                next_query = str(next_task["query"]).strip()
                swarm_ctx["task_index"] = next_task_index
                task_obj.query = next_query
                base_domains = list(swarm_ctx.get("base_domains") or [])
                refreshed_domains = _collect_background_domains(state, cfg)
                if refreshed_domains:
                    base_domains = refreshed_domains
                    swarm_ctx["base_domains"] = list(refreshed_domains)
                    state.log(f"  [swarm] refreshed seeds: {len(refreshed_domains)}")
                task_obj.domains = _compose_swarm_task_domains(base_domains, next_task)
                swarm_ctx["query_embedding"] = None
                swarm_ctx["seen_hashes"] = set()
                run_num = swarm_ctx.get("run_count", 1) + 1
                swarm_ctx["run_count"] = run_num
                try:
                    await orchestrator.submit(
                        task_obj.run, task_id=task_id, max_retries=1, retry_base_delay=5.0
                    )
                    state.log(
                        f"  [swarm] restarted (run #{run_num}) "
                        f"task='{next_task['label']}' query='{next_query}'"
                    )
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
