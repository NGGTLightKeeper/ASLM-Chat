"""Interactive debug console for the real web_search pipeline.

Run from ``Tools/mcp-web-search``:

    python -m core.debug.web_search_console

Useful one-shot form:

    python -m core.debug.web_search_console --once "reactive oxygen species pubmed" --fetch-previews
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from dataclasses import replace
from typing import Any
from urllib.parse import urlparse

from core.extract.content_processor import PreviewPayload
from core.query import (
    infer_query_types_from_rules,
    score_query_against_profiles,
)
from core.query.domain_constraints import (
    build_provider_query,
    filter_results_by_domain_constraints,
    parse_domain_constraints,
)
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
    _adapt_output_profile,
    _apply_effort_to_output_profile,
    _apply_year_hint_policy,
    _content_quality_signal,
    _effective_output_limit,
    _fetch_previews,
    _format_results,
    _get_output_profile,
    _is_low_effort,
    _make_request_id,
    _normalize_search_effort,
    _parse_query_profile,
    _result_score,
    _build_neural_class_mix,
    _triage_results,
    get_preview_settings,
    infer_query_language,
    infer_query_types,
    load_search_config,
)


class _ConsoleTraceHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        print(f"[trace] {record.getMessage()}")


def _install_trace_logging() -> None:
    logger = logging.getLogger("trace.web_search")
    logger.setLevel(logging.INFO)
    if not any(isinstance(handler, _ConsoleTraceHandler) for handler in logger.handlers):
        logger.addHandler(_ConsoleTraceHandler())
    logger.propagate = False


def _domain_from_url(url: str) -> str:
    host = urlparse(url or "").netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _trust_entry_for_url(trust_registry, url: str):
    host = urlparse(url or "").netloc.lower()
    for pattern, entry in getattr(trust_registry, "_lookup", {}).items():
        if host == pattern or host.endswith("." + pattern):
            return entry
    return None


def _class_mix(hybrid: list[tuple[str, float, str]]) -> dict[str, float]:
    return {name: float(weight) for name, weight, _reason in hybrid}


def _weighted_map_value(values: dict[str, float], class_mix: dict[str, float], default: float = 1.0) -> float:
    if not class_mix:
        return default
    return sum(weight * float(values.get(name, default)) for name, weight in class_mix.items()) or default


def _domain_debug(url: str, class_mix: dict[str, float]) -> dict[str, Any]:
    registry = get_registry()
    info = registry.lookup(url)
    strategy = registry.resolve_access_strategy(url)
    path = urlparse(url or "").path or "/"
    matched_path = ""
    path_weight = 1.0
    for candidate in sorted(info.path_weights, key=lambda item: len(item.path_prefix), reverse=True):
        if path.startswith(candidate.path_prefix):
            matched_path = candidate.path_prefix
            path_weight = _weighted_map_value(candidate.class_weights, class_mix)
            break

    base = float(info.base_weight or 1.0)
    class_weight = _weighted_map_value(info.class_weights, class_mix)
    demotion = _weighted_map_value(info.hard_demotions, class_mix)
    raw = base * class_weight * demotion * path_weight
    return {
        "pattern": info.pattern,
        "tier": info.tier,
        "method": info.method,
        "base_weight": round(base, 4),
        "class_weight": round(class_weight, 4),
        "hard_demotion": round(demotion, 4),
        "path_prefix": matched_path,
        "path_weight": round(path_weight, 4),
        "raw_multiplier": round(raw, 4),
        "bounded_multiplier": round(max(0.55, min(1.45, raw)), 4),
        "access": {
            "source": strategy.source,
            "method": strategy.method,
            "domain": strategy.domain,
            "endpoint_url": strategy.endpoint_url,
            "rewritten_url": strategy.rewritten_url,
            "scope": strategy.scope,
            "method_hint": strategy.method_hint,
        },
    }


def _trust_debug(trust_registry, url: str, class_mix: dict[str, float]) -> dict[str, Any]:
    entry = _trust_entry_for_url(trust_registry, url)
    if entry is None:
        return {"pattern": "", "tier": "?", "weight": 0.0, "affinity": 1.0, "blacklisted": False}
    affinity = _weighted_map_value(entry.class_affinity, class_mix)
    return {
        "pattern": entry.pattern,
        "tier": entry.tier,
        "weight": trust_registry.get_weight(url),
        "affinity": round(max(0.55, min(1.25, affinity)), 4),
        "blacklisted": trust_registry.is_blacklisted(url),
    }


def _print_json(title: str, value: Any) -> None:
    print(f"\n== {title} ==")
    print(json.dumps(value, indent=2, ensure_ascii=False, default=str))


def _top_pairs(mapping: dict[str, float], limit: int = 8) -> list[list[Any]]:
    return [
        [name, round(score, 4)]
        for name, score in sorted(mapping.items(), key=lambda item: item[1], reverse=True)[:limit]
    ]


class WebSearchDebugConsole:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.cfg = load_search_config()
        self.options = WebSearchOptions(
            max_results=args.max_results,
            fetch_previews=args.fetch_previews,
            concurrency=args.concurrency,
            fetch_timeout=args.fetch_timeout,
            total_timeout=args.total_timeout,
            effort=args.effort,
            use_hosted_engines=not args.no_hosted,
            use_fast_academic=not args.no_academic,
            candidate_pool_multiplier=args.candidate_pool_multiplier,
            ddgs_hedge_count=args.ddgs_hedge_count,
            ddgs_worker_timeout=args.ddgs_worker_timeout,
            ddgs_engine_timeout=args.ddgs_engine_timeout,
            ddgs_max_retries=args.ddgs_max_retries,
        )
        self.service = WebSearchService(self.options)
        self.model_session: SearchModelSession | None = None
        self.query_model = None
        self.source_model = None
        if args.neural:
            self._load_models()

    def _load_models(self) -> None:
        print("[models] loading ASLM embedding encoder/decoder...")
        t0 = time.perf_counter()
        self.model_session = SearchModelSession(load=True, device=self.args.device)
        self.model_session.__enter__()
        self.query_model = self.model_session.encoder
        self.source_model = self.model_session.decoder
        print(f"[models] session ready in {time.perf_counter() - t0:.2f}s")

    def close(self) -> None:
        if self.model_session is not None:
            self.model_session.close()
        self.model_session = None
        self.query_model = None
        self.source_model = None

    async def run_query(self, raw_query: str) -> None:
        raw_query = (raw_query or "").strip()
        if not raw_query:
            return

        started = time.perf_counter()
        req_id = f"console_{_make_request_id()}"
        constraints = parse_domain_constraints(raw_query)
        analysis_query = constraints.clean_query or raw_query
        analysis_query, year_hint = _apply_year_hint_policy(analysis_query, self.cfg.query)
        provider_query = build_provider_query(raw_query, constraints) or analysis_query
        lang = infer_query_language(analysis_query)
        rules = score_query_against_profiles(analysis_query)
        rules_top = [
            {
                "class": item.class_name,
                "score": round(item.score, 4),
                "reasons": item.reasons[:5],
            }
            for item in rules[:8]
            if item.score > 0 or item.reasons
        ]
        rules_only_types = infer_query_types_from_rules(analysis_query, limit=3)

        model_prediction = None
        class_mix_items = None
        if self.model_session is not None and self.query_model is not None:
            model_prediction = self.query_model.predict([analysis_query])[0]
            class_mix_items, class_debug = _build_neural_class_mix(analysis_query, self.model_session)
            hybrid = [(item.name, item.weight, item.reason) for item in class_mix_items]
            query_types = [item.name for item in class_mix_items] or rules_only_types
        else:
            hybrid = [(name, 1.0 / max(1, len(rules_only_types)), "rules-only-console") for name in rules_only_types]
            class_debug = {"source": "rules-only-console"}
            query_types = infer_query_types(analysis_query)

        query_type = query_types[0] if query_types else "general"
        class_mix = _class_mix(hybrid)
        out_profile = _apply_effort_to_output_profile(_get_output_profile(query_types), self.options)
        query_profile = _parse_query_profile(analysis_query)

        _print_json(
            "query",
            {
                "raw": raw_query,
                "analysis_query": analysis_query,
                "provider_query": provider_query,
                "lang": lang,
                "year_hint": year_hint,
                "constraints": {
                    "include": constraints.include_domains,
                    "exclude": constraints.exclude_domains,
                    "clean": constraints.clean_query,
                },
                "rules_top": rules_top,
                "rules_only_types": rules_only_types,
                "model": (
                    {
                        "score": round(model_prediction.score, 4),
                        "top": _top_pairs(model_prediction.labels),
                    }
                    if model_prediction is not None
                    else "disabled"
                ),
                "hybrid": [
                    {"class": name, "weight": weight, "reason": reason}
                    for name, weight, reason in hybrid
                ],
                "class_debug": class_debug,
                "output_profile": {
                    "max_results": out_profile.max_results,
                    "preview_fetch_limit": out_profile.preview_fetch_limit,
                    "unparsed_bonus": out_profile.unparsed_bonus,
                    "min_score_unparsed": out_profile.min_score_unparsed,
                },
            },
        )

        if self.args.analysis_only:
            print("\n[done] analysis-only mode")
            return

        deduped, triage, effective_query = await self.service._run_with_zero_result_fallback(
            provider_query=provider_query,
            analysis_query=analysis_query,
            query_types=query_types,
            out_profile=out_profile,
            opts=self.options,
            req_id=req_id,
            class_mix=class_mix_items if self.model_session is not None else None,
            source_budget=(
                allocate_source_budget(class_mix_items, out_profile.max_results)
                if self.model_session is not None
                else None
            ),
            model_session=self.model_session,
        )
        if effective_query != analysis_query:
            print(f"\n[fallback] effective_query={effective_query!r}")
            analysis_query = effective_query
            query_profile = _parse_query_profile(analysis_query)

        if constraints.has_constraints:
            before = len(deduped)
            deduped = filter_results_by_domain_constraints(deduped, constraints)
            triage = _triage_results(deduped, analysis_query) if deduped else []
            print(f"\n[constraints] filtered {before} -> {len(deduped)}")

        if not deduped:
            print("\n[empty] no provider results")
            return

        adapted_profile, adapt_meta = _adapt_output_profile(
            deduped,
            triage,
            out_profile,
            query_types=query_types,
        )
        if adapted_profile != out_profile:
            out_profile = adapted_profile
            print("\n[profile] adapted before fetch")
            print(json.dumps(adapt_meta, indent=2, ensure_ascii=False, default=str))

        top_for_fetch = int(out_profile.preview_fetch_limit)
        to_fetch = []
        to_fetch_indices = []
        to_fetch_policies = []
        for index, (result, decision) in enumerate(zip(deduped, triage)):
            if not decision.skip and len(to_fetch) < top_for_fetch:
                to_fetch.append(result)
                to_fetch_indices.append(index)
                to_fetch_policies.append(decision.fetch_policy)

        payloads = [PreviewPayload()] * len(deduped)
        if self.options.fetch_previews and to_fetch:
            loop = asyncio.get_running_loop()
            preview_settings = get_preview_settings(apply_hardware_profile=False)
            print(f"\n[fetch] fetching {len(to_fetch)} previews policies={to_fetch_policies}")
            fetched = await _fetch_previews(
                to_fetch,
                query=analysis_query,
                concurrency=self.options.concurrency,
                fetch_timeout=self.options.fetch_timeout,
                total_timeout=self.options.total_timeout,
                preview_settings=preview_settings,
                loop=loop,
                policies=to_fetch_policies,
                early_return_threshold=(
                    0
                    if _normalize_search_effort(self.options.effort) == "high"
                    else max(0, int(self.cfg.search.early_return_threshold))
                ),
                req_id=req_id,
                deadline=None,
            )
            for index, payload in zip(to_fetch_indices, fetched):
                payloads[index] = payload

        try:
            trust_registry = get_trust_registry()
        except Exception:
            trust_registry = None

        source_predictions = {}
        if self.source_model is not None:
            source_inputs = []
            source_indexes = []
            for index, (result, payload) in enumerate(zip(deduped, payloads)):
                if index >= self.args.inspect_results:
                    break
                source_indexes.append(index)
                source_inputs.append(
                    format_source_relevance_input(
                        query=analysis_query,
                        title=result.title,
                        url=result.url,
                        snippet=result.snippet,
                        preview=payload.text,
                    )
                )
            for index, prediction in zip(source_indexes, self.source_model.predict(source_inputs), strict=True):
                source_predictions[index] = prediction

        rows = []
        for index, (result, decision, payload) in enumerate(zip(deduped, triage, payloads)):
            if index >= self.args.inspect_results:
                break
            domain_dbg = _domain_debug(result.url, class_mix)
            trust_dbg = _trust_debug(trust_registry, result.url, class_mix) if trust_registry is not None else {}
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
            domain_multiplier = float(domain_dbg["bounded_multiplier"])
            trust_affinity = float(trust_dbg.get("affinity", 1.0) or 1.0)
            adjusted_score = current_score * domain_multiplier * trust_affinity
            source_prediction = source_predictions.get(index)
            rows.append(
                {
                    "rank": index + 1,
                    "title": result.title,
                    "url": result.url,
                    "domain": _domain_from_url(result.url),
                    "engine": result.engine,
                    "published_date": result.published_date,
                    "snippet": result.snippet,
                    "trust_tier": result.trust_tier,
                    "triage": {
                        "skip": decision.skip,
                        "policy": decision.fetch_policy,
                        "score": round(decision.score, 4),
                    },
                    "preview": {
                        "chars": len(payload.text or ""),
                        "semantic_score": round(float(payload.semantic_score or 0.0), 4),
                        "quality_score": round(float(payload.quality_score or 0.0), 4),
                        "strategy": payload.strategy_used,
                    },
                    "source_model": (
                        {
                            "score": round(source_prediction.score, 4),
                            "top": _top_pairs(source_prediction.labels, limit=5),
                        }
                        if source_prediction is not None
                        else "disabled"
                    ),
                    "domain_registry": domain_dbg,
                    "trust_registry": trust_dbg,
                    "scores": {
                        "current_result_score": round(current_score, 4),
                        "domain_trust_adjusted": round(adjusted_score, 4),
                        "content_quality_signal": (
                            round(_content_quality_signal(payload, result, analysis_query), 4)
                            if payload.text
                            else 0.0
                        ),
                    },
                }
            )

        _print_json("results trace", rows)

        if self.args.show_formatted:
            top_k = _effective_output_limit(out_profile, self.options)
            formatted = _format_results(
                deduped,
                payloads,
                raw_query,
                query_profile=query_profile,
                output_profile=out_profile,
                snippet_char_budget=320 if _is_low_effort(self.options) else 600,
                preview_char_budget=320 if _is_low_effort(self.options) else 1600,
                total_char_budget=self.options.total_context_budget or self.cfg.search.total_context_budget,
                query_type=query_type,
                query_types=query_types,
                rep_store=None,
                max_results_override=min(top_k, self.options.max_results),
            )
            print("\n== formatted output ==")
            print(formatted)

        print(f"\n[done] elapsed={time.perf_counter() - started:.2f}s results={len(deduped)} inspected={len(rows)}")

    def set_option(self, key: str, value: str) -> None:
        if key in {"fetch_previews", "neural", "show_formatted", "analysis_only"}:
            parsed = value.lower() in {"1", "true", "yes", "on"}
            setattr(self.args, key, parsed)
            if key == "fetch_previews":
                self.options = replace(self.options, fetch_previews=parsed)
                self.service = WebSearchService(self.options)
            if key == "neural" and parsed and self.query_model is None:
                self._load_models()
            if key == "neural" and not parsed:
                self.close()
            print(f"[set] {key}={parsed}")
            return
        if key in {"max_results", "inspect_results", "concurrency"}:
            parsed_i = int(value)
            setattr(self.args, key, parsed_i)
            if key == "max_results":
                self.options = replace(self.options, max_results=parsed_i)
                self.service = WebSearchService(self.options)
            if key == "concurrency":
                self.options = replace(self.options, concurrency=parsed_i)
                self.service = WebSearchService(self.options)
            print(f"[set] {key}={parsed_i}")
            return
        print(f"[set] unknown option: {key}")


HELP = """Commands:
  <query>                         run search debug trace
  :set fetch_previews on|off      fetch page previews or inspect SERP only
  :set neural on|off              enable/disable ASLM embedding models
  :set show_formatted on|off      print final formatted MCP-style output
  :set analysis_only on|off       only classify/route the query
  :set max_results N              search max result count
  :set inspect_results N          detailed rows to print
  :quit                           exit
