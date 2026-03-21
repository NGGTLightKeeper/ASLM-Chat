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
            "Open URL in the browser. Returns page snapshot with interactive elements "
            "and a brief text preview of page content."
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
            "Refresh the accessibility snapshot with updated refs. "
            "Also scrolls the page before snapshotting if scroll direction is provided."
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
            },
        },
    },
    {
        "id": "browser_click",
        "name": "Browser Click",
        "description": (
            "Click interactive elements by ref ID, click a batch of refs, "
            "or press a keyboard key."
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
        "description": "Type text into an input element (textbox, searchbox, and so on).",
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
            "Pause and display a message to the user, then wait for them to act. "
            "Use for CAPTCHA, login form, age gate, or manual overlay close."
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
        "description": "Take a screenshot of the current page and save it to task/.",
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
    """Expose this tool server only for Ollama tool-calling flows."""

    return engine == "ollama-service"


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
        _take_compact_snapshot,
        _take_snapshot,
        _wait_for_spa_content,
        log,
        state,
    )
    import browser as browser_module

    args = arguments or {}
    session = (context or {}).get("mcp_session")

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

            async def _navigate() -> None:
                await state.page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                await _wait_for_spa_content(state.page, timeout_ms=6000)

            await _run_with_keepalive(
                _navigate(),
                session=session,
                message=f"navigating to {target_url}...",
            )

            new_url = state.page.url
            action_context = f"Navigated to {new_url}"
            if new_url != target_url:
                action_context = f"Navigation: {target_url} -> {new_url} (redirected)"

            return _flatten_content(await _take_snapshot(action_context=action_context, run_dismiss=True))

        if name == "browser_snapshot":
            scroll = args.get("scroll")
            if scroll:
                amount = int(args.get("amount", 500))
                delta = amount if scroll == "down" else -amount
                await state.page.mouse.wheel(0, delta)
                await state.page.wait_for_timeout(600)

            return _flatten_content(
                await _take_snapshot(
                    action_context=f"Scrolled {scroll} {int(args.get('amount', 500))}px" if scroll else None
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

            relative_path = f"task/{file_name}"
            return (
                f"Screenshot saved: {file_path}\n"
                f"Call show_image('{relative_path}') to inspect visually."
            )

        return f"Unknown tool: {name}"
    except Exception as exc:
        return f"Error: {type(exc).__name__}: {exc}"


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

        session = None
        try:
            session = server.request_context.session
        except Exception:
            session = None

        result = await _execute_browser_tool(name, arguments or {}, {"mcp_session": session})
        return CallToolResult(content=[TextContent(type="text", text=result)])
