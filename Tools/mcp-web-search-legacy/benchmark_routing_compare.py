#!/usr/bin/env python3
"""
Compare DDGS routing strategies side-by-side.

Strategies
----------
legacy (current stability)
    Sequential plan: specialist → A → B, equal per-engine quota, early stop after
    `max_attempts` successes, replan with prefer_tier=B when A fails.

tiered_ab (candidate)
    Wave 1: 1–3 A-tier engines (low/medium/high), parallel when >1, ~2 URLs each.
    Wave 2: B-tier engines sequentially until pool filled or budget exhausted.
    No prefer_tier=B replan during A wave — next A is tried instead.

Usage
-----
    python benchmark_routing_compare.py
    python benchmark_routing_compare.py --query "Chromadb docs" --effort medium
    python benchmark_routing_compare.py --out routing-benchmark.json

Diagram
-------
```mermaid
flowchart TB
    subgraph legacy["legacy (stability)"]
        L1[plan: specialist + A + B] --> L2[run engines sequentially]
        L2 --> L3{A failed?}
        L3 -->|yes| L4[replan prefer_tier=B]
        L3 -->|no| L5[equal quota per engine]
        L4 --> L2
        L5 --> L6{successful >= max_attempts?}
        L6 -->|yes| L7[stop]
        L6 -->|no| L2
    end

    subgraph tiered["tiered_ab"]
        T1[wave A: N engines by effort] --> T2[parallel A run cap=2 each]
        T2 --> T3{pool full?}
        T3 -->|no| T4[wave B: fill remainder]
        T3 -->|yes| T5[done]
        T4 --> T5
    end
```
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.ddgs import DDGS
from core.ddgs.routing import PROFILES, a_tier_engine_count
from core.query.benchmark_queries import BENCHMARK_QUERIES
from core.query.class_profiles import infer_query_types_from_rules

STRATEGIES = ("legacy", "tiered_ab")


@dataclass
class BenchCase:
    case_id: str
    query: str
    effort: str = "medium"
    query_types: list[str] = field(default_factory=list)
    expect_domains: list[str] = field(default_factory=list)
    language: str = "en"


@dataclass
class RunMetrics:
    strategy: str
    effort: str
    elapsed_seconds: float
    result_count: int
    engines_attempted: list[str]
    engines_with_results: list[str]
    engine_histogram: dict[str, int]
    tier_histogram: dict[str, int]
    top_domains: list[str]
    expect_domain_hits: dict[str, int]
    stackoverflow_count: int
    errors: list[str]
    sample_urls: list[str]


def _default_cases() -> list[BenchCase]:
    cases = [
        BenchCase(
            case_id="chromadb-docs",
            query="Chromadb docs",
            effort="medium",
            expect_domains=["docs.trychroma.com", "github.com/chroma-core/chroma"],
        ),
        BenchCase(
            case_id="python-asyncio-cancel",
            query="python asyncio Task.cancel shielded cancellation",
            effort="medium",
            expect_domains=["docs.python.org"],
        ),
    ]
    for item in BENCHMARK_QUERIES[:4]:
        cases.append(
            BenchCase(
                case_id=item["id"],
                query=item["query"],
                effort="medium",
                language=item.get("language", "en"),
                query_types=[item.get("class", "general")],
            )
        )
    return cases


def _tier_for_engine(engine_name: str) -> str:
    profile = PROFILES.get(engine_name)
    return profile.tier if profile else "unknown"


def _run_strategy(
    case: BenchCase,
    *,
    strategy: str,
    max_results: int,
    max_attempts: int,
    timeout: int,
) -> RunMetrics:
    query_types = case.query_types or infer_query_types_from_rules(case.query)
    class_weights = {name: 1.0 for name in query_types}
    t0 = time.perf_counter()
    errors: list[str] = []
    rows: list[dict[str, Any]] = []
    try:
        rows = DDGS(timeout=timeout).text(
            case.query,
            backend="auto",
            max_results=max_results,
            max_attempts=max_attempts,
            routing_profile="stability",
            routing_strategy=strategy,
            effort=case.effort,
            language=case.language,
            query_types=query_types,
            class_weights=class_weights,
            timelimit=None,
        )
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")

    elapsed = round(time.perf_counter() - t0, 3)
    engine_hist: Counter[str] = Counter()
    tier_hist: Counter[str] = Counter()
    domain_hist: Counter[str] = Counter()
    expect_hits: dict[str, int] = {domain: 0 for domain in case.expect_domains}
    stackoverflow_count = 0
    engines_attempted: set[str] = set()
    engines_with_results: set[str] = set()

    for row in rows:
        engine = str(row.get("_engine") or "unknown")
        engines_with_results.add(engine)
        for eng in row.get("_engines") or [engine]:
            engines_attempted.add(str(eng))
        engine_hist[engine] += 1
        tier_hist[_tier_for_engine(engine)] += 1
        url = str(row.get("href") or "")
        host = urlparse(url).netloc.lower()
        domain_hist[host] += 1
        if "stackoverflow.com" in host:
            stackoverflow_count += 1
        for expected in case.expect_domains:
            if expected.lower() in host or expected.lower() in url.lower():
                expect_hits[expected] += 1

    return RunMetrics(
        strategy=strategy,
        effort=case.effort,
        elapsed_seconds=elapsed,
        result_count=len(rows),
        engines_attempted=sorted(engines_attempted),
        engines_with_results=sorted(engines_with_results),
        engine_histogram=dict(engine_hist),
        tier_histogram=dict(tier_hist),
        top_domains=[host for host, _ in domain_hist.most_common(8)],
        expect_domain_hits=expect_hits,
        stackoverflow_count=stackoverflow_count,
        errors=errors,
        sample_urls=[str(row.get("href") or "") for row in rows[:5]],
    )


def _score_summary(metrics: RunMetrics) -> dict[str, float]:
    a_share = metrics.tier_histogram.get("A", 0)
    b_share = metrics.tier_histogram.get("B", 0)
    total = max(1, metrics.result_count)
    expect_total = sum(metrics.expect_domain_hits.values())
    engine_diversity = len(metrics.engines_with_results)
    return {
        "a_tier_share": round(a_share / total, 3),
        "b_tier_share": round(b_share / total, 3),
        "expect_domain_hits": expect_total,
        "engine_diversity": engine_diversity,
        "stackoverflow_penalty": metrics.stackoverflow_count,
        "latency_seconds": metrics.elapsed_seconds,
    }


def _compare_winner(legacy: RunMetrics, tiered: RunMetrics) -> str:
    legacy_score = _score_summary(legacy)
    tiered_score = _score_summary(tiered)
    tiered_wins = 0
    legacy_wins = 0
    checks = [
        ("expect_domain_hits", True),
        ("a_tier_share", True),
        ("engine_diversity", True),
        ("stackoverflow_penalty", False),
        ("latency_seconds", False),
    ]
    for key, higher_is_better in checks:
        left = tiered_score[key]
        right = legacy_score[key]
        if left == right:
            continue
        if higher_is_better:
            if left > right:
                tiered_wins += 1
            else:
                legacy_wins += 1
        elif left < right:
            tiered_wins += 1
        else:
            legacy_wins += 1
    if tiered_wins > legacy_wins:
        return "tiered_ab"
    if legacy_wins > tiered_wins:
        return "legacy"
    return "tie"


def run_benchmark(
    cases: list[BenchCase],
    *,
    max_results: int,
    max_attempts: int,
    timeout: int,
) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    report_cases: list[dict[str, Any]] = []

    for case in cases:
        runs: dict[str, Any] = {}
        metrics_by_strategy: dict[str, RunMetrics] = {}
        for strategy in STRATEGIES:
            metrics = _run_strategy(
                case,
                strategy=strategy,
                max_results=max_results,
                max_attempts=max_attempts,
                timeout=timeout,
            )
            metrics_by_strategy[strategy] = metrics
            runs[strategy] = {
                **asdict(metrics),
                "score": _score_summary(metrics),
                "a_tier_planned": a_tier_engine_count(case.effort),
            }

        legacy = metrics_by_strategy["legacy"]
        tiered = metrics_by_strategy["tiered_ab"]
        report_cases.append(
            {
                "case_id": case.case_id,
                "query": case.query,
                "effort": case.effort,
                "query_types": case.query_types or infer_query_types_from_rules(case.query),
                "expect_domains": case.expect_domains,
                "winner_heuristic": _compare_winner(legacy, tiered),
                "runs": runs,
            }
        )
        print(f"\n=== {case.case_id} (effort={case.effort}) ===")
        for strategy in STRATEGIES:
            m = metrics_by_strategy[strategy]
            s = _score_summary(m)
            print(
                f"  {strategy:10}  {m.elapsed_seconds:5.2f}s  "
                f"results={m.result_count}  engines={m.engines_with_results}  "
                f"A%={s['a_tier_share']:.0%} B%={s['b_tier_share']:.0%}  "
                f"expect_hits={s['expect_domain_hits']}  SO={m.stackoverflow_count}"
            )
            print(f"             hist={m.engine_histogram}")

    tiered_wins = sum(1 for item in report_cases if item["winner_heuristic"] == "tiered_ab")
    legacy_wins = sum(1 for item in report_cases if item["winner_heuristic"] == "legacy")
    return {
        "tool": "benchmark_routing_compare",
        "started_at": started.isoformat().replace("+00:00", "Z"),
        "ended_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "config": {
            "strategies": list(STRATEGIES),
            "max_results": max_results,
            "max_attempts": max_attempts,
            "timeout_seconds": timeout,
            "tiered_ab_a_engines": {"low": 1, "medium": 2, "high": 3},
        },
        "summary": {
            "cases": len(report_cases),
            "tiered_ab_wins": tiered_wins,
            "legacy_wins": legacy_wins,
            "ties": len(report_cases) - tiered_wins - legacy_wins,
        },
        "cases": report_cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare legacy vs tiered_ab DDGS routing.")
    parser.add_argument("--query", action="append", dest="queries", help="Extra query (repeatable).")
    parser.add_argument("--effort", default="medium", choices=("low", "medium", "high"))
    parser.add_argument("--max-results", type=int, default=10)
    parser.add_argument("--max-attempts", type=int, default=3, help="hedge_count / B-wave budget")
    parser.add_argument("--timeout", type=int, default=12)
    parser.add_argument("--out", type=Path, default=ROOT / "routing-benchmark.json")
    args = parser.parse_args()

    if args.queries:
        cases = [
            BenchCase(case_id=f"custom-{index}", query=query, effort=args.effort)
            for index, query in enumerate(args.queries, start=1)
        ]
    else:
        cases = _default_cases()

    report = run_benchmark(
        cases,
        max_results=args.max_results,
        max_attempts=args.max_attempts,
        timeout=args.timeout,
    )
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {args.out}")
    print(
        f"Summary: tiered_ab={report['summary']['tiered_ab_wins']}  "
        f"legacy={report['summary']['legacy_wins']}  "
        f"ties={report['summary']['ties']}"
    )


if __name__ == "__main__":
    main()
