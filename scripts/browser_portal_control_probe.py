# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import sys
import threading
import time
from urllib.parse import quote
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BROWSER_AGENT_DIR = ROOT / "Tools" / "mcp-browser-agent"
if str(BROWSER_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(BROWSER_AGENT_DIR))


TARGET_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Portal Control Target</title>
  <style>
    body { margin: 0; font: 18px/1.4 system-ui, sans-serif; background: #f7f7f8; color: #111; }
    main { max-width: 860px; margin: 0 auto; padding: 72px 28px 120px; }
    h1 { font-size: 48px; margin: 0 0 18px; }
    .search { display: flex; gap: 10px; margin: 28px 0; }
    input { flex: 1; font: inherit; padding: 16px 18px; border: 1px solid #bbb; border-radius: 999px; }
    button { font: inherit; padding: 14px 18px; border: 0; border-radius: 12px; background: #0a84ff; color: white; cursor: pointer; }
    output { display: block; min-height: 32px; margin-top: 12px; font-weight: 700; }
    .cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-top: 36px; }
    .card { min-height: 120px; padding: 18px; border-radius: 16px; background: white; box-shadow: 0 10px 28px rgba(0,0,0,.08); }
    .spacer { height: 760px; display: grid; place-items: center; color: #666; }
  </style>
</head>
<body>
  <main>
    <h1>Portal Control Target</h1>
    <p>This local page exists only to test whether portal clicks, typing, paste, and scroll reach the backend browser.</p>
    <div class="search">
      <input id="query" aria-label="Test input" placeholder="Type here through the portal">
      <button id="apply" type="button">Apply</button>
    </div>
    <output id="result">No input yet.</output>
    <section class="cards">
      <button class="card" type="button">Card A</button>
      <button class="card" type="button">Card B</button>
      <button class="card" type="button">Card C</button>
    </section>
    <div class="spacer">Scroll through this area</div>
    <button id="bottom" type="button">Bottom button</button>
  </main>
  <script>
    const query = document.getElementById('query');
    const result = document.getElementById('result');
    document.getElementById('apply').addEventListener('click', () => {
      result.textContent = 'Applied: ' + query.value;
    });
    document.querySelectorAll('.card, #bottom').forEach((button) => {
      button.addEventListener('click', () => {
        result.textContent = 'Clicked: ' + button.textContent.trim();
      });
    });
  </script>
</body>
</html>"""

DEFAULT_TARGET_URL = "data:text/html;charset=utf-8," + quote(TARGET_HTML)


HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Live Browser Portal Control Probe</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #111113;
      --surface: #1c1c1e;
      --surface-2: #242426;
      --text: #fff;
      --muted: rgba(235, 235, 245, .58);
      --line: rgba(255, 255, 255, .11);
      --green: #30d158;
      --yellow: #ffd166;
      --red: #ff5a67;
      --blue: #0a84ff;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      background: radial-gradient(circle at 50% 0%, rgba(10, 132, 255, .08), transparent 34%), var(--bg);
      color: var(--text);
      font: 14px/1.4 Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }

    .stage {
      width: min(1120px, calc(100vw - 28px));
      display: grid;
      gap: 14px;
    }

    .portal {
      --wait-progress: 1;
      position: relative;
      overflow: hidden;
      border-radius: 14px;
      background: linear-gradient(180deg, rgba(255, 255, 255, .045), rgba(255, 255, 255, .014)), var(--surface);
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, .04), 0 24px 70px rgba(0, 0, 0, .34);
    }

    .portal.waiting::before {
      content: "";
      position: absolute;
      inset: 0;
      z-index: 5;
      padding: 2px;
      border-radius: inherit;
      background: conic-gradient(from -90deg, var(--blue) calc(var(--wait-progress) * 1turn), rgba(10, 132, 255, .14) 0);
      mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
      mask-composite: exclude;
      pointer-events: none;
      filter: drop-shadow(0 0 14px rgba(10, 132, 255, .28));
    }

    .request {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
      padding: 10px 12px;
      border-bottom: 1px solid rgba(255, 255, 255, .065);
      background: rgba(10, 132, 255, .09);
    }

    .request-main { min-width: 0; display: grid; gap: 2px; }
    .request-label { color: rgba(255, 255, 255, .55); font-size: 11px; text-transform: uppercase; letter-spacing: .04em; }
    .request-text { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: rgba(255, 255, 255, .92); font-weight: 650; }
    .timer { flex: 0 0 auto; min-width: 50px; text-align: right; color: rgba(255, 255, 255, .72); font-variant-numeric: tabular-nums; }

    .strip {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      min-height: 38px;
      padding: 8px 12px;
      color: var(--muted);
      background: rgba(255, 255, 255, .018);
    }

    .action, .status, .controls { display: flex; align-items: center; gap: 8px; min-width: 0; }
    .title { color: var(--text); font-weight: 650; white-space: nowrap; }
    .detail { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }

    .dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--yellow);
      box-shadow: 0 0 0 3px rgba(255, 209, 102, .14);
    }

    .dot.live { background: var(--green); box-shadow: 0 0 0 3px rgba(48, 209, 88, .15); }
    .dot.error { background: var(--red); box-shadow: 0 0 0 3px rgba(255, 90, 103, .14); }
    .dot.done { background: rgba(235, 235, 245, .32); box-shadow: 0 0 0 3px rgba(235, 235, 245, .08); }

    .viewport {
      position: relative;
      aspect-ratio: 16 / 9;
      min-height: 260px;
      overflow: hidden;
      background: #171719;
      outline: none;
      cursor: crosshair;
      touch-action: none;
    }

    .viewport:focus-visible { box-shadow: inset 0 0 0 2px rgba(10, 132, 255, .72); }
    .frame { width: 100%; height: 100%; display: block; object-fit: cover; user-select: none; pointer-events: none; }

    .waiting-overlay {
      position: absolute;
      inset: auto 12px 12px auto;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 7px 10px;
      border-radius: 999px;
      color: rgba(255, 255, 255, .88);
      background: rgba(0, 0, 0, .45);
      backdrop-filter: blur(12px);
      font-size: 12px;
      pointer-events: none;
    }

    .click-ring {
      position: absolute;
      width: 30px;
      height: 30px;
      margin: -15px 0 0 -15px;
      border: 2px solid var(--blue);
      border-radius: 50%;
      pointer-events: none;
      animation: ring .42s ease-out forwards;
    }

    .type-toast {
      position: absolute;
      left: 50%;
      top: 50%;
      transform: translate(-50%, -50%);
      max-width: min(520px, calc(100% - 32px));
      padding: 8px 12px;
      border-radius: 999px;
      background: rgba(0, 0, 0, .5);
      color: rgba(255, 255, 255, .9);
      backdrop-filter: blur(12px);
      font-size: 13px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      pointer-events: none;
    }

    .url {
      padding: 8px 12px 10px;
      border-top: 1px solid rgba(255, 255, 255, .045);
      color: var(--muted);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .panel { display: grid; grid-template-columns: 1fr auto; gap: 12px; align-items: start; }
    .log {
      min-height: 84px;
      max-height: 160px;
      overflow: auto;
      padding: 10px 12px;
      border: 1px solid var(--line);
      border-radius: 12px;
      background: rgba(255, 255, 255, .035);
      color: var(--muted);
      font: 12px/1.45 ui-monospace, SFMono-Regular, Consolas, monospace;
    }

    button {
      appearance: none;
      border: 1px solid var(--line);
      border-radius: 9px;
      padding: 8px 10px;
      background: var(--surface-2);
      color: var(--text);
      font: inherit;
      cursor: pointer;
    }

    button:hover { border-color: rgba(255, 255, 255, .2); background: rgba(255, 255, 255, .075); }

    @keyframes ring {
      from { opacity: 1; transform: scale(.65); }
      to { opacity: 0; transform: scale(1.8); }
    }
  </style>
</head>
<body>
  <main class="stage">
    <section class="portal waiting" id="portal" aria-label="Live browser portal probe">
      <div class="request">
        <div class="request-main">
          <div class="request-label">Manual action requested</div>
          <div class="request-text">This probe sends your portal actions to a real headless browser page.</div>
        </div>
        <div class="timer" id="timerText">120s</div>
      </div>
      <div class="strip">
        <div class="action">
          <span class="title" id="actionTitle">portal ready</span>
          <span class="detail" id="pageUrl">loading...</span>
        </div>
        <div class="status">
          <span class="dot" id="statusDot" aria-hidden="true"></span>
          <span id="statusText">Starting</span>
          <span class="detail" id="latencyText">0 ms</span>
        </div>
      </div>
      <div class="viewport" id="viewport" tabindex="0" aria-label="Interactive browser frame">
        <img class="frame" id="frame" alt="Browser frame" draggable="false">
        <div class="waiting-overlay" id="overlay">Click, type, paste, or scroll here</div>
      </div>
      <div class="url" id="urlLine">loading...</div>
    </section>
    <section class="panel">
      <div class="log" id="log"></div>
      <div class="controls">
        <button type="button" id="reload">Reload frame</button>
        <button type="button" id="finish">Finish wait</button>
        <button type="button" id="clear">Clear log</button>
      </div>
    </section>
  </main>
  <script>
    const portal = document.getElementById('portal');
    const viewport = document.getElementById('viewport');
    const frame = document.getElementById('frame');
    const logEl = document.getElementById('log');
    const statusDot = document.getElementById('statusDot');
    const statusText = document.getElementById('statusText');
    const latencyText = document.getElementById('latencyText');
    const actionTitle = document.getElementById('actionTitle');
    const pageUrl = document.getElementById('pageUrl');
    const urlLine = document.getElementById('urlLine');
    const timerText = document.getElementById('timerText');
    const overlay = document.getElementById('overlay');
    let controlled = true;
    let waitDurationMs = 120000;
    let waitStartedAt = performance.now();
    let framePollInFlight = false;
    let eventInFlight = false;
    let framePollTimer = 0;
    const framePollIntervalMs = 140;

    function appendLog(message) {
      const line = document.createElement('div');
      line.textContent = `${new Date().toLocaleTimeString('en-GB')} ${message}`;
      logEl.appendChild(line);
      logEl.scrollTop = logEl.scrollHeight;
    }

    function setStatus(kind, text) {
      statusDot.className = `dot ${kind || ''}`.trim();
      statusText.textContent = text;
    }

    function addRing(x, y) {
      const ring = document.createElement('div');
      ring.className = 'click-ring';
      ring.style.left = `${x}px`;
      ring.style.top = `${y}px`;
      viewport.appendChild(ring);
      ring.addEventListener('animationend', () => ring.remove());
    }

    function flashToast(text) {
      const previous = viewport.querySelector('.type-toast');
      if (previous) previous.remove();
      const toast = document.createElement('div');
      toast.className = 'type-toast';
      toast.textContent = text;
      viewport.appendChild(toast);
      window.setTimeout(() => toast.remove(), 650);
    }

    function applyFrame(payload) {
      if (payload.frame) frame.src = payload.frame;
      if (payload.url) {
        pageUrl.textContent = payload.url;
        urlLine.textContent = payload.url;
      }
      if (typeof payload.latency_ms === 'number') latencyText.textContent = `${payload.latency_ms} ms`;
    }

    async function postEvent(type, payload) {
      if (!controlled) return;
      const started = performance.now();
      eventInFlight = true;
      setStatus('', 'Sending event');
      actionTitle.textContent = `portal ${type}`;
      try {
        const response = await fetch('/event', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ type, ...payload })
        });
        const data = await response.json();
        if (!response.ok || !data.ok) throw new Error(data.error || response.statusText);
        applyFrame(data);
        setStatus('', 'Manual control');
        appendLog(`${type} ${JSON.stringify(payload)} -> ${Math.round(performance.now() - started)}ms`);
      } catch (error) {
        setStatus('error', 'Backend error');
        appendLog(`${type} failed: ${error.message || error}`);
      } finally {
        eventInFlight = false;
      }
    }

    async function reloadFrame(options = {}) {
      if (framePollInFlight) return;
      framePollInFlight = true;
      if (!options.silent) setStatus('', 'Loading frame');
      try {
        const response = await fetch('/frame');
        const data = await response.json();
        applyFrame(data);
        if (!eventInFlight) setStatus('', 'Manual control');
        if (!options.silent) appendLog('frame reloaded');
      } finally {
        framePollInFlight = false;
      }
    }

    function startFramePolling() {
      window.clearTimeout(framePollTimer);
      async function poll() {
        if (!controlled) return;
        if (!eventInFlight) {
          try {
            await reloadFrame({ silent: true });
          } catch (error) {
            setStatus('error', 'Frame polling error');
            appendLog(`frame poll failed: ${error.message || error}`);
          }
        }
        framePollTimer = window.setTimeout(poll, framePollIntervalMs);
      }
      framePollTimer = window.setTimeout(poll, framePollIntervalMs);
    }

    viewport.addEventListener('pointerdown', event => {
      if (!controlled) return;
      viewport.focus();
      const rect = viewport.getBoundingClientRect();
      const x = Math.round(event.clientX - rect.left);
      const y = Math.round(event.clientY - rect.top);
      addRing(x, y);
      postEvent('click', {
        x,
        y,
        viewport_width: Math.round(rect.width),
        viewport_height: Math.round(rect.height)
      });
    });

    viewport.addEventListener('wheel', event => {
      if (!controlled) return;
      event.preventDefault();
      postEvent('scroll', { delta_x: Math.round(event.deltaX), delta_y: Math.round(event.deltaY) });
    }, { passive: false });

    viewport.addEventListener('keydown', event => {
      if (!controlled) return;
      if (event.ctrlKey || event.metaKey || event.altKey) return;
      event.preventDefault();
      flashToast(event.key.length === 1 ? event.key : event.key);
      postEvent('key', { key: event.key });
    });

    viewport.addEventListener('paste', event => {
      if (!controlled) return;
      event.preventDefault();
      const text = event.clipboardData.getData('text/plain') || '';
      flashToast(text);
      postEvent('type', { text });
    });

    document.getElementById('reload').addEventListener('click', reloadFrame);
    document.getElementById('clear').addEventListener('click', () => { logEl.textContent = ''; latencyText.textContent = '0 ms'; });
    document.getElementById('finish').addEventListener('click', () => {
      controlled = false;
      window.clearTimeout(framePollTimer);
      portal.classList.remove('waiting');
      portal.style.setProperty('--wait-progress', '0');
      timerText.textContent = 'done';
      overlay.textContent = 'Manual control finished';
      setStatus('done', 'Finished');
      appendLog('finish_wait');
    });

    function tickTimer() {
      if (!controlled) return;
      const remaining = Math.max(0, waitDurationMs - (performance.now() - waitStartedAt));
      const progress = remaining / waitDurationMs;
      portal.style.setProperty('--wait-progress', progress.toFixed(4));
      timerText.textContent = `${Math.ceil(remaining / 1000)}s`;
      if (remaining > 0) requestAnimationFrame(tickTimer);
    }

    reloadFrame().then(() => {
      viewport.focus();
      startFramePolling();
      requestAnimationFrame(tickTimer);
    });
  </script>
</body>
</html>
"""


class BrowserPortalProbe:
    def __init__(self, url: str):
        self.url = url
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        self._ready = threading.Event()
        self._frame_version = 0
        self._last_frame = ""
        self._last_url = ""
        self._run(self._ensure_open())

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def _run(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout=60)

    async def _ensure_open(self) -> None:
        import browser

        async def open_page() -> None:
            await browser.state.ensure_open()
            await browser.state.page.goto(self.url, wait_until="domcontentloaded", timeout=30000)
            await browser.state.page.wait_for_timeout(1200)

        await browser.run_in_browser_loop(open_page())
        await self.capture_frame()

    async def capture_frame(self) -> dict[str, Any]:
        import browser

        async def capture() -> dict[str, Any]:
            page = browser.state.page
            data = await page.screenshot(type="jpeg", quality=62, full_page=False)
            self._frame_version += 1
            self._last_frame = "data:image/jpeg;base64," + base64.b64encode(data).decode("utf-8")
            self._last_url = page.url
            return {
                "ok": True,
                "frame": self._last_frame,
                "url": self._last_url,
                "version": self._frame_version,
            }

        return await browser.run_in_browser_loop(capture())

    async def apply_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        import browser

        started = time.perf_counter()

        async def apply() -> None:
            page = browser.state.page
            event_type = str(payload.get("type") or "")
            if event_type == "click":
                viewport = page.viewport_size or {"width": 1280, "height": 800}
                view_w = max(1, int(payload.get("viewport_width") or viewport.get("width") or 1280))
                view_h = max(1, int(payload.get("viewport_height") or viewport.get("height") or 800))
                browser_w = int(viewport.get("width") or 1280)
                browser_h = int(viewport.get("height") or 800)
                x = float(payload.get("x") or 0) * browser_w / view_w
                y = float(payload.get("y") or 0) * browser_h / view_h
                await page.mouse.click(x, y)
                await page.wait_for_timeout(220)
                return
            if event_type == "scroll":
                await page.mouse.wheel(float(payload.get("delta_x") or 0), float(payload.get("delta_y") or 0))
                await page.wait_for_timeout(120)
                return
            if event_type == "key":
                key = str(payload.get("key") or "")
                if key:
                    await page.keyboard.press(key)
                await page.wait_for_timeout(120)
                return
            if event_type == "type":
                text = str(payload.get("text") or "")
                if text:
                    await page.keyboard.type(text, delay=8)
                await page.wait_for_timeout(120)
                return
            raise ValueError(f"Unsupported event type: {event_type}")

        await browser.run_in_browser_loop(apply())
        result = await self.capture_frame()
        result["latency_ms"] = round((time.perf_counter() - started) * 1000)
        return result


class Handler(BaseHTTPRequestHandler):
    probe: BrowserPortalProbe

    def log_message(self, _format: str, *args: Any) -> None:
        return

    def _write(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        self._write(status, "application/json; charset=utf-8", json.dumps(payload).encode("utf-8"))

    def do_GET(self) -> None:
        try:
            if self.path in {"/", "/index.html"}:
                self._write(200, "text/html; charset=utf-8", HTML.encode("utf-8"))
                return
            if self.path.startswith("/frame"):
                payload = self.probe._run(self.probe.capture_frame())
                self._json(200, payload)
                return
            self._json(404, {"ok": False, "error": "not found"})
        except Exception as exc:
            self._json(500, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    def do_POST(self) -> None:
        try:
            if self.path != "/event":
                self._json(404, {"ok": False, "error": "not found"})
                return
            length = int(self.headers.get("Content-Length") or "0")
            raw = self.rfile.read(length).decode("utf-8")
            payload = json.loads(raw or "{}")
            if not isinstance(payload, dict):
                raise ValueError("JSON object expected")
            result = self.probe._run(self.probe.apply_event(payload))
            self._json(200, result)
        except Exception as exc:
            self._json(500, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a live browser portal control probe.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--url", default=DEFAULT_TARGET_URL)
    args = parser.parse_args()

    probe = BrowserPortalProbe(args.url)
    Handler.probe = probe
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Browser portal control probe: http://{args.host}:{args.port}/")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
