# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""CLI entry-point for the deep research pipeline.

Usage:
    python -m services.deep_research "question" [--depth low|medium|high|extra]
    python -m services.deep_research "question" --depth high --out report.md
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from services.deep_research.orchestrator import run_deep_research


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m services.deep_research",
        description="Run the deep research pipeline and print the report.",
    )
    parser.add_argument("question", help="Research question")
    parser.add_argument(
        "--depth",
        choices=["low", "medium", "high", "extra"],
        default="medium",
        help="Research depth (default: medium)",
    )
    parser.add_argument(
        "--out",
        metavar="FILE",
        default=None,
        help="Save the report to FILE instead of (or in addition to) stdout",
    )
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> str:
    try:
        return await run_deep_research(question=args.question, depth=args.depth)
    finally:
        # Close shared aiohttp sessions to suppress "Unclosed client session" warnings.
        try:
            from core.llm.llm_client import close_session as _close_llm_session
            await _close_llm_session()
        except Exception:
            pass
        try:
            from services.web_search import shutdown_web_search
            await shutdown_web_search()
        except Exception:
            pass


def main() -> None:
    args = _parse_args()
    report = asyncio.run(_run(args))
    print(report)
    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(report)
            print(f"\nReport saved to: {args.out}", file=sys.stderr)
        except OSError as exc:
            print(f"Failed to write report: {exc}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
