#!/usr/bin/env python3
# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Probe academic search via web_search, then fetch each result via read_page.

Workflow
--------
1. Run the current structured web search with an academic domain constraint
2. Keep up to N results
3. For each result:
   - store the search-side url/title/preview
   - keep ``pdf_url`` when web_search exposed one
   - parse the preferred target with read_page
4. Save a JSON report under ``tmp/``

The preferred read target is:
  pdf_url if present, otherwise result.url
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.read_page import run_read_page
from services.web_search import run_web_search_structured


@dataclass
class ReadPageProbe:
    target_url: str
    content_preview: str
    ok: bool
    error: str


@dataclass
class SearchReadProbe:
    url: str
    pdf_url: str
    title: str
    preview: str
    engine: str
    read_page: ReadPageProbe


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="scripts/academic_pdf_probe.py")
    parser.add_argument("query", help="Academic search query.")
    parser.add_argument(
        "--domain",
        default="arxiv.org",
        help="Academic domain constraint for web_search. Default: arxiv.org",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum result count. Default: 10",
    )
    parser.add_argument(
        "--read-timeout",
        type=float,
        default=20.0,
        help="Timeout passed to read_page. Default: 20",
    )
    parser.add_argument(
        "--read-max-chars",
        type=int,
        default=4000,
        help="Character cap passed to read_page. Default: 4000",
    )
    return parser.parse_args()


def _trim(text: str, limit: int) -> str:
    compact = " ".join(str(text or "").split()).strip()
    return compact[:limit].rstrip() if compact else ""


def _read_probe_from_text(target_url: str, text: str) -> ReadPageProbe:
    stripped = str(text or "").strip()
    is_error = stripped.startswith("Error:")
    is_warning = stripped.startswith("Warning:")
    return ReadPageProbe(
        target_url=target_url,
        content_preview=_trim(stripped, 1200),
        ok=bool(stripped) and not is_error,
        error=stripped if (is_error or is_warning) else "",
    )


async def _main() -> int:
    args = _parse_args()

    constrained_query = f"{args.query} site:{args.domain}"
    results = await run_web_search_structured(
        constrained_query,
        max_results=max(1, int(args.limit)),
    )
    results = results[: max(1, int(args.limit))]

    payload_results: list[SearchReadProbe] = []
    for result in results:
        read_target = result.pdf_url or result.url
        read_text = await run_read_page(
            read_target,
            timeout=max(5.0, float(args.read_timeout)),
            max_chars=max(500, int(args.read_max_chars)),
        )
        payload_results.append(
            SearchReadProbe(
                url=result.url,
                pdf_url=result.pdf_url,
                title=result.title,
                preview=_trim(result.snippet, 900),
                engine=result.engine,
                read_page=_read_probe_from_text(read_target, read_text),
            )
        )

    payload = {
        "query": args.query,
        "domain": args.domain,
        "constrained_query": constrained_query,
        "limit": int(args.limit),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "result_count": len(payload_results),
        "results": [asdict(item) for item in payload_results],
    }

    out_dir = REPO_ROOT / "tmp"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_domain = args.domain.replace("/", "_").replace("\\", "_").replace(":", "_")
    out_path = out_dir / f"academic_pdf_probe_{safe_domain}_{stamp}.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Saved: {out_path}")
    print(f"Results: {len(payload_results)}")
    used_pdf = sum(1 for item in payload_results if item.pdf_url)
    read_ok = sum(1 for item in payload_results if item.read_page.ok)
    print(f"Results with PDF URL: {used_pdf}")
    print(f"read_page ok: {read_ok}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
