# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


DEFAULT_BASE_URL = "http://localhost:1234"
DEFAULT_CHAT_PATH = "/api/v1/chat"


SPLIT_TOOLS = [
    {
        "name": "browser_open",
        "description": "Open a URL and return the current browser page state.",
        "parameters": {"url": "string"},
    },
    {
        "name": "browser_observe",
        "description": "Refresh and return URL, title, page preview, warnings, and interactive element refs.",
        "parameters": {"scroll": "optional: up|down", "amount": "optional integer pixels"},
    },
    {
        "name": "browser_click",
        "description": "Click one interactive element by ref from the latest observation.",
        "parameters": {"ref": "string"},
    },
    {
        "name": "browser_fill",
        "description": "Fill an input-like element by ref. Optionally submit with Enter.",
        "parameters": {"ref": "string", "text": "string", "submit": "optional boolean"},
    },
    {
        "name": "browser_press",
        "description": "Press a keyboard key such as Enter, Escape, Tab, ArrowDown.",
        "parameters": {"key": "string"},
    },
    {
        "name": "browser_scroll",
        "description": "Scroll the page up or down.",
        "parameters": {"direction": "up|down", "amount": "optional integer pixels"},
    },
    {
        "name": "browser_wait",
        "description": "Wait for navigation, page settling, visible text, or manual user action.",
        "parameters": {
            "until": "navigation|network_idle|text|element|user",
            "text": "optional string",
            "ref": "optional string",
            "message": "optional string for user waits",
            "timeout_seconds": "optional integer",
        },
    },
]


ACTION_TOOL = [
    {
        "name": "browser_open",
        "description": "Open a URL and return the current browser page state.",
        "parameters": {"url": "string"},
    },
    {
        "name": "browser_observe",
        "description": "Refresh and return URL, title, page preview, warnings, and interactive element refs.",
        "parameters": {"scroll": "optional: up|down", "amount": "optional integer pixels"},
    },
    {
        "name": "browser_action",
        "description": "Perform one browser action. Use refs from browser_observe when targeting elements.",
        "parameters": {
            "action": "click|fill|press|scroll|back|forward|reload|wait",
            "ref": "optional string",
            "text": "optional string for fill or wait text",
            "submit": "optional boolean for fill",
            "key": "optional string for press",
            "direction": "optional up|down for scroll",
            "amount": "optional integer pixels for scroll",
            "until": "optional navigation|network_idle|text|element|user for wait",
            "message": "optional string for user waits",
            "timeout_seconds": "optional integer",
        },
    },
]


SCENARIOS = [
    {
        "name": "open_url",
        "task": "Open https://github.com and inspect the page.",
        "state": "No page is open yet.",
        "expect": {"tool": "browser_open", "required": {"url": "https://github.com"}},
    },
    {
        "name": "fill_search",
        "task": "Search this page for ASLM Chat and submit the search.",
        "state": (
            "Current page:\n"
            "URL: https://github.com\n"
            "Title: GitHub\n"
            "Interactive elements:\n"
            "- [e0] link \"Skip to content\"\n"
            "- [e1] button \"Search or jump to...\"\n"
            "- [e2] textbox \"Search GitHub\"\n"
            "- [e3] link \"Sign in\"\n"
            "- [e4] link \"Sign up\""
        ),
        "expect": {"tool_any": ["browser_fill", "browser_action"], "required": {"ref": "e2", "text": "ASLM Chat"}},
    },
    {
        "name": "click_result",
        "task": "Open the ASLM-Chat repository result.",
        "state": (
            "Current page:\n"
            "URL: https://github.com/search?q=ASLM+Chat&type=repositories\n"
            "Title: Repository search results\n"
            "Interactive elements:\n"
            "- [e8] link \"NGGTLightKeeper/ASLM-Chat\"\n"
            "- [e9] link \"dimap/ASLM-Chat-fork\"\n"
            "- [e10] button \"Sort: Best match\""
        ),
        "expect": {"tool_any": ["browser_click", "browser_action"], "required": {"ref": "e8"}},
    },
    {
        "name": "dismiss_overlay",
        "task": "A cookie popup is blocking the page. Close or accept it, then observe the page again.",
        "state": (
            "Current page:\n"
            "URL: https://example-shop.test\n"
            "Warnings: OVERLAY cookie banner detected.\n"
            "Interactive elements:\n"
            "- [e2] button \"Accept all\"\n"
            "- [e3] button \"Reject\"\n"
            "- [e4] link \"Privacy policy\""
        ),
        "expect": {"tool_any": ["browser_click", "browser_action"], "required": {"ref": "e2"}},
    },
    {
        "name": "manual_login",
        "task": "The site requires login with private credentials. Ask the user to finish login manually.",
        "state": (
            "Current page:\n"
            "URL: https://bank.example/login\n"
            "Warnings: Login form detected.\n"
            "Interactive elements:\n"
            "- [e1] textbox \"Username\"\n"
            "- [e2] textbox \"Password\"\n"
            "- [e3] button \"Log in\""
        ),
        "expect": {"tool_any": ["browser_wait", "browser_action"], "required": {"until": "user"}},
    },
]


