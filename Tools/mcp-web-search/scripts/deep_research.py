# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Compatibility wrapper for the MCP monolith deep_research launcher."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.deep_research.orchestrator import run_deep_research


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="scripts/deep_research.py")
    parser.add_argument("question")
    parser.add_argument("--depth", default="standard", help="standard (default) or overdrive (higher limits, Docker sandbox).")
    parser.add_argument("--id", default="")
    parser.add_argument("--timeout", type=float, default=0.0, help="Optional hard timeout in seconds.")
    parser.add_argument("--no-yacy", action="store_true", help="Accepted for legacy compatibility.")
    return parser.parse_args()


async def _main() -> int:
    args = _parse_args()
    report = await run_deep_research(
        args.question,
        depth=args.depth,
        hard_timeout=args.timeout or None,
    )
    task_id = args.id.strip() or "research"
    out_dir = REPO_ROOT / "_out" / task_id
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "report.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"REPORT_PATH:{report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
