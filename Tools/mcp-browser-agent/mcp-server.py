# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from typing import Any

from mcp.types import CallToolResult, TextContent, Tool

SERVER_ROOT = Path(__file__).resolve().parent
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from browser import log

MCP_SERVER = {
    "id": "browser_agent",
    "name": "Browser Agent",
    "description": "Browser automation with snapshots, clicks, typing, and screenshots.",
}

TOOLS = [
    {
        "id": "browser_navigate",
        "name": "Browser Navigate",
        "description": (
            "Open a URL in the browser and return an accessibility tree snapshot of the loaded page. "
            "The snapshot lists all interactive elements (buttons, links, inputs, selects) with their ref IDs, roles, and labels. "
            "Also includes a brief text preview of the visible page content. "
            "Always call this first before using any other browser tool — ref IDs are only valid after a navigate or snapshot call. "
            "Handles redirects automatically and reports the final URL."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to navigate to"},
            },
            "required": ["url"],
        },
    },
    {
        "id": "browser_snapshot",
        "name": "Browser Snapshot",
        "description": (
            "Refresh the accessibility tree snapshot to get updated element refs after a page change. "
            "Call after any action that modifies the DOM (clicks, form submissions, dynamic content loading) to get fresh ref IDs. "
            "Optionally scrolls the page before snapshotting: scroll='down' or scroll='up' by the specified amount in pixels (default 500). "
            "Use scroll to reveal content below the fold and then snapshot to capture those elements. "
            "Set full=true to include all page regions (banner, navigation, footer) — use when navigation buttons or controls are missing from the default snapshot."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "scroll": {
                    "type": "string",
                    "enum": ["up", "down"],
                    "description": "Scroll before snapshotting (optional)",
                },
                "amount": {
                    "type": "integer",
                    "description": "Pixels to scroll (default: 500)",
                    "default": 500,
                },
                "full": {
                    "type": "boolean",
                    "description": "Include all page regions including banner and navigation (default: false)",
                    "default": False,
                },
            },
        },
    },
    {
        "id": "browser_click",
        "name": "Browser Click",
        "description": (
            "Click an interactive element by its ref ID, click multiple elements sequentially, or press a keyboard key. "
            "ref: single element ref ID from the snapshot (e.g. 'e5'). "
            "refs: list of ref IDs to click one after another in order. "
            "key: keyboard key to press without clicking an element — use for Enter, Escape, Tab, ArrowDown, ArrowUp, Space, and similar. "
            "Returns a compact updated snapshot after the action. "
            "If the click triggers navigation to a new URL, returns a full snapshot of the new page."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "ref": {
                    "type": "string",
                    "description": "Single element ref ID (for example 'e5')",
                },
                "refs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Multiple ref IDs to click sequentially.",
                },
                "key": {
                    "type": "string",
                    "description": "Keyboard key to press (Enter, Escape, Tab, ArrowDown, and so on).",
                },
            },
        },
    },
    {
        "id": "browser_type",
        "name": "Browser Type",
        "description": (
            "Clear an input element and type text into it. Works for textbox, searchbox, textarea, and similar input fields. "
            "ref is the element ref ID from the current snapshot. "
            "The existing content of the field is cleared before typing. "
            "Set press_enter=True to submit the input immediately after typing (equivalent to pressing Enter). "
            "Returns a compact updated snapshot after typing."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "ref": {"type": "string", "description": "Element ref ID"},
                "text": {"type": "string", "description": "Text to type"},
                "press_enter": {
                    "type": "boolean",
                    "description": "Press Enter after typing (default: false)",
                    "default": False,
                },
            },
            "required": ["ref", "text"],
        },
    },
    {
        "id": "browser_wait_for_user",
        "name": "Browser Wait For User",
        "description": (
            "Pause automation and display a message asking the user to perform a manual action in the browser. "
            "Use when the page requires human interaction that cannot be automated: CAPTCHA solving, login with credentials, age verification gate, cookie consent popup, or 2FA prompt. "
            "message should clearly describe what the user needs to do. "
            "The browser remains open and the session stays active during the wait. "
            "After timeout_seconds the tool resumes and returns a fresh snapshot of whatever state the page is in."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "What the user needs to do"},
                "timeout_seconds": {
                    "type": "integer",
                    "description": "Seconds to wait (default: 45)",
                    "default": 45,
                },
            },
            "required": ["message"],
        },
    },
    {
        "id": "browser_screenshot",
        "name": "Browser Screenshot",
        "description": (
            "Take a PNG screenshot of the current browser page and save it to the task workspace. "
            "full_page=False (default) captures only the visible viewport. "
            "full_page=True captures the entire scrollable page height. "
            "Saved as screenshot_<timestamp>.png. "
            "Returns the file path and a hint to call sandbox read(...) to inspect it visually. "
            "Use to verify visual state, capture rendered output, or document automation results."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "full_page": {
                    "type": "boolean",
                    "description": "Capture full scrollable page (default: false)",
                    "default": False,
                },
            },
        },
    },
]


