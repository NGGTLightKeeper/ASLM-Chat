from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_mcp_server_module():
    module_path = ROOT / "mcp-server.py"
    spec = importlib.util.spec_from_file_location("mcp_web_search_mcp_server", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@dataclass
class ToolCall:
    tool_name: str
    arguments: dict[str, Any]
    source: str
    raw: str


def _parse_xml_calls(text: str) -> list[ToolCall]:
    import re

    calls: list[ToolCall] = []
    pattern = re.compile(
        r"<tool_call>\s*<function=(?P<tool>[a-zA-Z0-9_./-]+)>(?P<body>.*?)</function>\s*</tool_call>",
        re.DOTALL,
    )
    param_pattern = re.compile(
        r"<parameter=(?P<name>[a-zA-Z0-9_./-]+)>(?P<value>.*?)</parameter>",
        re.DOTALL,
    )
    for match in pattern.finditer(text):
        tool_name = match.group("tool").strip()
        body = match.group("body")
        arguments: dict[str, Any] = {}
        for param in param_pattern.finditer(body):
            name = param.group("name").strip()
            value = param.group("value").strip()
            arguments[name] = value
        calls.append(ToolCall(tool_name=tool_name, arguments=arguments, source="xml", raw=match.group(0)))
    return calls


def _try_json_decode(payload: str) -> Any | None:
    payload = payload.strip()
    if not payload:
        return None
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return None


def _extract_json_block(text: str, start: int) -> tuple[Any | None, int]:
    decoder = json.JSONDecoder()
    snippet = text[start:].lstrip()
    if not snippet:
        return None, start
    offset = len(text[start:]) - len(snippet)
    try:
        value, end = decoder.raw_decode(snippet)
        return value, start + offset + end
    except json.JSONDecodeError:
        return None, start


def _parse_panel_calls(text: str, known_tools: set[str]) -> list[ToolCall]:
    calls: list[ToolCall] = []
    lines = text.splitlines()
    cursor = 0
    while cursor < len(lines):
        line = lines[cursor].strip()
        if line not in known_tools:
            cursor += 1
            continue

        tool_name = line
        scan = cursor + 1
        arguments: dict[str, Any] | None = None

        while scan < len(lines):
            current = lines[scan]
            stripped = current.strip()
            if stripped in known_tools:
                break
            if stripped.startswith("Arguments"):
                suffix = current.split("Arguments", 1)[1].strip()
                if suffix.startswith(":"):
                    inline_payload = suffix[1:].strip()
                    if inline_payload:
                        parsed = _try_json_decode(inline_payload)
                        if isinstance(parsed, dict):
                            arguments = parsed
                            break
                block_text = "\n".join(lines[scan + 1 :])
                parsed, _ = _extract_json_block(block_text, 0)
                if isinstance(parsed, dict):
                    arguments = parsed
                    break
            scan += 1

        if arguments is not None:
            raw = "\n".join(lines[cursor:scan + 1])
            calls.append(ToolCall(tool_name=tool_name, arguments=arguments, source="panel", raw=raw))
            cursor = scan + 1
        else:
            cursor += 1
    return calls


def extract_tool_calls(text: str, known_tools: set[str]) -> list[ToolCall]:
    calls: list[ToolCall] = []
    seen: set[tuple[str, str, str]] = set()
    for call in _parse_xml_calls(text):
        key = (call.tool_name, json.dumps(call.arguments, sort_keys=True), call.source)
        if key not in seen:
            calls.append(call)
            seen.add(key)
    for call in _parse_panel_calls(text, known_tools):
        key = (call.tool_name, json.dumps(call.arguments, sort_keys=True), call.source)
        if key not in seen:
            calls.append(call)
            seen.add(key)
    return calls


async def _execute_call(module: Any, call: ToolCall, context: dict[str, Any] | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        result = await module.call_tool(call.tool_name, call.arguments, context=context)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return {
            "tool": call.tool_name,
            "status": "ok",
            "elapsed_ms": elapsed_ms,
            "arguments": call.arguments,
            "result": result,
        }
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return {
            "tool": call.tool_name,
            "status": "error",
            "elapsed_ms": elapsed_ms,
            "arguments": call.arguments,
            "error": str(exc),
        }


def _print_execution(result: dict[str, Any]) -> None:
    print(f"Tool    : {result['tool']}")
    print(f"Status  : {result['status']}")
    print(f"Elapsed : {result['elapsed_ms']}ms")
    print(f"Args    : {json.dumps(result['arguments'], ensure_ascii=False)}")
    if result["status"] == "ok":
        payload = result["result"]
        if isinstance(payload, list):
            print(f"Result count: {len(payload)}")
            for index, item in enumerate(payload, 1):
                print(f"--- [{index}] ---")
                print(item)
        else:
            print(payload)
    else:
        print(f"Error   : {result['error']}")
    print()


def _built_in_stress_scenarios() -> list[ToolCall]:
    return [
        ToolCall(
            tool_name="web_search",
            arguments={
                "query": "stress test search engine performance comparison benchmarks 2024",
                "limit": 5,
            },
            source="builtin",
            raw="",
        ),
        ToolCall(
            tool_name="web_search",
            arguments={
                "query": [
                    "python web scraping tutorial 2024",
                    "machine learning framework comparison tensorflow pytorch keras",
                    "docker kubernetes difference use cases",
                ],
                "limit": 5,
            },
            source="builtin",
            raw="",
        ),
    ]


async def run_replay(path: Path | None, *, strict: bool = False) -> int:
    module = _load_mcp_server_module()
    known_tools = {tool["id"] for tool in module.TOOLS}

    if path is None:
        text = sys.stdin.read()
    else:
        text = path.read_text(encoding="utf-8")

    calls = extract_tool_calls(text, known_tools)
    if not calls:
        print("No tool calls found in input.")
        return 1

    exit_code = 0
    for call in calls:
        if call.tool_name not in known_tools:
            print(f"Cannot find tool with name {call.tool_name}.")
            print()
            exit_code = 1
            if strict:
                return exit_code
            continue
        result = await _execute_call(module, call)
        _print_execution(result)
        if result["status"] != "ok":
            exit_code = 1
            if strict:
                return exit_code
    return exit_code


async def run_stress() -> int:
    module = _load_mcp_server_module()
    exit_code = 0
    for call in _built_in_stress_scenarios():
        result = await _execute_call(module, call)
        _print_execution(result)
        if result["status"] != "ok":
            exit_code = 1
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay and emulate MCP tool calls against mcp-web-search.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    replay_parser = subparsers.add_parser("replay", help="Replay tool calls from a transcript file or stdin.")
    replay_parser.add_argument("--file", default="", help="Transcript path. Reads stdin when omitted.")
    replay_parser.add_argument("--strict", action="store_true", help="Stop on first invalid tool or execution error.")

    subparsers.add_parser("stress-search", help="Run built-in stress web_search scenarios.")

    args = parser.parse_args()

    if args.command == "replay":
        path = Path(args.file) if args.file else None
        return asyncio.run(run_replay(path, strict=args.strict))
    if args.command == "stress-search":
        return asyncio.run(run_stress())
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
