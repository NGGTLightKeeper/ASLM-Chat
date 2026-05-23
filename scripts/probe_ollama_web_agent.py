# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / "Tools" / "mcp-browser-agent" / "mcp-server.py"
SETTINGS_PATH = ROOT / "Settings" / "settings.json"
METADATA_PATH = ROOT / "Tools" / "model_runtime_metadata.json"


TASKS = [
    {
        "name": "wikipedia_openai",
        "prompt": (
            "Open wikipedia.org, search for OpenAI, navigate to the OpenAI article, "
            "and report the founding year visible from the page."
        ),
    },
    {
        "name": "python_events",
        "prompt": (
            "Open python.org, inspect the page, scroll if needed, and report one visible upcoming event or news item."
        ),
    },
    {
        "name": "visual_hn",
        "prompt": (
            "Open news.ycombinator.com, take a browser screenshot, inspect it visually, "
            "and report three visible story titles."
        ),
    },
]


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def default_ollama_base_url() -> str:
    settings = read_json(SETTINGS_PATH)
    port = int(settings.get("ollama-service_port") or 30002)
    return f"http://127.0.0.1:{port}"


def choose_model(explicit: str = "") -> str:
    if explicit:
        return explicit
    metadata = read_json(METADATA_PATH)
    models = metadata.get("models", {})
    if isinstance(models, dict):
        for preferred in ("gemma4:31b-cloud", "qwen3.6:35b"):
            record = models.get(f"ollama-service:{preferred}")
            if isinstance(record, dict):
                caps = record.get("capabilities", {})
                if isinstance(caps, dict) and caps.get("vision"):
                    return preferred
        for key, record in models.items():
            if not isinstance(record, dict) or not key.startswith("ollama-service:"):
                continue
            caps = record.get("capabilities", {})
            if isinstance(caps, dict) and caps.get("vision"):
                return str(record.get("model") or key.split(":", 1)[1])
    return "gemma4:31b-cloud"