@dataclass
class ProbeResult:
    style: str
    scenario: str
    ok: bool
    elapsed_seconds: float
    response_text: str
    parsed: Any
    notes: list[str]


def request_json(method: str, url: str, payload: dict[str, Any] | None = None, timeout: int = 60) -> Any:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
    return json.loads(body)


def choose_loaded_model(base_url: str) -> str:
    models_payload = request_json("GET", f"{base_url.rstrip('/')}/api/v1/models", timeout=10)
    models = models_payload.get("models") if isinstance(models_payload, dict) else []
    for model in models or []:
        if not isinstance(model, dict):
            continue
        loaded = model.get("loaded_instances")
        if isinstance(loaded, list) and loaded:
            return str(model.get("key") or loaded[0].get("id") or "").strip()
    raise RuntimeError("No loaded LM Studio LLM model found.")


def chat(base_url: str, chat_path: str, model: str, prompt: str, timeout: int) -> str:
    payload = {
        "model": model,
        "input": prompt,
    }
    response = request_json("POST", f"{base_url.rstrip('/')}{chat_path}", payload, timeout=timeout)
    output = response.get("output") if isinstance(response, dict) else None
    if isinstance(output, list):
        parts = [
            str(item.get("content") or "")
            for item in output
            if isinstance(item, dict) and item.get("type") == "message"
        ]
        if parts:
            return "\n".join(parts).strip()
    if isinstance(response, dict) and isinstance(response.get("content"), str):
        return str(response["content"]).strip()
    return json.dumps(response, ensure_ascii=False, indent=2)


def extract_json(text: str) -> Any:
    cleaned = StringCleaner.clean(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned, flags=re.IGNORECASE)
    if match:
        return json.loads(match.group(1).strip())

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end > start:
        return json.loads(cleaned[start : end + 1])
    raise ValueError("No JSON object found in response.")


class StringCleaner:
    @staticmethod
    def clean(value: str) -> str:
        text = str(value or "").strip()
        return text.replace("<|im_end|>", "").strip()


def build_prompt(style: str, tools: list[dict[str, Any]], scenario: dict[str, Any]) -> str:
    return f"""
You are testing a browser automation tool API. Choose the next tool call only.

Available tools:
{json.dumps(tools, ensure_ascii=False, indent=2)}

Rules:
- Return exactly one JSON object and no prose.
- Shape: {{"tool": "tool_name", "arguments": {{...}}}}
- Use refs exactly as shown in the page state.
- If no page is open and the task names a URL, open it.
- If private credentials, CAPTCHA, or 2FA are needed, wait for the user instead of typing secrets.
- Do not invent refs or URLs.

Task:
{scenario["task"]}

Page state:
{scenario["state"]}
""".strip()


