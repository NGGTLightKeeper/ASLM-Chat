# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Legacy-style reflection helpers for iterative deep research."""

from __future__ import annotations

import re
from typing import Any, Callable, Optional

from core.llm.llm_client import call_llm_json
from core.llm.tokenizer import (
    count_tokens,
    derive_token_budget_from_chars,
)
from services.deep_research.models import ResearchState
from services.deep_research.plan import _validate_queries


def _compact_text(text: str) -> str:
    return " ".join((text or "").split()).strip()


def _query_jaccard(q1: str, q2: str) -> float:
    """Word-level Jaccard similarity between two query strings.

    Uses only words of 3+ characters to reduce noise from common short words.
    Returns 0.0–1.0; values ≥ 0.45 indicate near-duplicate queries.
    """
    def _words(q: str) -> set[str]:
        return {w.lower() for w in q.split() if len(w) >= 3}

    w1, w2 = _words(q1), _words(q2)
    if not w1 or not w2:
        return 0.0
    return len(w1 & w2) / len(w1 | w2)


# Noise phrases appended to gap descriptions that should be removed before
# turning a gap into a search query ("Qwen 3.5 context window not found" → "Qwen 3.5 context window").
_GAP_NOISE_RE = re.compile(
    r"\b(not found|not available|not confirmed|not specified|not documented|"
    r"not publicly available|not publicly|unknown|missing|unclear|no data|"
    r"no information|no public|could not find|unable to find|unavailable|"
    r"unconfirmed|not clear|remains unclear|still unknown|cannot be found)\b.*$",
    re.IGNORECASE,
)


def _gap_list_overlap(gaps_a: list[str], gaps_b: list[str]) -> float:
    """Word-level Jaccard similarity between two gap lists (words ≥4 chars)."""
    def _words(gaps: list[str]) -> set[str]:
        return {w.lower() for g in gaps for w in g.split() if len(w) >= 4}
    wa, wb = _words(gaps_a), _words(gaps_b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def _gap_to_targeted_query(gap: str, max_words: int = 8) -> str | None:
    """Convert a gap description into a concise targeted search query.

    Strips trailing noise phrases ("not found", "unknown", "unclear" …) and
    truncates to *max_words* so the result is a usable search string.
    Returns None if nothing meaningful remains.
    """
    query = _GAP_NOISE_RE.sub("", gap).strip().rstrip(".,;:-(")
    if len(query) < 5:
        return None
    words = query.split()
    if len(words) > max_words:
        query = " ".join(words[:max_words])
    return query if len(query) >= 3 else None


def _generate_forced_queries(
    gaps: list[str],
    attempted_queries: list[str],
    max_queries: int = 2,
) -> list[str]:
    """Generate targeted queries from gap descriptions not yet covered.

    Each gap is converted to a concise query via ``_gap_to_targeted_query``.
    Candidates that are too similar (Jaccard ≥ 0.40) to already-attempted
    queries are skipped so we don't just repeat the same searches.
    """
    forced: list[str] = []
    for gap in gaps:
        if len(forced) >= max_queries:
            break
        query = _gap_to_targeted_query(gap, max_words=8)
        if not query:
            continue
        if attempted_queries:
            max_overlap = max(_query_jaccard(query, a) for a in attempted_queries)
            if max_overlap >= 0.40:
                continue
        forced.append(query)
    return forced


def _sanitize_content(text: str) -> str:
    return (text or "").replace("\x00", "").strip()


def _reflection_json_schema(target_queries: int) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["gaps", "followup_queries", "coverage_assessment"],
        "properties": {
            "gaps": {
                "type": "array",
                "items": {"type": "string", "minLength": 1, "maxLength": 200},
                "maxItems": max(1, target_queries),
            },
            "followup_queries": {
                "type": "array",
                "items": {"type": "string", "minLength": 1, "maxLength": 120},
                "maxItems": max(1, target_queries),
            },
            "coverage_assessment": {"type": "string", "minLength": 1, "maxLength": 400},
        },
    }