def supports(engine: str | None = None, model_name: str | None = None) -> bool:
    """Expose this tool server for engines that support tool-calling."""

    return engine in ("ollama-service", "lms")


def _flatten_content(content: Any) -> str:
    """Convert MCP-style content payloads into plain text for local tool execution."""

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            text = getattr(item, "text", None)
            if text is not None:
                chunks.append(str(text))
            elif isinstance(item, str):
                chunks.append(item)
            else:
                chunks.append(str(item))
        return "\n\n".join(chunk for chunk in chunks if chunk)

    text = getattr(content, "text", None)
    if text is not None:
        return str(text)

    return str(content)


async def _run_with_keepalive(coro, session=None, interval: float = 3.0, message: str = "working..."):
    """Run a coroutine while optionally sending keepalive logs to an MCP session."""

    if session is None:
        return await coro

    result = None
    done = asyncio.Event()

    async def _keepalive_loop() -> None:
        while not done.is_set():
            try:
                await asyncio.wait_for(asyncio.shield(done.wait()), timeout=interval)
            except asyncio.TimeoutError:
                pass

            if done.is_set():
                continue

            try:
                await session.send_log_message(level="debug", data=message, logger="browser-agent")
            except Exception:
                pass

    async def _run() -> None:
        nonlocal result
        result = await coro
        done.set()

    await asyncio.gather(_run(), _keepalive_loop())
    return result


async def _execute_browser_tool(name: str, arguments: dict[str, Any] | None, context: dict[str, Any] | None = None) -> str:
    """Execute one browser action and return plain text output."""

    from browser import (
        DOWNLOADS_DIR,
        _click_by_role_and_name,
        _fill_by_role_and_name,
        run_in_browser_loop,
        _take_compact_snapshot,
        _take_snapshot,
        _wait_for_spa_content,
        log,
        state,
    )
    import browser as browser_module

    args = arguments or {}
    session = (context or {}).get("mcp_session")
    keepalive_message = "working..."
    keepalive_interval = 3.0

    if name == "browser_navigate":
        target_url = str(args.get("url", "")).strip()
        if target_url and not target_url.startswith("http"):
            target_url = "https://" + target_url
        keepalive_message = f"navigating to {target_url or 'page'}..."
    elif name == "browser_wait_for_user":
        keepalive_message = "waiting for user..."
        keepalive_interval = 12.0

    async def _perform() -> str:
        if browser_module._waiting_for_user and name != "browser_wait_for_user":
            return (
                "BLOCKED: browser is waiting for user action.\n"
                "The user has not finished yet (login / CAPTCHA / confirmation).\n"
                "Call browser_wait_for_user again to wait longer or re-check progress."
            )

        await state.ensure_open()

        if name not in {"browser_navigate"}:
            current_url = state.page.url if state.page else "about:blank"
            if not current_url or current_url in {"about:blank", ""}:
                return f"No page is open yet. Call browser_navigate(url) first, then retry {name}."

        try:
            if name == "browser_navigate":
                target_url = str(args.get("url", "")).strip()
                if not target_url:
                    return "Error: url is required."
                if not target_url.startswith("http"):
                    target_url = "https://" + target_url

                log.info("Navigating to: %s", target_url)
                await state.page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                await _wait_for_spa_content(state.page, timeout_ms=6000)

                new_url = state.page.url
                action_context = f"Navigated to {new_url}"
                if new_url != target_url:
                    action_context = f"Navigation: {target_url} -> {new_url} (redirected)"

                return _flatten_content(await _take_snapshot(action_context=action_context, run_dismiss=True))

            if name == "browser_snapshot":
                scroll = args.get("scroll")
                full = bool(args.get("full", False))
                if scroll:
                    amount = int(args.get("amount", 500))
                    delta = amount if scroll == "down" else -amount
                    await state.page.mouse.wheel(0, delta)
                    await state.page.wait_for_timeout(600)

                return _flatten_content(
                    await _take_snapshot(
                        action_context=f"Scrolled {scroll} {int(args.get('amount', 500))}px" if scroll else None,
                        full=full,
                    )
                )

            if name == "browser_click":
                key = args.get("key")
                ref = args.get("ref")
                refs = args.get("refs")

                if key and not ref and not refs:
                    key_name = str(key)
                    log.info("Pressing key: %s", key_name)
                    await state.page.keyboard.press(key_name)
                    await state.page.wait_for_timeout(800)
                    return _flatten_content(await _take_compact_snapshot(action_context=f"Pressed {key_name}"))

                if refs:
                    clicked_refs: list[str] = []
                    errors: list[str] = []

                    for ref_value in refs:
                        current_ref = str(ref_value)
                        try:
                            await _click_by_role_and_name(current_ref)
                            clicked_refs.append(current_ref)
                            await state.page.wait_for_timeout(500)
                        except Exception as exc:
                            errors.append(f"[{current_ref}]: {exc}")

                    await state.page.wait_for_timeout(800)

                    action_desc = f"Batch clicked [{', '.join(clicked_refs)}]"
                    if errors:
                        action_desc += f" (errors: {'; '.join(errors)})"

                    return _flatten_content(await _take_compact_snapshot(action_context=action_desc))

                if ref is None:
                    return "Error: provide either ref, refs, or key."

                ref_value = str(ref)
                previous_url = state.page.url

                log.info("Clicking element: %s", ref_value)
                await _click_by_role_and_name(ref_value)
                await state.page.wait_for_timeout(1500)

                new_url = state.page.url
                if new_url != previous_url:
                    return _flatten_content(
                        await _take_snapshot(action_context=f"Clicked [{ref_value}] -> navigated to {new_url}")
                    )

                return _flatten_content(await _take_compact_snapshot(action_context=f"Clicked [{ref_value}]"))

            if name == "browser_type":
                ref_value = str(args.get("ref", "")).strip()
                text = str(args.get("text", ""))
                press_enter = bool(args.get("press_enter", False))

                if not ref_value:
                    return "Error: ref is required."

                log.info("Typing into %s: '%s'", ref_value, text[:50])
                await _fill_by_role_and_name(ref_value, text, clear=True, press_enter=press_enter)
                await state.page.wait_for_timeout(1000)
                return _flatten_content(
                    await _take_compact_snapshot(action_context=f"Typed '{text[:40]}' into [{ref_value}]")
                )

            if name == "browser_wait_for_user":
                message = str(args.get("message", "Please interact with the browser."))
                timeout_seconds = int(args.get("timeout_seconds", 45))

                log.info("Waiting %ss for user: %s", timeout_seconds, message)
                print(f"\n{'=' * 60}", file=sys.stderr)
                print("[browser-agent] USER ACTION REQUIRED:", file=sys.stderr)
                print(f"  {message}", file=sys.stderr)
                print(f"  Waiting {timeout_seconds} seconds...", file=sys.stderr)
                print(f"{'=' * 60}\n", file=sys.stderr)
                sys.stderr.flush()

                browser_module._waiting_for_user = True
                try:
                    keepalive_interval = 12
                    elapsed = 0
                    while elapsed < timeout_seconds:
                        chunk = min(keepalive_interval, timeout_seconds - elapsed)
                        await asyncio.sleep(chunk)
                        elapsed += chunk

                        if elapsed >= timeout_seconds:
                            continue

                        try:
                            await state.page.evaluate("() => document.readyState")
                        except Exception:
                            pass
                finally:
                    browser_module._waiting_for_user = False

                return _flatten_content(
                    await _take_snapshot(
                        action_context=f"Resumed after {timeout_seconds}s user wait",
                        run_dismiss=True,
                    )
                )

            if name == "browser_screenshot":
                full_page = bool(args.get("full_page", False))
                DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

                file_name = f"screenshot_{int(time.time())}.png"
                file_path = DOWNLOADS_DIR / file_name

                await state.page.screenshot(path=str(file_path), full_page=full_page)
                log.info("Screenshot saved: %s", file_path)

                relative_path = f"_sandbox/{file_name}"
                return (
                    f"Screenshot saved: {file_path}\n"
                    f"Call read('{file_name}') to inspect visually."
                )

            return f"Unknown tool: {name}"
        except Exception as exc:
            return f"Error: {type(exc).__name__}: {exc}"

    return await run_in_browser_loop(
        _perform(),
        session=session,
        interval=keepalive_interval,
        message=keepalive_message,
    )


