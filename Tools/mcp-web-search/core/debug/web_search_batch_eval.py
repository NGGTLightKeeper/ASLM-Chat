"""Batch evaluator for neural/domain web_search routing.

This is an operator tool, not a unit test. It runs live provider searches for a
small taxonomy-covering query set, fetches previews, runs both local ASLM
embedding exports, and writes a compact JSON + Markdown report.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from core.extract.content_processor import PreviewPayload
from core.query import infer_query_types_from_rules, score_query_against_profiles
from core.query.domain_constraints import build_provider_query, filter_results_by_domain_constraints, parse_domain_constraints
from core.query.aslm_embedding_runtime import (
    format_source_relevance_input,
    SearchModelSession,
)
from core.query.routing_score import allocate_source_budget
from core.registry.domain_registry import get_registry
from core.registry.trust_registry import get_trust_registry
from services.web_search import (
    WebSearchOptions,
    WebSearchService,
    _apply_effort_to_output_profile,
    _apply_year_hint_policy,
    _content_quality_signal,
    _fetch_previews,
    _get_output_profile,
    _normalize_search_effort,
    _parse_query_profile,
    _result_score,
    _build_neural_class_mix,
    get_preview_settings,
    infer_query_language,
    load_search_config,
)


BASIC_CASES: list[dict[str, str]] = [
    {"class": "finance", "query": "Nvidia latest earnings revenue guidance"},
    {"class": "medical", "query": "metformin side effects kidney disease"},
    {"class": "journalistic", "query": "France election results 2024 Reuters"},
    {"class": "academic", "query": "transformer attention mechanism arxiv survey"},
    {"class": "shopping", "query": "best laptop under 1000"},
    {"class": "troubleshooting", "query": "windows 11 bluetooth headphones no sound fix"},
    {"class": "forum", "query": "reddit mechanical keyboard recommendations"},
    {"class": "technical", "query": "c++ vector erase complexity"},
    {"class": "legal", "query": "California tenant security deposit law"},
    {"class": "government", "query": "IRS passport renewal official form"},
    {"class": "real_estate", "query": "Austin TX median rent apartments 2025"},
    {"class": "automotive", "query": "Toyota Camry hybrid maintenance schedule"},
    {"class": "travel", "query": "Japan rail pass price 2025"},
    {"class": "weather", "query": "weather tomorrow Yekaterinburg"},
    {"class": "local", "query": "coffee shops near Times Square open now"},
    {"class": "careers", "query": "senior backend engineer salary Berlin"},
    {"class": "education", "query": "MIT computer science admission requirements"},
    {"class": "documentation", "query": "FastAPI dependency injection documentation"},
    {"class": "entertainment", "query": "Dune Part Two cast release date"},
    {"class": "sports", "query": "NBA standings western conference"},
    {"class": "general", "query": "cat behavior"},
]


def _top_pairs(mapping: dict[str, float], limit: int = 5) -> list[list[Any]]:
    return [
        [name, round(score, 4)]
        for name, score in sorted(mapping.items(), key=lambda item: item[1], reverse=True)[:limit]
    ]


def _class_mix(hybrid: list[tuple[str, float, str]]) -> dict[str, float]:
    return {name: float(weight) for name, weight, _reason in hybrid}


def _weighted(values: dict[str, float], mix: dict[str, float], default: float = 1.0) -> float:
    return sum(weight * float(values.get(name, default)) for name, weight in mix.items()) or default


def _trust_entry_for_url(trust_registry, url: str):
    host = urlparse(url or "").netloc.lower()
    for pattern, entry in getattr(trust_registry, "_lookup", {}).items():
        if host == pattern or host.endswith("." + pattern):
            return entry
    return None


def _domain_trace(url: str, mix: dict[str, float]) -> dict[str, Any]:
    registry = get_registry()
    info = registry.lookup(url)
    strategy = registry.resolve_access_strategy(url)
    path = urlparse(url or "").path or "/"
    matched_path = ""
    path_weight = 1.0
    for item in sorted(info.path_weights, key=lambda candidate: len(candidate.path_prefix), reverse=True):
        if path.startswith(item.path_prefix):
            matched_path = item.path_prefix
            path_weight = _weighted(item.class_weights, mix)
            break
    base = float(info.base_weight or 1.0)
    class_weight = _weighted(info.class_weights, mix)
    demotion = _weighted(info.hard_demotions, mix)
    raw = base * class_weight * demotion * path_weight
    return {
        "pattern": info.pattern,
        "tier": info.tier,
        "method": info.method,
        "class_weight": round(class_weight, 4),
        "hard_demotion": round(demotion, 4),
        "path_prefix": matched_path,
        "path_weight": round(path_weight, 4),
        "multiplier": round(max(0.55, min(1.45, raw)), 4),
        "access_method": strategy.method,
        "access_source": strategy.source,
        "endpoint_url": strategy.endpoint_url,
    }


def _trust_trace(trust_registry, url: str, mix: dict[str, float]) -> dict[str, Any]:
    entry = _trust_entry_for_url(trust_registry, url)
    if entry is None:
        return {"pattern": "", "tier": "?", "weight": 0.0, "affinity": 1.0, "blacklisted": False}
    affinity = _weighted(entry.class_affinity, mix)
    return {
        "pattern": entry.pattern,
        "tier": entry.tier,
        "weight": trust_registry.get_weight(url),
        "affinity": round(max(0.55, min(1.25, affinity)), 4),
        "blacklisted": trust_registry.is_blacklisted(url),
    }


def _case_flags(expected: str, model_top: str, hybrid: list[tuple[str, float, str]], rows: list[dict[str, Any]]) -> list[str]:
    flags: list[str] = []
    hybrid_classes = [name for name, _weight, _reason in hybrid]
    if expected not in hybrid_classes:
        flags.append("expected_class_missing_from_hybrid")
    if model_top != expected:
        flags.append(f"model_primary={model_top}")
    if not rows:
        flags.append("no_results")
        return flags
    if all(row["preview_chars"] == 0 for row in rows):
        flags.append("no_previews")
    if all(row["domain_pattern"] == "*" for row in rows):
        flags.append("domain_registry_default_only")
    source_hits = [
        row
        for row in rows
        if expected in [name for name, _score in row.get("source_top", [])[:3]]
    ]
    if not source_hits:
        flags.append("source_model_expected_missing_top3")
    return flags


async def _evaluate_case(
    case: dict[str, str],
    *,
    query_model,
    source_model,
    model_session: SearchModelSession,
    service: WebSearchService,
    opts: WebSearchOptions,
    inspect_results: int,
) -> dict[str, Any]:
    cfg = load_search_config()
    started = time.perf_counter()
    raw_query = case["query"]
    expected = case["class"]

    constraints = parse_domain_constraints(raw_query)
    analysis_query = constraints.clean_query or raw_query
    analysis_query, year_hint = _apply_year_hint_policy(analysis_query, cfg.query)
    provider_query = build_provider_query(raw_query, constraints) or analysis_query
    lang = infer_query_language(analysis_query)
    rules = score_query_against_profiles(analysis_query)
    rules_only = infer_query_types_from_rules(analysis_query, limit=3)

    query_prediction = query_model.predict([analysis_query])[0]
    class_mix_items, class_debug = _build_neural_class_mix(analysis_query, model_session)
    hybrid = [(item.name, item.weight, item.reason) for item in class_mix_items]
    query_types = [item.name for item in class_mix_items] or rules_only
    query_type = query_types[0] if query_types else "general"
    mix = _class_mix(hybrid)
    out_profile = _apply_effort_to_output_profile(_get_output_profile(query_types), opts)
    query_profile = _parse_query_profile(analysis_query)

    deduped, triage, effective_query = await service._run_with_zero_result_fallback(
        provider_query=provider_query,
        analysis_query=analysis_query,
        query_types=query_types,
        out_profile=out_profile,
            opts=opts,
            req_id=f"batch_{expected}",
            class_mix=class_mix_items,
            source_budget=allocate_source_budget(class_mix_items, out_profile.max_results),
            model_session=model_session,
        )
    if effective_query != analysis_query:
        analysis_query = effective_query
        query_profile = _parse_query_profile(analysis_query)
    if constraints.has_constraints:
        deduped = filter_results_by_domain_constraints(deduped, constraints)
        from services.web_search import _triage_results

        triage = _triage_results(deduped, analysis_query) if deduped else []

    payloads = [PreviewPayload()] * len(deduped)
    to_fetch = []
    to_fetch_indexes = []
    policies = []
    for index, (result, decision) in enumerate(zip(deduped, triage)):
        if not decision.skip and len(to_fetch) < int(out_profile.preview_fetch_limit):
            to_fetch.append(result)
            to_fetch_indexes.append(index)
            policies.append(decision.fetch_policy)

    if to_fetch and opts.fetch_previews:
        loop = asyncio.get_running_loop()
        fetched = await _fetch_previews(
            to_fetch,
            query=analysis_query,
            concurrency=opts.concurrency,
            fetch_timeout=opts.fetch_timeout,
            total_timeout=opts.total_timeout,
            preview_settings=get_preview_settings(apply_hardware_profile=False),
            loop=loop,
            policies=policies,
            early_return_threshold=(
                0
                if _normalize_search_effort(opts.effort) == "high"
                else max(0, int(cfg.search.early_return_threshold))
            ),
            req_id=f"batch_{expected}",
            deadline=None,
        )
        for index, payload in zip(to_fetch_indexes, fetched):
            payloads[index] = payload

    trust_registry = get_trust_registry()
    source_inputs = [
        format_source_relevance_input(
            query=analysis_query,
            title=result.title,
            url=result.url,
            snippet=result.snippet,
            preview=payload.text,
        )
        for result, payload in list(zip(deduped, payloads))[:inspect_results]
    ]
    source_predictions = source_model.predict(source_inputs) if source_inputs else []

    rows = []
    for index, (result, decision, payload, source_prediction) in enumerate(
        zip(deduped, triage, payloads, source_predictions, strict=False)
    ):
        if index >= inspect_results:
            break
        result.parsed_relevance_score = round(source_prediction.score, 4) if source_prediction is not None else 0.0
        domain = _domain_trace(result.url, mix)
        trust = _trust_trace(trust_registry, result.url, mix)
        current_score = _result_score(
            result,
            payload,
            index=index,
            total=len(deduped),
            query=analysis_query,
            profile=query_profile,
            query_type=query_type,
            rep_store=None,
        )
        adjusted = current_score * float(domain["multiplier"]) * float(trust["affinity"])
        source_top = source_prediction.top(5) if source_prediction is not None else []
        rows.append(
            {
                "rank": index + 1,
                "title": result.title,
                "url": result.url,
                "engine": result.engine,
                "trust_tier": result.trust_tier,
                "triage_score": round(decision.score, 4),
                "triage_policy": decision.fetch_policy,
                "triage_skip": decision.skip,
                "preview_chars": len(payload.text or ""),
                "preview_strategy": payload.strategy_used,
                "source_score": round(source_prediction.score, 4) if source_prediction is not None else 0.0,
                "source_top": [[name, round(score, 4)] for name, score in source_top],
                "domain_pattern": domain["pattern"],
                "domain_method": domain["method"],
                "domain_multiplier": domain["multiplier"],
                "trust_pattern": trust["pattern"],
                "trust_affinity": trust["affinity"],
                "current_score": round(current_score, 4),
                "adjusted_score": round(adjusted, 4),
                "content_quality_signal": round(_content_quality_signal(payload, result, analysis_query), 4)
                if payload.text
                else 0.0,
            }
        )

    model_top = query_prediction.top(1)[0][0]
    flags = _case_flags(expected, model_top, hybrid, rows)
    return {
        "expected_class": expected,
        "query": raw_query,
        "analysis_query": analysis_query,
        "provider_query": provider_query,
        "lang": lang,
        "year_hint": year_hint,
        "elapsed_sec": round(time.perf_counter() - started, 3),
        "result_count": len(deduped),
        "query_model": {
            "score": round(query_prediction.score, 4),
            "top": _top_pairs(query_prediction.labels, 8),
        },
        "rules_top": [
            {"class": item.class_name, "score": round(item.score, 4), "reasons": item.reasons[:4]}
            for item in rules[:8]
            if item.score > 0 or item.reasons
        ],
        "rules_only": rules_only,
        "hybrid": [
            {"class": name, "weight": weight, "reason": reason}
            for name, weight, reason in hybrid
        ],
        "class_debug": class_debug,
        "flags": flags,
        "rows": rows,
    }


def _render_markdown(cases: list[dict[str, Any]]) -> str:
    lines = [
        "# Web Search Neural/Domain Batch Eval",
        "",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Summary",
        "",
        "| Class | Query | Model Top | Hybrid | Results | Preview | Flags |",
        "|---|---|---|---|---:|---:|---|",
    ]
    for case in cases:
        model_top = case["query_model"]["top"][0][0] if case["query_model"]["top"] else "?"
        hybrid = ", ".join(f"{item['class']}:{item['weight']:.2f}" for item in case["hybrid"])
        preview_count = sum(1 for row in case["rows"] if row["preview_chars"] > 0)
        flags = ", ".join(case["flags"]) if case["flags"] else "ok"
        lines.append(
            f"| {case['expected_class']} | `{case['query']}` | {model_top} | {hybrid} | "
            f"{case['result_count']} | {preview_count}/{len(case['rows'])} | {flags} |"
        )
    lines.extend(["", "## Details", ""])
    for case in cases:
        lines.extend(
            [
                f"### {case['expected_class']}: `{case['query']}`",
                "",
                f"- Query model: {case['query_model']['top'][:5]}",
                f"- Rules: {case['rules_top'][:4]}",
                f"- Hybrid: {case['hybrid']}",
                f"- Flags: {case['flags'] or ['ok']}",
                "",
                "| Rank | Title | Domain Pattern | Trust | Triage | Preview | Source Model Top | Current | Adjusted |",
                "|---:|---|---|---|---|---:|---|---:|---:|",
            ]
        )
        for row in case["rows"]:
            title = str(row["title"]).replace("|", "\\|")[:90]
            source_top = ", ".join(f"{name}:{score:.2f}" for name, score in row["source_top"][:3])
            lines.append(
                f"| {row['rank']} | {title} | {row['domain_pattern']} | {row['trust_tier']} | "
                f"{row['triage_policy']} {row['triage_score']:.2f} | {row['preview_chars']} | "
                f"{source_top} | {row['current_score']:.3f} | {row['adjusted_score']:.3f} |"
            )
        lines.append("")
    return "\n".join(lines)


async def _main_async(args: argparse.Namespace) -> int:
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    class_slug = "all" if not args.classes else "-".join(args.classes)
    class_slug = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in class_slug)[:80]
    stamp = f"{time.strftime('%Y%m%d_%H%M%S')}_{os.getpid()}_{class_slug}"

    print("[models] loading ASLM embedding encoder/decoder")

    opts = WebSearchOptions(
        max_results=args.max_results,
        fetch_previews=not args.no_fetch_previews,
        concurrency=args.concurrency,
        fetch_timeout=args.fetch_timeout,
        total_timeout=args.total_timeout,
        effort=args.effort,
        use_hosted_engines=not args.no_hosted,
        use_fast_academic=not args.no_academic,
        candidate_pool_multiplier=args.candidate_pool_multiplier,
        ddgs_hedge_count=args.ddgs_hedge_count,
    )
    service = WebSearchService(opts)
    selected = BASIC_CASES if not args.classes else [case for case in BASIC_CASES if case["class"] in set(args.classes)]

    cases = []
    with SearchModelSession(load=True, device=args.device) as model_session:
        query_model = model_session.encoder
        source_model = model_session.decoder
        if query_model is None or source_model is None:
            raise RuntimeError("ASLM model session failed to load")
        for index, case in enumerate(selected, start=1):
            print(f"[{index}/{len(selected)}] {case['class']}: {case['query']}")
            try:
                cases.append(
                    await _evaluate_case(
                        case,
                        query_model=query_model,
                        source_model=source_model,
                        model_session=model_session,
                        service=service,
                        opts=opts,
                        inspect_results=args.inspect_results,
                    )
                )
            except Exception as exc:
                cases.append(
                    {
                        "expected_class": case["class"],
                        "query": case["query"],
                        "flags": [f"error:{type(exc).__name__}:{exc}"],
                        "query_model": {"top": []},
                        "hybrid": [],
                        "result_count": 0,
                        "rows": [],
                    }
                )
                print(f"  error: {type(exc).__name__}: {exc}")

    json_path = out_dir / f"web_search_batch_eval_{stamp}.json"
    md_path = out_dir / f"web_search_batch_eval_{stamp}.md"
    json_path.write_text(json.dumps(cases, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(_render_markdown(cases), encoding="utf-8")
    print(f"[done] json={json_path}")
    print(f"[done] markdown={md_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run live batch eval for web_search neural/domain routing")
    parser.add_argument("--classes", nargs="*", help="Only run selected expected classes")
    parser.add_argument("--max-results", type=int, default=6)
    parser.add_argument("--inspect-results", type=int, default=3)
    parser.add_argument("--no-fetch-previews", action="store_true")
    parser.add_argument("--no-hosted", action="store_true")
    parser.add_argument("--no-academic", action="store_true")
    parser.add_argument("--candidate-pool-multiplier", type=int, default=1)
    parser.add_argument("--ddgs-hedge-count", type=int, default=1)
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--fetch-timeout", type=float, default=5.0)
    parser.add_argument("--total-timeout", type=float, default=10.0)
    parser.add_argument("--effort", default="medium", choices=["low", "medium", "high"])
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--output-dir", default="tmp")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
