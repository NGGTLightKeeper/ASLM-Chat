# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.fetch.stackexchange_fetcher import (
    fetch_stackexchange_question,
    fetch_stackexchange_question_data,
    is_stackexchange_question_url,
)


# Build the Stack Exchange probe CLI argument parser.
def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="scripts/stackexchange_probe.py",
        description="One-off Stack Exchange structured output probe.",
    )
    parser.add_argument("url", help="Stack Exchange question URL")
    parser.add_argument("--timeout", type=float, default=20.0, help="API timeout in seconds")
    parser.add_argument("--answers", type=int, default=3, help="Max answers to fetch")
    parser.add_argument("--comments", type=int, default=5, help="Max comments per post to fetch")
    parser.add_argument("--save", action="store_true", help="Save structured JSON and markdown under _out/stackexchange_probe")
    return parser.parse_args()


# Fetch structured + markdown Stack Exchange output and optionally save artifacts.
async def _main() -> int:
    args = _parse_args()

    print(f"is_stackexchange_question_url={is_stackexchange_question_url(args.url)}")
    print(f"url={args.url}")
    print(f"timeout={args.timeout}s answers={args.answers} comments={args.comments}")
    print()

    data = await fetch_stackexchange_question_data(
        args.url,
        timeout=args.timeout,
        answer_limit=args.answers,
        comment_limit=args.comments,
    )
    markdown = await fetch_stackexchange_question(
        args.url,
        timeout=args.timeout,
        answer_limit=args.answers,
    )

    print(f"ok={bool(data.get('ok'))}")
    if not data.get("ok"):
        print(f"error={data.get('error')}")
    question = data.get("question") if isinstance(data.get("question"), dict) else {}
    answers = data.get("answers") if isinstance(data.get("answers"), list) else []
    print(f"title={question.get('title', '')!r}")
    print(f"answers={len(answers)}")
    print(f"question_comments={len(question.get('comments') or []) if isinstance(question, dict) else 0}")
    print(f"quota_remaining={data.get('quota_remaining')}")
    print()

    print("MARKDOWN_PREVIEW:")
    print(markdown[:4000])
    print()

    print("JSON_PREVIEW:")
    print(json.dumps(data, ensure_ascii=False, indent=2)[:4000])
    print()

    if args.save:
        out_dir = REPO_ROOT / "_out" / "stackexchange_probe"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "result.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (out_dir / "result.md").write_text(markdown, encoding="utf-8")
        (out_dir / "result.meta.txt").write_text(
            "\n".join(
                [
                    f"url={args.url}",
                    f"ok={bool(data.get('ok'))}",
                    f"title={question.get('title', '')}",
                    f"answers={len(answers)}",
                    f"question_comments={len(question.get('comments') or []) if isinstance(question, dict) else 0}",
                    f"quota_remaining={data.get('quota_remaining')}",
                ]
            ),
            encoding="utf-8",
        )
        print(f"saved_to={out_dir}")

    return 0 if data.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
