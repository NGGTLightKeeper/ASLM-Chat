# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import time
from pathlib import Path
from typing import Any

from services.web_search import (
    clear_shared_search_model_session,
    run_web_search_rich,
)


DEFAULT_QUERIES = [
    "cat behavior",
    "c++ vector erase complexity",
    "reactive oxygen species pubmed",
    "best laptop under 1000",
    "FastAPI dependency injection documentation",
]


# Compute a percentile from sorted elapsed-time samples.
def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * pct)))
    return ordered[index]


# Run one live web_search_rich call under a temporary pipeline env override.
async def _run_one(query: str, *, pipeline: str, args: argparse.Namespace) -> dict[str, Any]:
    from core.config.pipeline_modes import normalize_pipeline_mode

    pipeline = normalize_pipeline_mode(pipeline)
    old_pipeline = os.environ.get("ASLM_WEB_SEARCH_PIPELINE")
    old_keep = os.environ.get("ASLM_WEB_SEARCH_KEEP_MODELS")
    old_device = os.environ.get("ASLM_WEB_SEARCH_MODEL_DEVICE")

    # Apply benchmark overrides for this single query.
    os.environ["ASLM_WEB_SEARCH_PIPELINE"] = pipeline
    os.environ["ASLM_WEB_SEARCH_KEEP_MODELS"] = "1" if args.keep_models else "0"
    if args.device:
        os.environ["ASLM_WEB_SEARCH_MODEL_DEVICE"] = args.device
    elif old_device is not None:
        os.environ["ASLM_WEB_SEARCH_MODEL_DEVICE"] = old_device
    else:
        os.environ.pop("ASLM_WEB_SEARCH_MODEL_DEVICE", None)

    try:
        started = time.perf_counter()
        payload = await run_web_search_rich(
            query,
            max_results=args.max_results,
            effort=args.effort,
            hard_timeout=args.hard_timeout,
        )
        elapsed = time.perf_counter() - started
        sources = payload.get("sources") or []
        return {
            "query": query,
            "pipeline": pipeline,
            "elapsed_sec": round(elapsed, 3),
            "source_count": len(sources),
            "status": (payload.get("ui") or {}).get("status", "unknown"),
            "top_url": sources[0].get("url") if sources else "",
            "top_title": sources[0].get("title") if sources else "",
        }
    except Exception as exc:
        return {
            "query": query,
            "pipeline": pipeline,
            "elapsed_sec": 0.0,
            "source_count": 0,
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
        }
    finally:
        # Restore prior environment values.
        if old_pipeline is None:
            os.environ.pop("ASLM_WEB_SEARCH_PIPELINE", None)
        else:
            os.environ["ASLM_WEB_SEARCH_PIPELINE"] = old_pipeline
        if old_keep is None:
            os.environ.pop("ASLM_WEB_SEARCH_KEEP_MODELS", None)
        else:
            os.environ["ASLM_WEB_SEARCH_KEEP_MODELS"] = old_keep
        if old_device is None:
            os.environ.pop("ASLM_WEB_SEARCH_MODEL_DEVICE", None)
        else:
            os.environ["ASLM_WEB_SEARCH_MODEL_DEVICE"] = old_device


# Benchmark every query for one pipeline across repeated runs.
async def _run_pipeline(pipeline: str, queries: list[str], args: argparse.Namespace) -> list[dict[str, Any]]:
    clear_shared_search_model_session()
    rows: list[dict[str, Any]] = []
    for run_index in range(args.runs):
        for query in queries:
            print(f"[{pipeline}] run={run_index + 1}/{args.runs} query={query!r}")
            rows.append(await _run_one(query, pipeline=pipeline, args=args))
    clear_shared_search_model_session()
    return rows


