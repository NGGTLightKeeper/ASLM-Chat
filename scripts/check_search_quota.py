from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from API import mcp as tool_registry  # noqa: E402


def run_check(attempts: int, effort: str) -> int:
    tool_event = {
        "alias": "web_search__web_search",
        "server_id": "web_search",
        "tool_id": "web_search",
        "tool_name": "Web search",
    }
    arguments = {
        "query": "quota verification search",
        "effort": effort,
    }
    counters: dict[str, int] = {}
    blocked_at: int | None = None

    print(f"Checking web_search quota: effort={effort!r}, attempts={attempts}")
    for attempt in range(1, attempts + 1):
        error = tool_registry.consume_tool_quota(
            tool_event,
            counters,
            arguments=arguments,
        )
        if error is None:
            print(f"{attempt}: ALLOW")
            continue

        if blocked_at is None:
            blocked_at = attempt
        print(f"{attempt}: BLOCK - {error}")

    expected_block_at = 4 if effort.strip().lower() == "high" else None
    if expected_block_at is not None and blocked_at != expected_block_at:
        print(f"FAIL: expected first block at attempt {expected_block_at}, got {blocked_at}")
        return 1

    if expected_block_at is None and blocked_at is not None:
        print(f"FAIL: effort={effort!r} should not hit the high-effort quota in this check")
        return 1

    print("OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify that high-effort web_search is limited to 3 calls per assistant response."
    )
    parser.add_argument("--attempts", type=int, default=5, help="Number of simulated web_search calls.")
    parser.add_argument("--effort", default="high", help="web_search effort argument to test.")
    args = parser.parse_args()

    attempts = max(1, int(args.attempts))
    return run_check(attempts, str(args.effort))


if __name__ == "__main__":
    raise SystemExit(main())
