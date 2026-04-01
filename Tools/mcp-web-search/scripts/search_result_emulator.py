from __future__ import annotations

import argparse
import asyncio
import importlib.util
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEPTH_PRESETS: dict[str, dict[str, Any]] = {
    "low": {
        "limit": 5,
        "profile": "speed",
        "preview_limit": 5,
        "output_chars": 900,
        "top_k": 2,
        "semantic_min_score": 0.24,
        "fetch_timeout": 4.5,
        "total_timeout": 8.0,
        "concurrency": 3,
        "rerank": "off",
    },
    "medium": {
        "limit": 10,
        "profile": "balanced",
        "preview_limit": 10,
        "output_chars": 1400,
        "top_k": 3,
        "semantic_min_score": 0.20,
        "fetch_timeout": 6.0,
        "total_timeout": 12.0,
        "concurrency": 4,
        "rerank": "soft",
    },
    "high": {
        "limit": 15,
        "profile": "quality",
        "preview_limit": 15,
        "output_chars": 1800,
        "top_k": 4,
        "semantic_min_score": 0.18,
        "fetch_timeout": 8.0,
        "total_timeout": 16.0,
        "concurrency": 4,
        "rerank": "soft",
    },
    "extra": {
        "limit": 20,
        "profile": "quality",
        "preview_limit": 20,
        "output_chars": 2200,
        "top_k": 5,
        "semantic_min_score": 0.16,
        "fetch_timeout": 10.0,
        "total_timeout": 20.0,
        "concurrency": 5,
        "rerank": "soft",
    },
}


def _load_mcp_server_module():
    module_path = ROOT / "mcp-server.py"
    spec = importlib.util.spec_from_file_location("mcp_web_search_mcp_server", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _configure_stdio() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def _parse_queries(args: argparse.Namespace) -> str | list[str]:
    queries: list[str] = []

    if args.query:
        queries.extend(q.strip() for q in args.query if q and q.strip())

    if args.queries_json:
        parsed = json.loads(args.queries_json)
        if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
            raise ValueError("--queries-json must be a JSON array of strings.")
        queries.extend(item.strip() for item in parsed if item.strip())

    if not queries:
        prompt = "Enter search query"
        if args.interactive:
            prompt += " (multiple queries: separate with ||)"
        prompt += ": "
        raw = input(prompt).strip()
        if not raw:
            raise ValueError("Empty query.")
        if "||" in raw:
            queries.extend(part.strip() for part in raw.split("||") if part.strip())
        else:
            queries.append(raw)

    if len(queries) == 1:
        return queries[0]
    return queries


def _print_plain(result: Any) -> None:
    if isinstance(result, list):
        for index, item in enumerate(result, 1):
            if index > 1:
                print()
            print(f"--- [{index}] ---")
            print(item)
        return
    print(result)


def _resolve_limit(args: argparse.Namespace) -> int:
    if args.limit and args.limit > 0:
        return args.limit
    return int(DEPTH_PRESETS[args.depth]["limit"])


def _apply_search_test_settings(depth: str, *, gliner_enabled: bool) -> dict[str, Any]:
    preset = dict(DEPTH_PRESETS[depth])
    config_mod = importlib.import_module("config")
    content_processor = importlib.import_module("content_processor")
    targets = [config_mod, getattr(content_processor, "_CONFIG_MODULE", None)]

    overrides = {
        "WEB_SEARCH_MODE": "semantic",
        "WEB_SEARCH_PREVIEW_PROFILE": preset["profile"],
        "WEB_SEARCH_PREVIEW_LIMIT": preset["preview_limit"],
        "WEB_SEARCH_PREVIEW_OUTPUT_CHARS": preset["output_chars"],
        "WEB_SEARCH_PREVIEW_TOP_K": preset["top_k"],
        "WEB_SEARCH_PREVIEW_FETCH_TIMEOUT": preset["fetch_timeout"],
        "WEB_SEARCH_PREVIEW_TOTAL_TIMEOUT": preset["total_timeout"],
        "WEB_SEARCH_PREVIEW_CONCURRENCY": preset["concurrency"],
        "WEB_SEARCH_PREVIEW_RERANK": preset["rerank"],
        "WEB_SEARCH_SEMANTIC_MIN_SCORE": preset["semantic_min_score"],
        "WEB_SEARCH_PREVIEW_ENABLE_GLINER": bool(gliner_enabled),
        "WEB_SEARCH_PREVIEW_GLINER_TIERS": ("unknown", "moderate", "hardened", "fortress"),
    }

    for target in targets:
        if target is None:
            continue
        for key, value in overrides.items():
            setattr(target, key, value)
    return overrides


async def _run_search(args: argparse.Namespace) -> int:
    if not args.show_op_log:
        os.environ["MCP_WEB_SEARCH_OP_LOG"] = "0"
    module = _load_mcp_server_module()
    active_overrides = _apply_search_test_settings(args.depth, gliner_enabled=args.gliner)
    query = _parse_queries(args)
    payload = {
        "query": query,
        "limit": _resolve_limit(args),
    }
    result = await module.call_tool("web_search", payload)

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if args.show_config:
            print(
                "Active settings: "
                f"depth={args.depth} limit={payload['limit']} "
                f"profile={active_overrides['WEB_SEARCH_PREVIEW_PROFILE']} "
                f"mode={active_overrides['WEB_SEARCH_MODE']} "
                f"gliner={str(args.gliner).lower()} "
                f"top_k={active_overrides['WEB_SEARCH_PREVIEW_TOP_K']} "
                f"semantic_min_score={active_overrides['WEB_SEARCH_SEMANTIC_MIN_SCORE']}"
            )
            print()
        _print_plain(result)
    return 0


def main() -> int:
    _configure_stdio()
    parser = argparse.ArgumentParser(
        description="Call mcp-web-search/web_search directly and print the returned results.",
    )
    parser.add_argument(
        "-q",
        "--query",
        action="append",
        help="Search query. Repeat the flag to emulate batch mode.",
    )
    parser.add_argument(
        "--queries-json",
        default="",
        help='JSON array of queries, for example: ["query one", "query two"]',
    )
    parser.add_argument(
        "-l",
        "--limit",
        type=int,
        default=0,
        help="Maximum result count per query. When omitted, a depth-specific default is used.",
    )
    parser.add_argument(
        "--depth",
        choices=tuple(DEPTH_PRESETS),
        default="medium",
        help="Test preset inspired by deep_research depth levels.",
    )
    parser.add_argument(
        "--format",
        choices=("plain", "json"),
        default="plain",
        help="Output format.",
    )
    parser.add_argument(
        "--show-op-log",
        action="store_true",
        help="Show internal mcp-web-search operation logs in stderr.",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Prompt for a query when flags are omitted. Multiple queries can be separated with ||.",
    )
    parser.add_argument(
        "--gliner",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable or disable GLiNER in preview processing. Enabled by default for tests.",
    )
    parser.add_argument(
        "--show-config",
        action="store_true",
        help="Print effective test settings before the search results.",
    )

    args = parser.parse_args()

    try:
        return asyncio.run(_run_search(args))
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