def _make_tool_handler(tool_id: str):
    """Build an ASLM-compatible per-tool wrapper."""

    async def _handler(arguments: dict[str, Any] | None, context: dict[str, Any] | None = None) -> str:
        return await _execute_browser_tool(tool_id, arguments or {}, context or {})

    return _handler


TOOL_HANDLERS = {
    tool["id"]: _make_tool_handler(tool["id"])
    for tool in TOOLS
}


async def call_tool(tool_id: str, arguments: dict[str, Any] | None, context: dict[str, Any] | None = None) -> str:
    """Generic ASLM-compatible dispatcher for Browser Agent tools."""

    return await _execute_browser_tool(tool_id, arguments or {}, context or {})


def register_tools(server) -> None:
    """Attach Browser Agent tools to the provided MCP server."""

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """Describe the Browser Agent tool surface."""

        return [
            Tool(
                name=tool["id"],
                description=tool["description"],
                inputSchema=tool["parameters"],
            )
            for tool in TOOLS
        ]

    @server.call_tool()
    async def server_call_tool(name: str, arguments: dict[str, Any] | None) -> CallToolResult:
        """Execute the requested Browser Agent tool."""

        log.info("server_call_tool: %s", name)
        session = None
        try:
            session = server.request_context.session
        except Exception:
            session = None

        result = await _execute_browser_tool(name, arguments or {}, {"mcp_session": session})
        return CallToolResult(content=[TextContent(type="text", text=result)])
