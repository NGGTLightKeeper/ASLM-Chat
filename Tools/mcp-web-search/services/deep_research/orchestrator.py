# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Legacy-style deep research orchestration on top of the new search backend."""

from __future__ import annotations

import asyncio
import math
from typing import Optional

from services.deep_research.config import (
    PHASE_TIMEOUTS,
    TRIAGE_BATCH_BUDGET_SEC,
    TRIAGE_MAX_CONCURRENT_BATCHES,
    ResearchConfig,
)
from services.deep_research.logging_config import get_logger, open_cot_log, start_new_run
from services.deep_research.models import PhaseResult, QueryPlan, ResearchState


def _gap_overlap(gaps_a: list[str], gaps_b: list[str]) -> float:
    """Word-level Jaccard similarity between two gap lists.

    Uses only words of 4+ characters to avoid noise from common short words.
    A value ≥ 0.65 indicates the model is identifying essentially the same
    information gaps as the previous iteration (stagnation signal).
    """
    def _words(gaps: list[str]) -> set[str]:
        return {w.lower() for g in gaps for w in g.split() if len(w) >= 4}

    wa, wb = _words(gaps_a), _words(gaps_b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def _synth_timeout(state: ResearchState, depth: str) -> float:
    key = "synthesize_high" if depth in ("high", "extra") else "synthesize_low"
    static = PHASE_TIMEOUTS.get(key, 320.0)
    remaining = state.config.total_hard_timeout - state.elapsed - 30.0
    return max(static, remaining)


def _semantic_backend_for_timeout(state: ResearchState) -> str:
    cached = getattr(state, "_semantic_backend_for_timeout", "")
    if cached:
        return str(cached)
    try:
        from core.llm.semantic import ensure_embedder_ready, get_embedder_backend
        ensure_embedder_ready(require_cuda=False)
        backend = get_embedder_backend()
    except Exception as exc:
        backend = "unknown"
        state.log(f"  Semantic backend probe failed: {type(exc).__name__}: {exc}")
    setattr(state, "_semantic_backend_for_timeout", backend)
    if backend.startswith("cpu"):
        state.log(
            "  Semantic inference backend is CPU; "
            f"timeout multiplier={float(getattr(state.config, 'inference_cpu_timeout_multiplier', 2.0)):.1f}x"
        )
    elif backend and backend != "unknown":
        state.log(f"  Semantic inference backend: {backend}")
    return backend


def _cpu_scaled_timeout(state: ResearchState, timeout: float) -> float:
    backend = _semantic_backend_for_timeout(state)
    if not backend.startswith("cpu"):
        return timeout
    multiplier = max(1.0, float(getattr(state.config, "inference_cpu_timeout_multiplier", 2.0)))
    return timeout * multiplier


def _dedup_timeout_for(state: ResearchState) -> float:
    return _cpu_scaled_timeout(state, PHASE_TIMEOUTS["dedup_filter"])


def _harvest_timeout_for(state: ResearchState) -> float:
    cfg = state.config
    base = PHASE_TIMEOUTS["harvest"]
    if cfg.depth not in ("high", "extra"):
        return _cpu_scaled_timeout(state, base)
    estimated = (
        math.ceil(cfg.max_urls_to_extract_per_pass / max(1, cfg.content_fetch_concurrency))
        * max(5.0, cfg.content_request_timeout)
        + 60.0
    )
    estimated = _cpu_scaled_timeout(state, estimated)
    cap = 720.0 if _semantic_backend_for_timeout(state).startswith("cpu") else 360.0
    return max(base, min(cap, estimated))


async def _run_phase(
    state: ResearchState,
    phase_results: list[dict],
    phase_name: str,
    coro,
    timeout: float,
) -> Optional[PhaseResult]:
    state.log(f"Phase: {phase_name} (timeout={timeout:.0f}s)")
    try:
        result = await asyncio.wait_for(coro, timeout=timeout)
        phase_results.append(
            {
                "phase": result.phase_name,
                "success": result.success,
                "items": result.items_produced,
                "duration": round(result.duration_sec, 2),
            }
        )
        state.log(f"Phase {phase_name} done: {result.items_produced} items in {result.duration_sec:.1f}s")
        return result
    except asyncio.TimeoutError:
        state.error(f"Phase {phase_name} timed out after {timeout:.0f}s")
        phase_results.append({"phase": phase_name, "success": False, "error": "timeout"})
        return None
    except Exception as exc:
        state.error(f"Phase {phase_name} failed: {type(exc).__name__}: {exc}")
        phase_results.append({"phase": phase_name, "success": False, "error": str(exc)})
        return None


async def _iterate(
    state: ResearchState,
    phase_results: list[dict],
) -> None:
    from services.deep_research.dedup_filter import run_dedup_filter
    from services.deep_research.harvest import harvest_query_plans
    from services.deep_research.reflection import reflect_and_generate_followup

    cfg = state.config
    consecutive_failures = 0
    last_followup_signature: tuple[str, ...] = ()
    repeated_followup_sets = 0
    gap_stagnation_counter = 0
    iteration_start = state.elapsed
    _last_dedup_count: int = len(state.extracted_sources)

    for iteration in range(int(cfg.max_iterations)):
        if len(state.extracted_sources) >= cfg.max_sources:
            state.log(f"Source limit reached ({cfg.max_sources}), stopping iterations")
            break

        state.log("=" * 60)
        state.log(
            f"ITERATION {iteration + 1}/{cfg.max_iterations} | "
            f"{len(state.extracted_sources)} sources"
        )
        state.log("=" * 60)

        gaps_before = len(state.iteration_gaps)
        followup = await reflect_and_generate_followup(
            state,
            failed_queries=state.failed_queries,
            attempted_queries=state.attempted_followups,
        )
        if not followup:
            state.log("Coverage sufficient")
            break

        # ── Gap stagnation check ──────────────────────────────────────────────
        # If the model keeps identifying the same gaps across iterations, it means
        # public data on those topics is likely exhausted or follow-up queries are
        # not reaching new sources.  Two consecutive high-overlap iterations → stop.
        if len(state.iteration_gaps) > gaps_before and len(state.iteration_gaps) >= 2:
            overlap = _gap_overlap(state.iteration_gaps[-1], state.iteration_gaps[-2])
            state.log(f"  Gap overlap with previous iteration: {overlap:.0%}")
            if overlap >= 0.65:
                gap_stagnation_counter += 1
                state.log(f"  Gap stagnation ({gap_stagnation_counter}/2): same gaps, different queries won't help")
                if gap_stagnation_counter >= 2:
                    state.log("  Gaps unchanged for 2 iterations — public data likely exhausted, stopping")
                    break
            else:
                gap_stagnation_counter = 0

        # ── Exact-signature repeat check (existing, kept as backstop) ────────
        followup_signature = tuple(sorted({q.strip().lower() for q in followup if q and q.strip()}))
        if followup_signature == last_followup_signature:
            repeated_followup_sets += 1
            state.log(f"  Repeated follow-up set detected ({repeated_followup_sets})")
            if repeated_followup_sets >= 2:
                state.log("  Same follow-up queries keep repeating, stopping iterations")
                break
        else:
            repeated_followup_sets = 0
            last_followup_signature = followup_signature

        for query in followup:
            cleaned = query.strip()
            if cleaned:
                state.attempted_followups.append(cleaned)

        query_plans = [QueryPlan(query=query) for query in followup if query.strip()]
        iteration_timeout = _cpu_scaled_timeout(state, max(30.0, float(cfg.iteration_search_timeout_sec)))
        state.log(f"  Follow-up search: queries={len(query_plans)} timeout={iteration_timeout:.0f}s")
        try:
            _, new_sources = await asyncio.wait_for(
                harvest_query_plans(
                    state,
                    query_plans,
                    exclude_urls=state.raw_urls,
                    existing_hashes={s.content_hash for s in state.extracted_sources},
                ),
                timeout=iteration_timeout,
            )
        except asyncio.TimeoutError:
            state.log(f"  Follow-up search timeout after {iteration_timeout:.0f}s")
            state.failed_queries.extend(followup)
            state.last_iteration_sources = []
            consecutive_failures += 1
            if consecutive_failures >= 3:
                state.log("  3 consecutive timeouts, stopping")
                break
            continue

        if not new_sources:
            state.log("  No new sources from follow-up")
            state.failed_queries.extend(followup)
            state.last_iteration_sources = []
            consecutive_failures += 1
            if consecutive_failures >= 3:
                state.log("  3 empty iterations, stopping")
                break
            continue

        new_sources.sort(
            key=lambda source: (
                float(getattr(source, "relevance_score", 0.0) or 0.0),
                int(getattr(source, "char_count", 0) or 0),
            ),
            reverse=True,
        )
        max_iter_sources = max(1, int(cfg.max_sources_per_iteration))
        if len(new_sources) > max_iter_sources:
            state.log(f"  Iteration pre-cap: keep {max_iter_sources}, drop {len(new_sources) - max_iter_sources}")
            new_sources = new_sources[:max_iter_sources]

        new_sources_added = len(new_sources)
        state.extracted_sources.extend(new_sources)

        _current_count = len(state.extracted_sources)
        _grew = (_current_count - _last_dedup_count) / max(1, _last_dedup_count)
        if _grew >= cfg.dedup_cooldown_ratio or new_sources_added >= cfg.dedup_min_new_sources or _last_dedup_count == 0:
            await _run_phase(
                state,
                phase_results,
                "dedup_filter_iteration",
                run_dedup_filter(state),
                _dedup_timeout_for(state),
            )
            _last_dedup_count = len(state.extracted_sources)
        else:
            state.log(
                f"  Dedup skipped: pool grew {_grew:.0%} < {cfg.dedup_cooldown_ratio:.0%}, "
                f"added {new_sources_added} < {cfg.dedup_min_new_sources} threshold"
            )

        retained_hashes = {source.content_hash for source in state.extracted_sources}
        state.last_iteration_sources = [
            source for source in new_sources if source.content_hash in retained_hashes
        ]
        if state.last_iteration_sources:
            consecutive_failures = 0
            state.log(f"  +{len(state.last_iteration_sources)} retained sources")
        else:
            state.failed_queries.extend(followup)
            consecutive_failures += 1
            if consecutive_failures >= 3:
                state.log("  3 failed iterations after dedup, stopping")
                break

    phase_results.append(
        {
            "phase": "iterate",
            "success": True,
            "items": len(state.extracted_sources),
            "duration": round(state.elapsed - iteration_start, 2),
        }
    )


async def orchestrate(
    question: str,
    depth: str = "medium",
) -> dict:
    logger = get_logger()
    cfg = ResearchConfig.for_depth(depth)
    state = ResearchState(question=question, config=cfg, _logger=logger)
    start_new_run(logger, question=question, depth=depth)
    state.cot_sink = open_cot_log(question)
    state.log(f"Deep Research: '{question}'")
    state.log(f"  depth={depth} num_queries={cfg.num_queries} max_sources={cfg.max_sources}")

    phase_results: list[dict] = []

    from services.deep_research.content_profiles import apply_content_profile
    from services.deep_research.dedup_filter import run_dedup_filter
    from services.deep_research.harvest import run_harvest
    from services.deep_research.plan import run_plan
    from services.deep_research.synthesize import run_synthesize

    plan_result = await _run_phase(state, phase_results, "plan", run_plan(state), PHASE_TIMEOUTS["plan"])
    if plan_result is None or not state.query_plans:
        return _build_result(state, "error", phase_results, "Query planning failed")
    state.search_queries = [plan.query for plan in state.query_plans]
    apply_content_profile(state)

    harvest_result = await _run_phase(
        state,
        phase_results,
        "harvest",
        run_harvest(state),
        _harvest_timeout_for(state),
    )
    if harvest_result is None or not state.extracted_sources:
        return _build_result(state, "partial", phase_results, "No sources harvested")

    await _run_phase(
        state,
        phase_results,
        "dedup_filter",
        run_dedup_filter(state),
        _dedup_timeout_for(state),
    )
    state.last_iteration_sources = list(state.extracted_sources)

    await _iterate(state, phase_results)

    synth_result = await _run_phase(
        state,
        phase_results,
        "synthesize",
        run_synthesize(state),
        _synth_timeout(state, depth),
    )

    # If synthesis was killed by timeout or crashed before writing state.final_report,
    # generate a raw source dump so the collected evidence is not lost entirely.
    if not state.final_report or not state.final_report.strip():
        state.error("Synthesis produced no report — writing raw source fallback")
        usable = [
            (i, src, (src.summary or src.relevant_chunks or src.text or "").replace("\x00", "").strip())
            for i, src in enumerate(state.extracted_sources, 1)
        ]
        usable = [(i, src, content) for i, src, content in usable if content]
        lines = [
            f"# Research: {state.question}\n",
            f"*Synthesis failed or timed out after {state.elapsed:.0f}s "
            f"(depth={depth}, sources={len(usable)}/{len(state.extracted_sources)} with content).*\n",
            "*The content below is raw extracted source material, not a synthesised report.*\n",
        ]
        for i, src, content in usable:
            lines.append(f"\n## [{i}] {src.title}\n\n{content[:2000]}\n")
        if usable:
            lines.append("\n---\n\n## Sources\n")
            for i, src, _ in usable:
                lines.append(f"{i}. [{src.title}]({src.url})")
        state.final_report = "\n".join(lines)

    status = "complete" if (synth_result and synth_result.success and state.final_report) else "partial"
    return _build_result(state, status, phase_results)


def _build_result(
    state: ResearchState,
    status: str,
    phase_results: list[dict],
    error: str = "",
) -> dict:
    if error and not state.final_report:
        state.final_report = (
            f"# Research: {state.question}\n\n"
            f"Pipeline terminated early: {error}\n\n"
            f"Completed phases: {', '.join(state.completed_phases) or 'none'}\n"
            f"Sources collected: {state.source_count}\n"
        )
    return {
        "status": status,
        "completed_phases": list(state.completed_phases),
        "report": state.final_report,
        "sources_count": state.source_count,
        "duration_sec": round(state.elapsed, 2),
        "errors": list(state.errors),
        "phase_results": phase_results,
    }


async def run_deep_research(
    question: str,
    depth: str = "medium",
    hard_timeout: Optional[float] = None,
) -> str:
    cfg = ResearchConfig.for_depth(depth)
    timeout = hard_timeout or cfg.total_hard_timeout
    try:
        result = await asyncio.wait_for(orchestrate(question, depth), timeout=timeout)
    except asyncio.TimeoutError:
        return (
            f"# Research: {question}\n\n"
            f"Pipeline timed out after {timeout:.0f}s (depth={depth}).\n"
        )
    return result.get("report", "No report generated.")
