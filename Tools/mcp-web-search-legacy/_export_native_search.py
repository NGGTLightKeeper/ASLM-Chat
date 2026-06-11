# One-off: lean native web_search export (medium effort).
from __future__ import annotations

import asyncio
import json
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT.parents[1]) not in sys.path:
    sys.path.insert(0, str(ROOT.parents[1]))

from core.config import load_search_config
from core.query import parse_domain_constraints
from services.web_search import (
    _apply_year_hint_policy,
    _build_effort_options,
    _effort_hard_timeout,
    _normalize_search_effort,
    _resolve_auto_timelimit,
    _stricter_timelimit,
    run_web_search_rich,
    validate_search_query,
)

QUERY = "Chromadb docs"
EFFORT = "high"
OUT = ROOT / "chromadb-docs-medium-search.json"


async def main() -> None:
    cfg = load_search_config()
    started = datetime.now(timezone.utc)
    t0 = time.perf_counter()

    constraints = parse_domain_constraints(QUERY)
    query_for_search = constraints.clean_query or QUERY
    query_for_search, year_tl = _apply_year_hint_policy(query_for_search, cfg.query)
    type_tl = (
        _resolve_auto_timelimit(query_for_search)
        if cfg.query.auto_type_timelimit_enabled
        else None
    )
    auto_timelimit = _stricter_timelimit(year_tl, type_tl)
    search_effort = _normalize_search_effort(EFFORT)
    hard_timeout = _effort_hard_timeout(search_effort, None)
    opts = _build_effort_options(
        cfg,
        effort=search_effort,
        max_results=10,
        fetch_previews=True,
        timelimit=auto_timelimit,
    )

    rich = await run_web_search_rich(QUERY, effort=EFFORT)
    elapsed = round(time.perf_counter() - t0, 3)
    ended = datetime.now(timezone.utc)

    payload = {
        "tool": "web_search",
        "request": {
            "query": QUERY,
            "effort": EFFORT,
            "shopping": False,
        },
        "timing": {
            "started_at": started.isoformat().replace("+00:00", "Z"),
            "ended_at": ended.isoformat().replace("+00:00", "Z"),
            "elapsed_seconds": elapsed,
        },
        "config": {
            "search_config": json.loads(
                (ROOT / "core" / "config" / "search_config.json").read_text(encoding="utf-8")
            ),
            "resolved": {
                "raw_query": QUERY,
                "coerced_query": query_for_search,
                "effort": search_effort,
                "shopping": False,
                "max_results": 10,
                "validation": validate_search_query(query_for_search),
                "domain_constraints": {
                    "has_constraints": constraints.has_constraints,
                    "include_domains": list(constraints.include_domains),
                    "exclude_domains": list(constraints.exclude_domains),
                    "clean_query": constraints.clean_query,
                    "raw_tokens": list(constraints.raw_tokens),
                },
                "timelimit": {
                    "year_hint": year_tl,
                    "auto_type": type_tl,
                    "resolved": auto_timelimit,
                },
                "hard_timeout_seconds": hard_timeout,
                "options": asdict(opts),
            },
        },
        "result": {
            "query": rich.get("query"),
            "search_id": rich.get("search_id"),
            "status": rich.get("ui", {}).get("status", "ok"),
            "result_count": rich.get("ui", {}).get("result_count", len(rich.get("sources", []))),
            "sources": rich.get("sources", []),
        },
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUT} ({payload['result']['result_count']} sources, timelimit={auto_timelimit})")


if __name__ == "__main__":
    asyncio.run(main())
