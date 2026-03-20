# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path


# Import path setup
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
SRC_ROOT = PROJECT_ROOT / "src"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from src.llm_client import llm_client
from src.orchestrator import orchestrator
from src.search_client import search_client


# CLI argument parsing

# Parse command-line arguments for the standalone runner
def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the Deep Think runner."""

    parser = argparse.ArgumentParser(description="Deep Think tool-driven research swarm")
    parser.add_argument("query", help="Question or task to analyze")
    parser.add_argument("--mode", default="full", choices=["full", "quick"], help="Output verbosity")
    parser.add_argument(
        "--profile",
        default="balanced",
        choices=["quick", "balanced", "research"],
        help="Execution profile",
    )
    parser.add_argument("--id", default="", help="Optional task id")
    return parser.parse_args()


# CLI execution

# Run the orchestrator and print output paths
async def _run(query: str, mode: str, profile: str, task_id: str) -> int:
    """Run the Deep Think workflow and print the resulting artifact path."""

    try:
        report = await orchestrator.run(
            query=query,
            mode=mode,
            profile=profile,
            task_id=task_id or None,
        )

        print(
            orchestrator.format_report_for_llm(report, include_raw_reports=mode == "full"),
            file=sys.stderr,
        )
        print(f"REPORT_PATH:{Path(report.output_dir) / 'report.md'}", file=sys.stdout)
        return 0
    finally:
        await llm_client.close()
        await search_client.close()


# Entrypoint

# Start the async CLI runner
def main() -> None:
    """Start the standalone Deep Think CLI."""

    args = parse_args()
    raise SystemExit(asyncio.run(_run(args.query, args.mode, args.profile, args.id)))


if __name__ == "__main__":
    main()