# Aggregate mean/median/p90 timing stats per pipeline.
def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_pipeline: dict[str, list[float]] = {}
    for row in rows:
        if row.get("status") == "error":
            continue
        by_pipeline.setdefault(str(row["pipeline"]), []).append(float(row["elapsed_sec"]))
    return {
        pipeline: {
            "count": len(values),
            "mean_sec": round(statistics.mean(values), 3) if values else 0.0,
            "median_sec": round(statistics.median(values), 3) if values else 0.0,
            "p90_sec": round(_percentile(values, 0.90), 3) if values else 0.0,
            "min_sec": round(min(values), 3) if values else 0.0,
            "max_sec": round(max(values), 3) if values else 0.0,
        }
        for pipeline, values in sorted(by_pipeline.items())
    }


# Render a Markdown table report from benchmark rows.
def _render_markdown(rows: list[dict[str, Any]]) -> str:
    summary = _summary(rows)
    lines = [
        "# Web Search Latency Compare",
        "",
        "## Summary",
        "",
        "| Pipeline | Count | Mean | Median | P90 | Min | Max |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for pipeline, stats in summary.items():
        lines.append(
            f"| {pipeline} | {stats['count']} | {stats['mean_sec']:.3f}s | "
            f"{stats['median_sec']:.3f}s | {stats['p90_sec']:.3f}s | "
            f"{stats['min_sec']:.3f}s | {stats['max_sec']:.3f}s |"
        )
    lines.extend([
        "",
        "## Rows",
        "",
        "| Pipeline | Query | Elapsed | Sources | Status | Top |",
        "|---|---|---:|---:|---|---|",
    ])
    for row in rows:
        top = str(row.get("top_title") or row.get("error") or "").replace("|", "\\|")[:90]
        lines.append(
            f"| {row['pipeline']} | `{row['query']}` | {float(row['elapsed_sec']):.3f}s | "
            f"{row.get('source_count', 0)} | {row.get('status', '')} | {top} |"
        )
    return "\n".join(lines)


# Run all pipelines, then write JSON and Markdown reports under output_dir.
async def _main_async(args: argparse.Namespace) -> int:
    queries = args.queries or DEFAULT_QUERIES
    rows: list[dict[str, Any]] = []
    for pipeline in args.pipelines:
        rows.extend(await _run_pipeline(pipeline, queries, args))

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"web_search_latency_compare_{stamp}.json"
    md_path = out_dir / f"web_search_latency_compare_{stamp}.md"
    payload = {"summary": _summary(rows), "rows": rows}
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(_render_markdown(rows), encoding="utf-8")
    print(f"[done] json={json_path}")
    print(f"[done] markdown={md_path}")
    print(json.dumps(payload["summary"], indent=2, ensure_ascii=False))
    return 0


# Build the latency-compare CLI argument parser.
def build_parser() -> argparse.ArgumentParser:
    from core.config.pipeline_modes import PIPELINE_MODE_CHOICES

    parser = argparse.ArgumentParser(
        description="Compare rules and aslm_embedding live web_search latency"
    )
    parser.add_argument("queries", nargs="*", help="Queries to benchmark. Defaults to a small mixed set.")
    parser.add_argument(
        "--pipelines",
        nargs="+",
        default=["rules", "aslm_embedding"],
        choices=PIPELINE_MODE_CHOICES,
        help="Pipeline mode (aliases: legacy→rules, neural_v2→aslm_embedding)",
    )
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--max-results", type=int, default=3)
    parser.add_argument("--effort", default="low", choices=["low", "medium", "high"])
    parser.add_argument("--hard-timeout", type=float, default=45.0)
    parser.add_argument("--device", default="", help="Model device for aslm_embedding: cpu, cuda, or auto")
    parser.add_argument("--no-keep-models", dest="keep_models", action="store_false")
    parser.add_argument("--output-dir", default="tmp")
    parser.set_defaults(keep_models=True)
    return parser


# CLI entry: asyncio driver for latency comparison.
def main() -> int:
    return asyncio.run(_main_async(build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
