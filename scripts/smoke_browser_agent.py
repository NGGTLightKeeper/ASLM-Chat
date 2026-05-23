# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import re
import sys
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / "Tools" / "mcp-browser-agent" / "mcp-server.py"


HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Browser Agent Smoke</title>
  <style>
    body { font-family: sans-serif; margin: 32px; }
    header, main, footer { max-width: 760px; margin: 0 auto 24px; }
    textarea { width: 100%; height: 160px; display: block; }
    #searchPanel[hidden] { display: none; }
    .CodeMirror, .ace_editor, #rich { min-height: 44px; border: 1px solid #999; padding: 8px; margin: 8px 0; white-space: pre-wrap; }
    .spacer { height: 1200px; }
  </style>
</head>
<body>
  <header>
    <button id="openSearch" type="button" aria-label="Search or jump to">Search or jump to</button>
    <div id="searchPanel" role="dialog" aria-label="Search dialog" hidden>
      <label>Search <input id="searchInput" type="search" aria-label="Search"></label>
      <button id="submitSearch" type="button">Submit search</button>
      <output id="searchResult" aria-live="polite"></output>
    </div>
  </header>
  <main>
    <h1>Browser Agent Smoke Page</h1>
    <p>This text should only appear in full snapshots.</p>
    <label for="notes">Notes</label>
    <textarea id="notes" aria-label="Notes"></textarea>
    <div id="rich" role="textbox" aria-label="Rich notes" contenteditable="true"></div>
    <div class="CodeMirror" role="textbox" aria-label="CodeMirror notes"></div>
    <div class="ace_editor" role="textbox" aria-label="Ace notes"></div>
    <button id="save" type="button">Save notes</button>
    <div class="spacer">Scroll target lives below this spacer.</div>
    <button id="bottom" type="button">Bottom button</button>
  </main>
  <footer>
    <a href="#bottom">Footer link</a>
  </footer>
  <script>
    const panel = document.getElementById('searchPanel');
    const searchInput = document.getElementById('searchInput');
    document.getElementById('openSearch').addEventListener('click', () => {
      panel.hidden = false;
      searchInput.focus();
    });
    document.getElementById('submitSearch').addEventListener('click', () => {
      document.getElementById('searchResult').textContent = 'Search query: ' + searchInput.value;
    });
    const cmRoot = document.querySelector('.CodeMirror');
    cmRoot.CodeMirror = {
      value: '',
      getValue() { return this.value; },
      setValue(value) {
        this.value = String(value);
        cmRoot.textContent = this.value;
        cmRoot.dispatchEvent(new Event('input', { bubbles: true }));
      },
      focus() { cmRoot.focus(); },
      refresh() {}
    };
    cmRoot.tabIndex = 0;
    const aceRoot = document.querySelector('.ace_editor');
    aceRoot.env = {
      editor: {
        value: '',
        getValue() { return this.value; },
        setValue(value) {
          this.value = String(value);
          aceRoot.textContent = this.value;
          aceRoot.dispatchEvent(new Event('input', { bubbles: true }));
        },
        focus() { aceRoot.focus(); }
      }
    };
    aceRoot.tabIndex = 0;
  </script>
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


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def find_ref(snapshot: str, role: str, label: str) -> str:
    pattern = rf"\[(e\d+)\]\s+{re.escape(role)}\s+{re.escape(json.dumps(label))}"
    match = re.search(pattern, snapshot)
    if not match:
        raise AssertionError(f"Could not find {role} {label!r} in snapshot.")
    return match.group(1)


def model_text(result: Any) -> str:
    if isinstance(result, dict) and isinstance(result.get("model_context"), str):
        return result["model_context"]
    return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, indent=2)