def _build_coverage_digest(state: ResearchState, *, top_n: int = 8) -> str:
    """Compact quality-sorted overview of the full source pool.

    Always placed first in the reflection context so the model knows what has
    already been harvested before seeing the last-iteration detail.  Kept small
    (~500-800 chars) so it never meaningfully competes for budget.
    """
    sources = state.extracted_sources
    if not sources:
        return ""

    sorted_sources = sorted(
        sources,
        key=lambda s: float(getattr(s, "relevance_score", 0.0) or 0.0),
        reverse=True,
    )

    high = sum(1 for s in sources if float(getattr(s, "relevance_score", 0.0) or 0.0) >= 0.80)
    med  = sum(1 for s in sources if 0.50 <= float(getattr(s, "relevance_score", 0.0) or 0.0) < 0.80)
    low  = len(sources) - high - med

    top_titles = ", ".join(
        f'"{(s.title or "untitled")[:50].strip()}" ({float(getattr(s, "relevance_score", 0.0) or 0.0):.2f})'
        for s in sorted_sources[:top_n]
    )

    lines = [
        f"\n=== POOL OVERVIEW ({len(sources)} sources collected so far) ===",
        f"  Relevance: {high} high (≥0.80), {med} medium (0.50–0.79), {low} low (<0.50)",
        f"  Top sources: {top_titles}",
    ]

    topics = sorted({s.sub_topic for s in sources if s.sub_topic})
    if topics:
        lines.append(f"  Topics covered: {', '.join(topics[:8])}")

    return "\n".join(lines) + "\n"


def _build_gap_history_block(state: ResearchState) -> str:
    """Format the per-iteration gap history for the reflection prompt.

    Shows the last 4 iterations so the model can see which gaps are recurring
    vs newly discovered.  Only injected when at least one previous gap list exists.
    """
    if not state.iteration_gaps:
        return ""

    recent = state.iteration_gaps[-4:]
    first_idx = max(1, len(state.iteration_gaps) - len(recent) + 1)

    lines = ["\n=== GAP HISTORY (what previous iterations could not find) ==="]
    for offset, gaps in enumerate(recent):
        iter_label = f"Iteration {first_idx + offset}"
        gap_str = "; ".join(gaps[:6]) if gaps else "none recorded"
        lines.append(f"  {iter_label}: {gap_str}")
    lines.append(
        "  NOTE: Gaps that persist across 2+ iterations likely have no strong public source.\n"
        "  Do NOT generate the same queries again. Either try a genuinely different angle\n"
        "  or return empty followup_queries to signal coverage is sufficient."
    )
    return "\n".join(lines) + "\n"


