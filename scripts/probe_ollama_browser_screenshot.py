# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / "Tools" / "mcp-browser-agent" / "mcp-server.py"
METADATA_PATH = ROOT / "Tools" / "model_runtime_metadata.json"
SETTINGS_PATH = ROOT / "Settings" / "settings.json"


HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Browser Screenshot Vision Probe</title>
  <style>
    body {
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      font-family: Arial, sans-serif;
      background: white;
      color: black;
    }
    main {
      border: 4px solid black;
      padding: 48px;
      text-align: center;
    }
    h1 {
      font-size: 56px;
      margin: 0 0 16px;
      letter-spacing: 0;
    }
    p {
      font-size: 30px;
      margin: 0;
    }
  </style>
</head>
<body>
  <main>
    <h1>VISION_TEST_42</h1>
    <p>Browser screenshot probe</p>
  </main>
</body>
</html>
"""


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        return


def load_server_module():
    sys.path.insert(0, str(SERVER_PATH.parent))
    spec = importlib.util.spec_from_file_location("browser_mcp_server", SERVER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {SERVER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def start_http_server(root: Path) -> tuple[ThreadingHTTPServer, str]:
    handler = partial(QuietHandler, directory=str(root))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address
    return httpd, f"http://{host}:{port}/index.html"


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


def choose_vision_model(explicit: str = "") -> str:
    if explicit:
        return explicit
    metadata = read_json(METADATA_PATH)
    models = metadata.get("models", {})
    if isinstance(models, dict):
        for key, record in models.items():
            if not isinstance(record, dict):
                continue
            if not key.startswith("ollama-service:"):
                continue
            capabilities = record.get("capabilities", {})
            if isinstance(capabilities, dict) and capabilities.get("vision"):
                return str(record.get("model") or key.split(":", 1)[1])
    raise RuntimeError("No Ollama vision model found in Tools/model_runtime_metadata.json")


def post_json(url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
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


async def run_probe(model: str, base_url: str, timeout: int, keep_screenshot: bool) -> None:
    server = load_server_module()

    with tempfile.TemporaryDirectory(prefix="browser-screenshot-probe-") as temp_name:
        temp_dir = Path(temp_name)
        (temp_dir / "index.html").write_text(HTML, encoding="utf-8")
        httpd, url = start_http_server(temp_dir)
        screenshot_path: Path | None = None
        try:
            context = {
                "engine": "ollama-service",
                "model_name": model,
                "selected_tool_server_ids": ["browser_agent"],
                "project_dir": str(ROOT),
                "module_dir": str(ROOT),
            }
            await server._execute_browser_tool("browser_navigate", {"url": url}, context)
            result = await server._execute_browser_tool("browser_screenshot", {"full_page": False}, context)
            if not isinstance(result, dict) or not result.get("ok"):
                raise AssertionError(f"Expected inline screenshot envelope, got: {result!r}")

            image = result.get("result")
            if not isinstance(image, dict):
                raise AssertionError("Screenshot result missing image payload.")
            screenshot_path = Path(str(image.get("host_path") or ""))
            preview = image.get("preview")
            if not isinstance(preview, dict) or preview.get("type") != "inline_base64":
                raise AssertionError(f"Screenshot preview is not inline base64: {preview!r}")
            image_base64 = str(preview.get("data_base64") or "")
            if not image_base64:
                raise AssertionError("Screenshot inline base64 is empty.")

            payload = {
                "model": model,
                "stream": False,
                "messages": [
                    {
                        "role": "user",
                        "content": "Read the large text in the screenshot. Reply with only that exact token.",
                        "images": [image_base64],
                    }
                ],
            }
            response = post_json(f"{base_url.rstrip('/')}/api/chat", payload, timeout=timeout)
            content = str((response.get("message") or {}).get("content") or "")
            if "VISION_TEST_42" not in content:
                raise AssertionError(f"Ollama did not read the screenshot token. Response: {content!r}")

            print(f"ollama screenshot probe: PASS ({model})")
        finally:
            httpd.shutdown()
            try:
                import browser

                await browser.run_in_browser_loop(browser.state.close())
            except Exception:
                pass
            if screenshot_path and screenshot_path.exists() and not keep_screenshot:
                try:
                    screenshot_path.unlink()
                except OSError:
                    pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify browser_screenshot inline images through local Ollama.")
    parser.add_argument("--model", default="", help="Ollama vision model name. Defaults to first vision model in metadata.")
    parser.add_argument("--base-url", default=default_ollama_base_url())
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--keep-screenshot", action="store_true")
    args = parser.parse_args()

    try:
        model = choose_vision_model(args.model.strip())
        asyncio.run(run_probe(model, args.base_url, args.timeout, args.keep_screenshot))
    except Exception as exc:
        print(f"ollama screenshot probe: FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
