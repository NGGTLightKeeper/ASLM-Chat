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

from core.debug.web_search_latency_compare import (
    DEFAULT_QUERIES,
    _percentile,
    _render_markdown,
    _run_one,
)
from services.web_search import clear_shared_search_model_session


MODES: dict[str, dict[str, str]] = {
    "rules_high": {
        "pipeline": "rules",
        "encoder": "1",
        "decoder": "1",
        "label": "rules pipeline (class_profiles only, high effort)",
    },
    "neural_full": {
        "pipeline": "aslm_embedding",
        "encoder": "1",
        "decoder": "1",
        "label": "aslm_embedding high (encoder + decoder)",
    },
    "neural_encoder": {
        "pipeline": "aslm_embedding",
        "encoder": "1",
        "decoder": "0",
        "label": "aslm_embedding high (encoder only)",
    },
    "neural_decoder": {
        "pipeline": "aslm_embedding",
        "encoder": "0",
        "decoder": "1",
        "label": "aslm_embedding high (decoder only, rules classify)",
    },
}


# Aggregate timing stats grouped by ablation mode name.
def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_mode: dict[str, list[float]] = {}
    for row in rows:
        if row.get("status") == "error":
            continue
        by_mode.setdefault(str(row["mode"]), []).append(float(row["elapsed_sec"]))
    return {
        mode: {
            "count": len(values),
            "mean_sec": round(statistics.mean(values), 3) if values else 0.0,
            "median_sec": round(statistics.median(values), 3) if values else 0.0,
            "p90_sec": round(_percentile(values, 0.90), 3) if values else 0.0,
            "max_sec": round(max(values), 3) if values else 0.0,
        }
        for mode, values in sorted(by_mode.items())
    }


# Render ablation-specific Markdown (mode column instead of pipeline).
def _render_ablation_markdown(rows: list[dict[str, Any]], modes: dict[str, dict[str, str]]) -> str:
    summary = _summary(rows)
    lines = [
        "# Web Search Model Ablation",
        "",
        "## Summary",
        "",
        "| Mode | Count | Mean | Median | P90 | Max |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for mode, stats in summary.items():
        lines.append(
            f"| {mode} | {stats['count']} | {stats['mean_sec']:.3f}s | "
            f"{stats['median_sec']:.3f}s | {stats['p90_sec']:.3f}s | {stats['max_sec']:.3f}s |"
        )
    lines.extend(["", "## Mode descriptions", ""])
    for name, meta in modes.items():
        lines.append(f"- **{name}**: {meta.get('label', '')}")
    lines.extend([
        "",
        "## Rows",
        "",
        "| Mode | Query | Elapsed | Sources | Status | Top |",
        "|---|---|---:|---:|---|---|",
    ])
    for row in rows:
        top = str(row.get("top_title") or row.get("error") or "").replace("|", "\\|")[:90]
        lines.append(
            f"| {row['mode']} | `{row['query']}` | {float(row['elapsed_sec']):.3f}s | "
            f"{row.get('source_count', 0)} | {row.get('status', '')} | {top} |"
        )
    return "\n".join(lines)


# Run one ablation mode across queries with encoder/decoder env toggles.
async def _run_mode(mode: str, meta: dict[str, str], queries: list[str], args: argparse.Namespace) -> list[dict[str, Any]]:
    clear_shared_search_model_session()
    os.environ["ASLM_WEB_SEARCH_PIPELINE"] = meta["pipeline"]
    os.environ["ASLM_WEB_SEARCH_NEURAL_ENCODER"] = meta["encoder"]
    os.environ["ASLM_WEB_SEARCH_NEURAL_DECODER"] = meta["decoder"]
    args.pipelines = [meta["pipeline"]]
    rows: list[dict[str, Any]] = []
    for run_index in range(args.runs):
        for query in queries:
            print(f"[{mode}] run={run_index + 1}/{args.runs} query={query!r}")
            row = await _run_one(query, pipeline=meta["pipeline"], args=args)
            row["mode"] = mode
            rows.append(row)
    clear_shared_search_model_session()
    return rows


# Execute selected ablation modes and write JSON/Markdown reports.
async def _main_async(args: argparse.Namespace) -> int:
    queries = args.queries or DEFAULT_QUERIES
    selected = {name: MODES[name] for name in (args.modes or list(MODES)) if name in MODES}
    if not selected:
        raise SystemExit(f"No valid modes. Choose from: {', '.join(MODES)}")

    rows: list[dict[str, Any]] = []
    for mode, meta in selected.items():
        rows.extend(await _run_mode(mode, meta, queries, args))

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"web_search_model_ablation_{stamp}.json"
    md_path = out_dir / f"web_search_model_ablation_{stamp}.md"
    payload = {"summary": _summary(rows), "modes": selected, "rows": rows}
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(_render_ablation_markdown(rows, selected), encoding="utf-8")
    print(f"[done] json={json_path}")
    print(f"[done] markdown={md_path}")
    print(json.dumps(payload["summary"], indent=2, ensure_ascii=False))
    return 0


# Build the model-ablation CLI argument parser.
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ablation: rules vs encoder vs decoder vs full (high effort)")
    parser.add_argument("queries", nargs="*", help="Queries; defaults to latency_compare set")
    parser.add_argument(
        "--modes",
        nargs="+",
        choices=list(MODES),
        default=list(MODES),
        help="Ablation modes to run",
    )
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--max-results", type=int, default=4)
    parser.add_argument("--effort", default="high", choices=["low", "medium", "high"])
    parser.add_argument("--hard-timeout", type=float, default=90.0)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--no-keep-models", dest="keep_models", action="store_false")
    parser.add_argument("--output-dir", default="tmp/model_ablation")
    parser.set_defaults(keep_models=True)
    return parser


# CLI entry: asyncio driver for model ablation benchmarks.
def main() -> int:
    return asyncio.run(_main_async(build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