def _build_reflection_context(
    state: ResearchState,
    *,
    prompt_char_budget: int,
    snippet_char_limit: int = 220,
) -> tuple[str, dict[str, int]]:
    budget = max(4000, int(prompt_char_budget))
    budget_tokens = derive_token_budget_from_chars(budget)
    blocks: list[str] = []
    used_chars = 0
    used_tokens = 0
    extracted_added = 0
    snippet_added = 0
    budget_reached = 0

    def _truncate_to_fit(block: str, remaining_chars: int, remaining_tokens: int) -> str:
        candidate = block[:remaining_chars].rstrip()
        if not candidate:
            return ""
        while candidate and count_tokens(candidate) > remaining_tokens and len(candidate) > 256:
            candidate = candidate[: max(128, int(len(candidate) * 0.85))].rstrip()
        return candidate

    def _try_add(block: str) -> bool:
        nonlocal used_chars, used_tokens, budget_reached
        if not block:
            return False
        remaining_chars = budget - used_chars
        remaining_tokens = budget_tokens - used_tokens
        if remaining_chars <= 0 or remaining_tokens <= 0:
            budget_reached = 1
            return False
        block_tokens = count_tokens(block)
        if len(block) <= remaining_chars and block_tokens <= remaining_tokens:
            blocks.append(block)
            used_chars += len(block)
            used_tokens += block_tokens
            return True
        if not blocks:
            truncated = _truncate_to_fit(block, remaining_chars, remaining_tokens)
            if truncated:
                if not truncated.endswith("\n"):
                    truncated += "\n"
                blocks.append(truncated)
                used_chars += len(truncated)
                used_tokens += count_tokens(truncated)
        budget_reached = 1
        return False

    # ── 1. Coverage digest ────────────────────────────────────────────────────
    # Always first: compact quality-sorted overview of the full pool.
    # This lets the model understand what topics are already covered without
    # spending budget on per-source full text for items outside last iteration.
    digest = _build_coverage_digest(state)
    if digest:
        _try_add(digest)

    # ── 2. Previous iteration full content ───────────────────────────────────
    # Sort by relevance so the best sources from the last iteration appear first.
    prev_sources = sorted(
        state.last_iteration_sources,
        key=lambda s: float(getattr(s, "relevance_score", 0.0) or 0.0),
        reverse=True,
    )
    extracted_blocks: list[str] = []
    for i, source in enumerate(prev_sources, 1):
        content = _sanitize_content(source.summary or source.relevant_chunks or source.text or "")
        if not content:
            continue
        extracted_blocks.append(
            f"\n[EXTRACTED {i}]\n"
            f"Title: {source.title}\n"
            f"URL: {source.url}\n"
            f"Content:\n{content}\n"
        )

    if extracted_blocks:
        _try_add("\n=== PREVIOUS ITERATION FULL CONTENT ===\n")
        for block in extracted_blocks:
            if _try_add(block):
                extracted_added += 1
            else:
                break

    # ── 3. Snippets: extracted pool (relevance-sorted) then raw results ───────
    # Extracted sources come first and are sorted by relevance so the model sees
    # the best evidence before running out of budget on low-quality raw snippets.
    #
    # Sources already shown in EXTRACTED section are excluded to avoid duplication.
    # For extracted sources without summary/chunks, we prefer the raw search snippet
    # (compact, original) over the full page text to keep the section readable.
    seen_snippet_urls: set[str] = set(s.url for s in prev_sources)  # skip already shown in EXTRACTED
    snippet_blocks: list[str] = []
    snippet_index = 1

    # Pre-build URL → compact search snippet lookup for use as fallback.
    raw_snippet_by_url: dict[str, str] = {
        r.url: _compact_text(r.snippet or "")
        for r in state.raw_results
        if r.snippet
    }

    sorted_extracted = sorted(
        state.extracted_sources,
        key=lambda s: float(getattr(s, "relevance_score", 0.0) or 0.0),
        reverse=True,
    )
    for source in sorted_extracted:
        if source.url in seen_snippet_urls:
            continue
        seen_snippet_urls.add(source.url)
        # Prefer structured summary/chunks; fall back to original search snippet
        # (compact); use full text only as last resort (it gets truncated anyway).
        snippet_text = (
            source.summary
            or source.relevant_chunks
            or raw_snippet_by_url.get(source.url, "")
            or source.text
        )
        snippet = _compact_text(snippet_text)[: max(120, snippet_char_limit)]
        if not snippet:
            continue
        snippet_blocks.append(
            f"\n[SEARCH {snippet_index}]\n"
            f"Title: {source.title}\n"
            f"URL: {source.url}\n"
            f"Snippet: {snippet}\n"
        )
        snippet_index += 1

    for result in state.raw_results:
        if result.url in seen_snippet_urls:
            continue
        seen_snippet_urls.add(result.url)
        snippet = _compact_text(result.snippet or "")[: max(120, snippet_char_limit)]
        if not snippet:
            continue
        snippet_blocks.append(
            f"\n[SEARCH {snippet_index}]\n"
            f"Title: {result.title}\n"
            f"URL: {result.url}\n"
            f"Snippet: {snippet}\n"
        )
        snippet_index += 1

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
        "used_tokens": used_tokens,
        "budget_tokens": budget_tokens,
        "budget_reached": budget_reached,
    }


def _make_cot_sink(state: ResearchState) -> Optional[Callable[[str], None]]:
    """Return a sink that writes raw model thinking to the CoT log for this iteration."""
    if state.cot_sink is None:
        return None
    state._reflection_count += 1
    iteration = state._reflection_count

    def sink(thinking: str) -> None:
        try:
            state.cot_sink(thinking, iteration)  # type: ignore[misc]
        except Exception:
            pass

    return sink


