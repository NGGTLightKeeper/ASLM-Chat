#!/usr/bin/env python3
"""Ping every DDGS text engine with a minimal live search."""
from __future__ import annotations

import argparse
import importlib
import inspect
import json
import pkgutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import load_search_config
from core.ddgs import DDGS
from core.ddgs.base import BaseSearchEngine
from core.ddgs.engines import ENGINES
from core.ddgs.routing import PROFILES


@dataclass
class EnginePing:
    name: str
    tier: str
    enabled: bool
    status: str  # ok | empty | error | disabled | skipped
    latency_seconds: float | None
    result_count: int
    sample_url: str
    sample_title: str
    error: str


def _discover_all_engine_names() -> list[tuple[str, bool]]:
    """Return (name, enabled) for every text engine class in engines/."""
    names: dict[str, bool] = {name: True for name in ENGINES["text"]}
    package = importlib.import_module("core.ddgs.engines")
    for _finder, module_name, _is_package in pkgutil.iter_modules(package.__path__, package.__name__ + "."):
        module = importlib.import_module(module_name)
        for _, engine_class in inspect.getmembers(module, inspect.isclass):
            if not issubclass(engine_class, BaseSearchEngine) or engine_class is BaseSearchEngine:
                continue
            if engine_class.__name__.startswith("Base"):
                continue
            name = getattr(engine_class, "name", None)
            if not isinstance(name, str):
                continue
            enabled = not bool(getattr(engine_class, "disabled", False))
            names[name] = enabled
    return sorted(names.items())


def _ping_one(name: str, *, query: str, timeout: int, max_results: int) -> EnginePing:
    profile = PROFILES.get(name)
    tier = profile.tier if profile else "?"
    t0 = time.perf_counter()
    try:
        rows = DDGS(timeout=timeout).text(
            query,
            backend=name,
            max_results=max_results,
            region="us-en",
            timelimit=None,
        )
        latency = round(time.perf_counter() - t0, 3)
        if not rows:
            return EnginePing(
                name=name,
                tier=tier,
                enabled=True,
                status="empty",
                latency_seconds=latency,
                result_count=0,
                sample_url="",
                sample_title="",
                error="",
            )
        first = rows[0]
        return EnginePing(
            name=name,
            tier=tier,
            enabled=True,
            status="ok",
            latency_seconds=latency,
            result_count=len(rows),
            sample_url=str(first.get("href") or ""),
            sample_title=str(first.get("title") or "")[:120],
            error="",
        )
    except Exception as exc:
        latency = round(time.perf_counter() - t0, 3)
        return EnginePing(
            name=name,
            tier=tier,
            enabled=True,
            status="error",
            latency_seconds=latency,
            result_count=0,
            sample_url="",
            sample_title="",
            error=f"{type(exc).__name__}: {exc}",
        )


def run_ping(
    *,
    query: str,
    timeout: int,
    max_results: int,
    workers: int,
    include_disabled: bool,
) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    engines = _discover_all_engine_names()
    pings: list[EnginePing] = []

    to_run: list[str] = []
    for name, enabled in engines:
        if not enabled:
            if include_disabled:
                pings.append(
                    EnginePing(
                        name=name,
                        tier=PROFILES.get(name, None).tier if name in PROFILES else "?",
                        enabled=False,
                        status="disabled",
                        latency_seconds=None,
                        result_count=0,
                        sample_url="",
                        sample_title="",
                        error="",
                    )
                )
            continue
        to_run.append(name)

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {
            pool.submit(
                _ping_one,
                name,
                query=query,
                timeout=timeout,
                max_results=max_results,
            ): name
            for name in to_run
        }
        for future in as_completed(futures):
            pings.append(future.result())

    tier_order = {"A": 0, "specialized": 1, "B": 2, "?": 3}
    pings.sort(key=lambda item: (tier_order.get(item.tier, 9), item.name))
    ok = sum(1 for item in pings if item.status == "ok")
    empty = sum(1 for item in pings if item.status == "empty")
    errors = sum(1 for item in pings if item.status == "error")
    disabled = sum(1 for item in pings if item.status == "disabled")

    return {
        "tool": "ping_engines",
        "started_at": started.isoformat().replace("+00:00", "Z"),
        "ended_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "query": query,
        "timeout_seconds": timeout,
        "summary": {
            "total": len(pings),
            "ok": ok,
            "empty": empty,
            "error": errors,
            "disabled": disabled,
        },
        "engines": [asdict(item) for item in pings],
    }


def _print_table(report: dict[str, Any]) -> None:
    print(f"\nQuery: {report['query']!r}  timeout={report['timeout_seconds']}s")
    print(f"{'engine':<14} {'tier':<12} {'status':<8} {'lat':>6}  {'n':>3}  detail")
    print("-" * 90)
    for row in report["engines"]:
        lat = f"{row['latency_seconds']:.2f}s" if row["latency_seconds"] is not None else "  -  "
        detail = row["error"] or row["sample_url"] or row["sample_title"] or "-"
        if len(detail) > 52:
            detail = detail[:49] + "..."
        print(
            f"{row['name']:<14} {row['tier']:<12} {row['status']:<8} {lat:>6}  "
            f"{row['result_count']:>3}  {detail}"
        )
    summary = report["summary"]
    print(
        f"\nok={summary['ok']} empty={summary['empty']} "
        f"error={summary['error']} disabled={summary['disabled']}"
    )


def main() -> None:
    cfg = load_search_config()
    default_timeout = int(getattr(cfg.search, "ddgs_engine_timeout", 8))
    parser = argparse.ArgumentParser(description="Ping all DDGS text engines.")
    parser.add_argument("--query", default="python programming language")
    parser.add_argument("--timeout", type=int, default=default_timeout)
    parser.add_argument("--max-results", type=int, default=3)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--include-disabled", action="store_true", default=True)
    parser.add_argument("--out", type=Path, default=ROOT / "engines-ping.json")
    args = parser.parse_args()

    report = run_ping(
        query=args.query,
        timeout=args.timeout,
        max_results=args.max_results,
        workers=args.workers,
        include_disabled=args.include_disabled,
    )
    _print_table(report)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