"""


async def _main_async(args: argparse.Namespace) -> int:
    if args.trace:
        _install_trace_logging()
    console = WebSearchDebugConsole(args)
    try:
        if args.once:
            await console.run_query(args.once)
            return 0

        print("ASLM web_search debug console")
        print(HELP)
        while True:
            try:
                line = input("web-search> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return 0
            if not line:
                continue
            if line in {":q", ":quit", "quit", "exit"}:
                return 0
            if line in {":h", ":help", "help"}:
                print(HELP)
                continue
            if line.startswith(":set "):
                parts = line.split(maxsplit=2)
                if len(parts) != 3:
                    print("usage: :set <option> <value>")
                    continue
                console.set_option(parts[1], parts[2])
                continue
            try:
                await console.run_query(line)
            except Exception as exc:
                print(f"[error] {type(exc).__name__}: {exc}")
    finally:
        console.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Interactive web_search debug console")
    parser.add_argument("--once", help="Run one query and exit")
    parser.add_argument("--max-results", type=int, default=10)
    parser.add_argument("--inspect-results", type=int, default=8)
    parser.add_argument("--fetch-previews", action="store_true")
    parser.add_argument("--show-formatted", action="store_true")
    parser.add_argument("--analysis-only", action="store_true")
    parser.add_argument("--no-neural", dest="neural", action="store_false")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--effort", default="medium", choices=["low", "medium", "high"])
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--fetch-timeout", type=float, default=6.0)
    parser.add_argument("--total-timeout", type=float, default=12.0)
    parser.add_argument("--candidate-pool-multiplier", type=int)
    parser.add_argument("--ddgs-hedge-count", type=int)
    parser.add_argument("--ddgs-worker-timeout", type=float)
    parser.add_argument("--ddgs-engine-timeout", type=int)
    parser.add_argument("--ddgs-max-retries", type=int)
    parser.add_argument("--no-hosted", action="store_true")
    parser.add_argument("--no-academic", action="store_true")
    parser.add_argument("--trace", action="store_true", help="Print raw trace.web_search stage logs")
    parser.set_defaults(neural=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return asyncio.run(_main_async(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