async def reflect_and_generate_followup(
    state: ResearchState,
    failed_queries: list[str] | None = None,
    attempted_queries: list[str] | None = None,
) -> list[str]:
    """LLM reflection over current coverage to request focused follow-up queries."""
    cfg = state.config
    state.log("Reflection...")
    reflection_timeout = max(15.0, float(cfg.reflection_timeout_sec))

    # 0.0 means "not set" — default reflection temperature is 0.4.
    r_temp = float(cfg.reflection_temperature) if cfg.reflection_temperature > 0.0 else 0.4

    state.log(
        f"  [llm] reflection timeout={reflection_timeout:.0f}s temp={r_temp:.2f}"
    )
    reflection_context, reflection_meta = _build_reflection_context(
        state,
        prompt_char_budget=int(cfg.reflection_prompt_char_budget),
        snippet_char_limit=int(getattr(cfg, "reflection_snippet_char_limit", 220)),
    )
    state.log(
        "  Reflection ctx: "
        f"extracted={reflection_meta['extracted_added']} "
        f"snippets={reflection_meta['snippet_added']} "
        f"chars={reflection_meta['used_chars']}"
        + (" (budget reached)" if reflection_meta.get("budget_reached") else "")
    )

    failed_block = ""
    if failed_queries:
        failed_block = "\nThese queries returned nothing - DO NOT repeat:\n"
        for query in failed_queries:
            failed_block += f"  - {query}\n"

    attempted_block = ""
    if attempted_queries:
        attempted_block = "\nAlready attempted follow-up queries - avoid repeating unless absolutely necessary:\n"
        for query in attempted_queries[-12:]:
            attempted_block += f"  - {query}\n"

    gap_history_block = _build_gap_history_block(state)

    prompt = f"""You are a research quality reviewer.

Original question: "{state.question}"

Extracted source contents and unextracted search snippets:
{reflection_context}
{gap_history_block}
{failed_block}
{attempted_block}
If findings are comprehensive, return empty followup_queries.
Otherwise generate 3-{max(3, int(cfg.followup_queries_per_iteration))} follow-up queries.

QUERY FORMAT:
- Short English search phrases only — NO questions, NO full sentences
- GOOD: "GLiNER documentation usage", "pytorch memory optimization large batch"
- BAD: "What are the performance metrics of GLiNER?"

DIG DEEPER:
- Do not keep searching the same question from slightly different wording.
- If a gap mentions a specific name, version, feature, limit, claim, or missing attribute,
  generate a query for that deeper missing detail instead of another broad overview.
- Prefer targeted evidence angles such as official docs, release notes, changelogs,
  specifications, constraints, compatibility, pricing, limits, or implementation details
  when they are relevant to the remaining gap.
- Only return empty followup_queries when the important named details have been checked
  or the available sources strongly indicate that they cannot be found publicly.

DIVERSITY — assign each query a different angle type from this list:
  factual      : what/how something works  ("transformer attention mechanism")
  comparative  : X vs Y, alternatives     ("pytorch vs jax training speed")
  procedural   : how to do it             ("huggingface fine-tuning tutorial")
  data/metrics : numbers, limits          ("API rate limit values")
  troubleshoot : problems, edge cases     ("pytorch CUDA out of memory large batch")
  site-targeted: pin to a specific source ("site:github.com GLiNER open issues")

Pick the angle types that are most useful for the remaining gaps — you do NOT need to
use all six. But do NOT generate two queries of the same type.

Return JSON:
{{
  "gaps": ["gap1", "gap2"],
  "followup_queries": ["query1", "query2"],
  "coverage_assessment": "brief"
}}"""

    result = await call_llm_json(
        prompt=prompt,
        model=cfg.query_model,
        temperature=r_temp,
        json_schema=_reflection_json_schema(int(cfg.followup_queries_per_iteration)),
        schema_name="research_reflection_followup",
        structured_output=cfg.structured_output_enabled,
        strict=cfg.structured_output_strict,
        cot_sink=_make_cot_sink(state),
        timeout=reflection_timeout,
        debug_label="reflection",
        debug_log=state.log,
    )

    if not isinstance(result, dict):
        state.log("  WARN Failed to parse reflection output, generating fallback follow-up")
        blocked_set = {
            query.strip().lower()
            for query in ((failed_queries or []) + (attempted_queries or []))
            if query and query.strip()
        }
        subject = ""
        for candidate in state.search_queries or []:
            cleaned = " ".join((candidate or "").split()).strip()
            if not cleaned:
                continue
            subject = " ".join(cleaned.split()[:5]).strip()
            break
        if not subject:
            words = state.question.strip().split()
            subject = " ".join(words[:5]).strip() or state.question.strip()[:60]
        fallback = []
        for aspect in ("comparison", "specs", "review", "alternatives", "problems", "benchmarks"):
            candidate = f"{subject} {aspect}".strip()
            if candidate.lower() in blocked_set:
                continue
            fallback.append(candidate)
            if len(fallback) >= max(1, int(cfg.followup_queries_per_iteration)):
                break
        validated = _validate_queries(fallback, max_words=6, max_chars=70)
        for query in validated:
            state.log(f"  fallback: {query}")
        return validated[: max(1, int(cfg.followup_queries_per_iteration))]

    gaps = result.get("gaps", [])
    followup = result.get("followup_queries", [])
    assessment = result.get("coverage_assessment", "N/A")
    state.log(f"  {assessment}")
    for gap in gaps:
        state.log(f"  Gap: {gap}")

    # ── Jaccard dedup: drop follow-up queries too similar to already-attempted ones ──
    # Catches rephrasing that string-equality misses ("X benchmark" vs "X speed test").
    # Threshold 0.45: loose enough to allow same topic from a different angle,
    # strict enough to catch pure synonym swaps.
    if followup and attempted_queries:
        deduped: list[str] = []
        for q in followup:
            max_overlap = max(
                (_query_jaccard(q, prev) for prev in attempted_queries),
                default=0.0,
            )
            if max_overlap >= 0.45:
                state.log(
                    f"  Jaccard-dedup dropped {q!r} "
                    f"(overlap={max_overlap:.0%} with attempted queries)"
                )
            else:
                deduped.append(q)
        followup = deduped

    if followup:
        for query in followup:
            state.log(f"  Follow-up: {query}")
    else:
        state.log("  Coverage is sufficient — checking for untried named gaps...")
        # ── Named-gap safety net ─────────────────────────────────────────────
        # The model returned no follow-ups, but the gaps it just identified may
        # contain named details (model versions, specs, limits) that have never
        # been targeted by a search.  If the gaps are NEW (not a repeat of the
        # previous iteration's gaps), force at least one targeted query so we
        # don't stop prematurely before exploring the specific missing details.
        gap_strings = [str(g) for g in gaps if g]
        if gap_strings:
            prev_gaps = state.iteration_gaps[-1] if state.iteration_gaps else []
            gaps_are_new = not prev_gaps or _gap_list_overlap(gap_strings, prev_gaps) < 0.65
            if gaps_are_new:
                n_forced = max(1, int(cfg.followup_queries_per_iteration) // 2)
                forced = _generate_forced_queries(
                    gap_strings,
                    attempted_queries or [],
                    max_queries=n_forced,
                )
                if forced:
                    state.log(
                        f"  Named-gap safety: {len(forced)} untried named detail(s) found — "
                        "blocking premature stop"
                    )
                    for q in forced:
                        state.log(f"  Forced: {q}")
                    state.iteration_gaps.append(gap_strings)
                    return _validate_queries(forced, max_words=8, max_chars=80)
        state.log("  Coverage sufficient — no untried named gaps, stopping")

    # Save gaps for stagnation detection in the orchestrator.
    if gaps:
        state.iteration_gaps.append([str(g) for g in gaps if g])

    return _validate_queries(followup, max_words=6, max_chars=70)
