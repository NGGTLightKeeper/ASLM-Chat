# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from deep_research import run_background_swarm_probe
from src.llm_client import close_session as close_llm_session
from src.config import OUTPUT_DIR


def main() -> None:
    parser = argparse.ArgumentParser(description="Run standalone background swarm probe")
    parser.add_argument("query", help="Research question for the swarm")
    parser.add_argument("--depth", default="high", choices=["low", "medium", "high", "extra"])
    parser.add_argument("--id", default="", help="Task ID")
    parser.add_argument("--timeout", type=float, default=300.0, help="Standalone swarm timeout in seconds")
    parser.add_argument("--overdrive-multiplier", type=float, default=1.0, help="Scale selected quantity knobs")
    args = parser.parse_args()

    async def _run_with_cleanup() -> str:
        try:
            return await run_background_swarm_probe(
                question=args.query,
                depth=args.depth,
                task_id=args.id,
                timeout_sec=args.timeout,
                overdrive_multiplier=args.overdrive_multiplier,
            )
        finally:
            await close_llm_session()

    result = asyncio.run(_run_with_cleanup())
    print(result, file=sys.stderr)

    output_dir = OUTPUT_DIR / args.id if args.id else None
    if output_dir:
        report_file = output_dir / "report.md"
        if report_file.exists():
            print(f"REPORT_PATH:{report_file}", file=sys.stdout)


if __name__ == "__main__":
    main()