async def run_smoke(verbose: bool = False) -> None:
    server = load_server_module()

    async def call(name: str, args: dict[str, Any] | None = None) -> Any:
        result = await server._execute_browser_tool(
            name,
            args or {},
            {
                "selected_tool_server_ids": ["browser_agent"],
                "project_dir": str(ROOT),
                "module_dir": str(ROOT),
            },
        )
        if verbose:
            text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, indent=2)
            print(f"\n--- {name} {args or {}} ---\n{text[:3000]}")
        return result

    with tempfile.TemporaryDirectory(prefix="browser-agent-smoke-") as temp_name:
        temp_dir = Path(temp_name)
        (temp_dir / "index.html").write_text(HTML, encoding="utf-8")
        httpd, url = start_http_server(temp_dir)
        try:
            snapshot = await call("browser_navigate", {"url": url})
            snapshot_text = model_text(snapshot)
            require(
                isinstance(snapshot, dict)
                and isinstance(snapshot.get("ui"), dict)
                and isinstance(snapshot["ui"].get("frame"), dict),
                "navigate should include browser portal UI frame",
            )
            require(isinstance(snapshot_text, str), "navigate should return text")
            require("### Page text" not in snapshot_text, "default snapshot must not include page text")
            require("### Text inputs" in snapshot_text, "default snapshot should list text inputs")
            require("Search or jump to" in snapshot_text, "default snapshot should include header search button")

            full = await call("browser_snapshot", {"full": True})
            full_text = model_text(full)
            require(isinstance(full_text, str), "full snapshot should return text")
            require("### Page text" in full_text, "full snapshot should include page text")
            require("This text should only appear in full snapshots." in full_text, "full snapshot should expose page content")
            require("### Accessibility tree" in full_text, "full snapshot should include accessibility tree")

            search_button = find_ref(snapshot_text, "button", "Search or jump to")
            after_click = await call("browser_click", {"ref": search_button})
            after_click_text = model_text(after_click)
            search_input = find_ref(after_click_text, "searchbox", "Search")
            await call("browser_text", {"ref": search_input, "text": "ASLM Chat"})
            search_read = await call("browser_text", {"ref": search_input})
            require("ASLM Chat" in model_text(search_read), "browser_text should write and read search input")

            notes_ref = find_ref(after_click_text, "textbox", "Notes")
            await call("browser_text", {"ref": notes_ref, "text": "one\ntwo\nthree"})
            notes_read = await call("browser_text", {"ref": notes_ref})
            require("one\ntwo\nthree" in model_text(notes_read), "textarea set/read failed")

            await call("browser_text", {"ref": notes_ref, "old_text": "two", "new_text": "TWO"})
            notes_read = await call("browser_text", {"ref": notes_ref})
            require("TWO" in model_text(notes_read), "old_text replace failed")

            await call("browser_text", {"ref": notes_ref, "action": "delete", "range": "3:3"})
            notes_read = await call("browser_text", {"ref": notes_ref})
            require("three" not in model_text(notes_read), "line delete failed")

            contenteditable_ref = find_ref(after_click_text, "textbox", "Rich notes")
            await call("browser_text", {"ref": contenteditable_ref, "text": "rich\ntext"})
            rich_read = await call("browser_text", {"ref": contenteditable_ref})
            require("rich\ntext" in model_text(rich_read), "contenteditable set/read failed")

            codemirror_ref = find_ref(after_click_text, "textbox", "CodeMirror notes")
            await call("browser_text", {"ref": codemirror_ref, "text": "cm one\ncm two"})
            cm_read = await call("browser_text", {"ref": codemirror_ref})
            require("Text target: codemirror" in model_text(cm_read), "CodeMirror adapter was not selected")
            require("cm one\ncm two" in model_text(cm_read), "CodeMirror adapter failed")

            ace_ref = find_ref(after_click_text, "textbox", "Ace notes")
            await call("browser_text", {"ref": ace_ref, "text": "ace one\nace two"})
            ace_read = await call("browser_text", {"ref": ace_ref})
            require("Text target: ace" in model_text(ace_read), "Ace adapter was not selected")
            require("ace one\nace two" in model_text(ace_read), "Ace adapter failed")

            await call("browser_scroll", {"direction": "down", "amount": 900})
            screenshot = await call("browser_screenshot", {"full_page": False})
            require(isinstance(screenshot, dict) and screenshot.get("kind") == "image", "screenshot should return image metadata")
            host_path = Path(str(screenshot.get("host_path") or ""))
            require(host_path.exists(), f"screenshot file missing: {host_path}")

            print("browser-agent smoke: PASS")
        finally:
            httpd.shutdown()
            try:
                import browser_process

                await browser_process.browser_process_manager.shutdown(reason="smoke-test-cleanup")
            except Exception:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Run browser-agent smoke checks against a local test page.")
    parser.add_argument("--verbose", action="store_true", help="Print tool outputs.")
    args = parser.parse_args()

    try:
        asyncio.run(run_smoke(verbose=args.verbose))
    except Exception as exc:
        print(f"browser-agent smoke: FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
