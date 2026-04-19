# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""CLI entry point for agentic deep research."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from services.deep_research.orchestrator import run_deep_research


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m services.deep_research")
    parser.add_argument("question")
    parser.add_argument("--depth", default="standard", help="standard (default) or overdrive (higher limits, Docker sandbox).")
    parser.add_argument("--out", default="")
    return parser.parse_args()


async def _main() -> str:
    args = _parse_args()
    report = await run_deep_research(args.question, depth=args.depth)
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
    return report


if __name__ == "__main__":
    print(asyncio.run(_main()))