def validate(style: str, parsed: Any, scenario: dict[str, Any]) -> tuple[bool, list[str]]:
    notes: list[str] = []
    if not isinstance(parsed, dict):
        return False, ["response is not an object"]
    tool = str(parsed.get("tool") or "").strip()
    args = parsed.get("arguments")
    if not isinstance(args, dict):
        return False, ["arguments is not an object"]

    expect = scenario["expect"]
    expected_tool = expect.get("tool")
    expected_any = expect.get("tool_any")
    if expected_tool and tool != expected_tool:
        notes.append(f"expected tool {expected_tool}, got {tool}")
    if expected_any and tool not in expected_any:
        notes.append(f"expected one of {expected_any}, got {tool}")

    if style == "action" and tool == "browser_action":
        action = str(args.get("action") or "").strip()
        if scenario["name"] in {"fill_search"} and action != "fill":
            notes.append(f"expected action fill, got {action}")
        if scenario["name"] in {"click_result", "dismiss_overlay"} and action != "click":
            notes.append(f"expected action click, got {action}")
        if scenario["name"] == "manual_login" and action != "wait":
            notes.append(f"expected action wait, got {action}")

    for key, expected_value in (expect.get("required") or {}).items():
        actual = args.get(key)
        if key == "text":
            if str(expected_value).lower() not in str(actual or "").lower():
                notes.append(f"expected text containing {expected_value!r}, got {actual!r}")
        elif actual != expected_value:
            notes.append(f"expected {key}={expected_value!r}, got {actual!r}")

    return len(notes) == 0, notes


def run_probe(base_url: str, chat_path: str, model: str, timeout: int) -> list[ProbeResult]:
    results: list[ProbeResult] = []
    styles = {
        "split": SPLIT_TOOLS,
        "action": ACTION_TOOL,
    }
    for style, tools in styles.items():
        for scenario in SCENARIOS:
            prompt = build_prompt(style, tools, scenario)
            started = time.perf_counter()
            try:
                response_text = chat(base_url, chat_path, model, prompt, timeout)
                parsed = extract_json(response_text)
                ok, notes = validate(style, parsed, scenario)
            except Exception as exc:
                response_text = f"{type(exc).__name__}: {exc}"
                parsed = None
                ok = False
                notes = [str(exc)]
            results.append(
                ProbeResult(
                    style=style,
                    scenario=str(scenario["name"]),
                    ok=ok,
                    elapsed_seconds=time.perf_counter() - started,
                    response_text=response_text,
                    parsed=parsed,
                    notes=notes,
                )
            )
    return results


def print_report(results: list[ProbeResult]) -> None:
    by_style: dict[str, list[ProbeResult]] = {}
    for result in results:
        by_style.setdefault(result.style, []).append(result)

    for style, items in by_style.items():
        passed = sum(1 for item in items if item.ok)
        print(f"\n== {style} tools: {passed}/{len(items)} passed ==")
        for item in items:
            mark = "PASS" if item.ok else "FAIL"
            print(f"[{mark}] {item.scenario} ({item.elapsed_seconds:.1f}s)")
            if item.parsed is not None:
                print(json.dumps(item.parsed, ensure_ascii=False))
            else:
                print(item.response_text[:500])
            if item.notes:
                print("notes:", "; ".join(item.notes))


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe browser tool API style against local LM Studio.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--chat-path", default=DEFAULT_CHAT_PATH)
    parser.add_argument("--model", default="")
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args()

    model = args.model.strip() or choose_loaded_model(args.base_url)
    print(f"Using model: {model}")
    print(f"Endpoint: {args.base_url.rstrip('/')}{args.chat_path}")

    results = run_probe(args.base_url, args.chat_path, model, args.timeout)
    print_report(results)

    failed = [result for result in results if not result.ok]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