def load_server_module():
    sys.path.insert(0, str(SERVER_PATH.parent))
    spec = importlib.util.spec_from_file_location("browser_mcp_server", SERVER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {SERVER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def post_json(base_url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/chat",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
    return json.loads(data)


def extract_message(response: dict[str, Any]) -> str:
    message = response.get("message")
    if isinstance(message, dict):
        return str(message.get("content") or "").strip()
    return json.dumps(response, ensure_ascii=False)


def extract_json(text: str) -> dict[str, Any]:
    cleaned = text.replace("<|im_end|>", "").strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned, flags=re.IGNORECASE)
    if match:
        cleaned = match.group(1).strip()
    else:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            cleaned = cleaned[start : end + 1]
    payload = json.loads(cleaned)
    if not isinstance(payload, dict):
        raise ValueError("response JSON is not an object")
    return payload


def tool_docs(server: Any) -> list[dict[str, Any]]:
    docs = []
    for tool in server.TOOLS:
        docs.append(
            {
                "tool": tool["id"],
                "description": tool.get("description", ""),
                "arguments": tool.get("parameters", {}).get("properties", {}),
                "required": tool.get("parameters", {}).get("required", []),
            }
        )
    return docs


def screenshot_image_payload(result: Any) -> str:
    if not isinstance(result, dict):
        return ""
    image = result.get("result") if result.get("ok") else result
    if not isinstance(image, dict):
        return ""
    preview = image.get("preview")
    if not isinstance(preview, dict) or preview.get("type") != "inline_base64":
        return ""
    return str(preview.get("data_base64") or "")


def model_text(result: Any) -> str:
    if isinstance(result, dict) and isinstance(result.get("model_context"), str):
        return result["model_context"]
    return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, indent=2)


async def run_task(
    *,
    server: Any,
    model: str,
    base_url: str,
    task: dict[str, str],
    max_steps: int,
    timeout: int,
) -> dict[str, Any]:
    docs = tool_docs(server)
    history: list[dict[str, Any]] = []
    observation = "No page is open."
    latest_image = ""
    transcript: list[dict[str, Any]] = []
    final_answer = ""

    async def call_tool(name: str, args: dict[str, Any]) -> Any:
        return await server._execute_browser_tool(
            name,
            args,
            {
                "engine": "ollama-service",
                "model_name": model,
                "selected_tool_server_ids": ["browser_agent"],
                "project_dir": str(ROOT),
                "module_dir": str(ROOT),
            },
        )

    for step in range(max_steps):
        prompt = f"""
You are a web-browsing agent controlling a real browser.
Choose exactly one next tool call or finish.

Return only JSON:
{{"tool":"browser_tool_id","arguments":{{...}}}}
or
{{"tool":"done","arguments":{{"answer":"concise final answer"}}}}

Rules:
- Use refs only from the latest observation.
- After click/key/text/scroll, use the returned snapshot refs.
- If a target is not editable, click/open it, observe, then type into the input ref.
- Use browser_screenshot when the task requires visual inspection.
- Do not ask the user unless login, CAPTCHA, 2FA, or rate-limit blocks progress.

Available tools:
{json.dumps(docs, ensure_ascii=False, indent=2)[:12000]}

Task:
{task["prompt"]}

Recent steps:
{json.dumps(history[-8:], ensure_ascii=False, indent=2)}

Latest observation:
{observation[:7000]}
""".strip()

        message: dict[str, Any] = {"role": "user", "content": prompt}
        if latest_image:
            message["images"] = [latest_image]
        response = post_json(
            base_url,
            {"model": model, "stream": False, "messages": [message], "options": {"temperature": 0}},
            timeout=timeout,
        )
        raw = extract_message(response)
        try:
            decision = extract_json(raw)
        except Exception as exc:
            transcript.append({"step": step + 1, "raw": raw, "error": f"parse: {exc}"})
            break

        name = str(decision.get("tool") or "")
        args = decision.get("arguments") if isinstance(decision.get("arguments"), dict) else {}
        row: dict[str, Any] = {"step": step + 1, "tool": name, "arguments": args}
        latest_image = ""

        if name == "done":
            final_answer = str(args.get("answer") or args.get("reason") or "")
            row["result"] = final_answer
            transcript.append(row)
            break

        valid_tools = {tool["id"] for tool in server.TOOLS}
        if name not in valid_tools:
            observation = f"Error: unknown tool {name}. Use one of: {', '.join(sorted(valid_tools))}."
            row["result"] = observation
            transcript.append(row)
            history.append(row)
            continue

        result = await call_tool(name, args)
        latest_image = screenshot_image_payload(result)
        observation = model_text(result)
        row["result_preview"] = observation[:1800]
        row["image_forwarded"] = bool(latest_image)
        transcript.append(row)
        history.append(row)

    return {"task": task["name"], "answer": final_answer, "transcript": transcript}


async def main_async(args: argparse.Namespace) -> int:
    server = load_server_module()
    model = choose_model(args.model.strip())
    base_url = args.base_url.strip() or default_ollama_base_url()

    selected_tasks = TASKS
    if args.task:
        wanted = {item.strip() for item in args.task.split(",") if item.strip()}
        selected_tasks = [task for task in TASKS if task["name"] in wanted]
        if not selected_tasks:
            raise RuntimeError(f"No matching tasks for {sorted(wanted)}")

    results = []
    try:
        for task in selected_tasks:
            result = await run_task(
                server=server,
                model=model,
                base_url=base_url,
                task=task,
                max_steps=args.max_steps,
                timeout=args.timeout,
            )
            results.append(result)
            print(f"\n== {task['name']} ==")
            print(result.get("answer") or "(no final answer)")
            for row in result["transcript"]:
                suffix = " +image" if row.get("image_forwarded") else ""
                print(f"- step {row['step']}: {row.get('tool')} {row.get('arguments', {})}{suffix}")
    finally:
        try:
            import browser

            await browser.run_in_browser_loop(browser.state.close())
        except Exception:
            pass

    if args.output:
        Path(args.output).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run real web browsing tasks through local Ollama and browser-agent.")
    parser.add_argument("--model", default="", help="Ollama model name. Defaults to a vision model from metadata.")
    parser.add_argument("--base-url", default=default_ollama_base_url())
    parser.add_argument("--task", default="", help="Comma-separated task names, or empty for all.")
    parser.add_argument("--max-steps", type=int, default=10)
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--output", default="", help="Optional JSON transcript path.")
    args = parser.parse_args()

    try:
        return asyncio.run(main_async(args))
    except Exception as exc:
        print(f"ollama web agent probe: FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
