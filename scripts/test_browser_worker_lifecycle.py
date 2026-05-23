# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import os
import sys
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / "Tools" / "mcp-browser-agent" / "mcp-server.py"
BROWSER_AGENT_DIR = SERVER_PATH.parent
if str(BROWSER_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(BROWSER_AGENT_DIR))


HTML = """<!doctype html>
<html>
<head><meta charset="utf-8"><title>Browser Worker Lifecycle</title></head>
<body>
  <h1>Browser Worker Lifecycle</h1>
  <input aria-label="Lifecycle input">
</body>
</html>
"""


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        return


def start_http_server(root: Path) -> tuple[ThreadingHTTPServer, str]:
    handler = partial(QuietHandler, directory=str(root))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address
    return httpd, f"http://{host}:{port}/index.html"


def load_server_module():
    os.environ["ASLM_BROWSER_WORKER_IDLE_TIMEOUT"] = "1.5"
    os.environ.pop("ASLM_BROWSER_AGENT_INLINE", None)
    os.environ.pop("ASLM_BROWSER_AGENT_WORKER", None)
    importlib.invalidate_caches()
    sys.modules.pop("browser_process", None)

    spec = importlib.util.spec_from_file_location("browser_mcp_server_lifecycle", SERVER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {SERVER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, importlib.import_module("browser_process")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


async def wait_for_exit(process, timeout: float = 5.0) -> bool:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if process.returncode is not None:
            return True
        await asyncio.sleep(0.1)
    return process.returncode is not None


async def run_lifecycle_test() -> None:
    server, browser_process = load_server_module()
    manager = browser_process.browser_process_manager
    context = {"module_dir": str(ROOT), "project_dir": str(ROOT)}

    with tempfile.TemporaryDirectory(prefix="browser-worker-lifecycle-") as temp_name:
        temp_dir = Path(temp_name)
        (temp_dir / "index.html").write_text(HTML, encoding="utf-8")
        httpd, url = start_http_server(temp_dir)
        try:
            first = await server._execute_browser_tool("browser_navigate", {"url": url}, context)
            require(not (isinstance(first, str) and first.startswith("Error:")), "navigate failed")
            first_process = manager._process
            require(first_process is not None, "worker process was not created")
            first_pid = first_process.pid
            require(first_pid != os.getpid(), "worker did not run in a separate process")

            second = await server._execute_browser_tool("browser_snapshot", {}, context)
            require(not (isinstance(second, str) and second.startswith("Error:")), "snapshot failed")
            require(manager._process is first_process, "worker should be reused before idle timeout")
            require(first_process.returncode is None, "worker exited too early")

            require(await wait_for_exit(first_process, timeout=5.0), "worker was not killed after idle timeout")
            expired_snapshot = await server._execute_browser_tool("browser_snapshot", {}, context)
            require(
                not (isinstance(expired_snapshot, str) and expired_snapshot.startswith("Error:")),
                "snapshot after idle kill should restore the last page instead of failing",
            )
            restored_process = manager._process
            require(restored_process is not None, "restored worker process was not created")
            require(restored_process.pid != first_pid, "restored worker should be a new process")
            restored_text = expired_snapshot.get("model_context", "") if isinstance(expired_snapshot, dict) else str(expired_snapshot)
            require("Browser Worker Lifecycle" in restored_text, "restored snapshot should contain the last page")

            third = await server._execute_browser_tool("browser_navigate", {"url": url}, context)
            require(not (isinstance(third, str) and third.startswith("Error:")), "second navigate failed")
            second_process = manager._process
            require(second_process is not None, "second worker process was not created")
            require(second_process is restored_process, "navigate should reuse restored worker process")

            wait_task = asyncio.create_task(
                server._execute_browser_tool(
                    "browser_wait_for_user",
                    {"message": "Lifecycle wait probe", "timeout_seconds": 3},
                    context,
                )
            )
            await asyncio.sleep(2.0)
            wait_process = manager._process
            require(wait_process is second_process, "wait_user should keep the active worker")
            require(wait_process.returncode is None, "worker died while wait_user timer was active")

            from browser_portal import enqueue_browser_portal_event

            enqueue_browser_portal_event({"type": "finish"}, context)
            wait_result = await wait_task
            require(not (isinstance(wait_result, str) and wait_result.startswith("Error:")), "wait_user failed")
            require(await wait_for_exit(second_process, timeout=5.0), "worker did not idle-kill after wait_user finished")
        finally:
            httpd.shutdown()
            await manager.shutdown(reason="test-cleanup")


def main() -> None:
    asyncio.run(run_lifecycle_test())
    print("browser worker lifecycle: OK")


if __name__ == "__main__":
    main()
