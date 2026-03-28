# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

import asyncio
import sys
from typing import Any

from mcp.types import CallToolResult, TextContent, Tool


# MCP tool registration

# Register all tools on the MCP server
def register_tools(server) -> None:
    """Attach Browser Agent tools to the provided server."""

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

    # Execution helpers

    # Keep the MCP session alive during long operations
    async def _run_with_keepalive(
        coro,
        interval: float = 3.0,
        message: str = "working…",
    ):
        """Run a coroutine while periodically sending keepalive logs."""

        result = None
        done = asyncio.Event()

        async def _keepalive_loop() -> None:
            """Emit debug logs until the tracked operation finishes."""

            try:
                session = server.request_context.session
            except LookupError:
                return

            while not done.is_set():
                try:
                    await asyncio.wait_for(asyncio.shield(done.wait()), timeout=interval)
                except asyncio.TimeoutError:
                    pass

                if done.is_set():
                    continue

                try:
                    await session.send_log_message(
                        level="debug",
                        data=message,
                        logger="browser-agent",
                    )
                except Exception:
                    pass

        async def _run() -> None:
            """Capture the coroutine result and finish the keepalive loop."""

            nonlocal result
            result = await coro
            done.set()

        await asyncio.gather(_run(), _keepalive_loop())
        return result


    # Tool declarations

    # Return the list of MCP tools exposed by the agent
    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """Describe the Browser Agent tool surface."""

        return [
            Tool(
                name="browser_navigate",
                description=(
                    "Open URL in the browser. Returns page snapshot with interactive elements "
                    "and a brief text preview of page content."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "URL to navigate to",
                        },
                    },
                    "required": ["url"],
                },
            ),
            Tool(
                name="browser_snapshot",
                description=(
                    "Refresh the accessibility snapshot with updated refs. "
                    "Also scrolls the page before snapshotting if scroll direction is provided. "
                    "Use when: refs go stale, you need to see full element tree, or scroll "
                    "to reveal more content."
                ),
                inputSchema={
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
            ),
            Tool(
                name="browser_click",
                description=(
                    "Click interactive elements by ref ID, OR press a keyboard key.\n"
                    "- Single click: {\"ref\": \"e5\"}\n"
                    "- Multiple clicks (batch): {\"refs\": [\"e5\", \"e8\", \"e12\"]}\n"
                    "  Batch mode clicks elements sequentially with a short pause between.\n"
                    "  Use for: selecting multiple checkboxes, radio + submit in one call.\n"
                    "- Keyboard key: {\"key\": \"Enter\"}\n"
                    "Returns compact snapshot (URL + interactive elements from main area)."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "ref": {
                            "type": "string",
                            "description": "Single element ref ID (e.g. 'e5')",
                        },
                        "refs": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Multiple ref IDs to click sequentially (e.g. ['e5', 'e8'])",
                        },
                        "key": {
                            "type": "string",
                            "description": "Keyboard key to press (Enter, Escape, Tab, ArrowDown, etc.)",
                        },
                    },
                },
            ),
            Tool(
                name="browser_type",
                description="Type text into an input element (textbox, searchbox, etc.).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "ref": {
                            "type": "string",
                            "description": "Element ref ID (textbox/searchbox)",
                        },
                        "text": {
                            "type": "string",
                            "description": "Text to type",
                        },
                        "press_enter": {
                            "type": "boolean",
                            "description": "Press Enter after typing (default: false)",
                            "default": False,
                        },
                    },
                    "required": ["ref", "text"],
                },
            ),
            Tool(
                name="browser_wait_for_user",
                description=(
                    "Pause and display a message to the user, then wait for them to act. "
                    "Use for: CAPTCHA, login form, age gate, manual overlay close. "
                    "Always call browser_navigate first — requires an open page. "
                    "Returns a full snapshot after the wait."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": "What the user needs to do",
                        },
                        "timeout_seconds": {
                            "type": "integer",
                            "description": "Seconds to wait (default: 45)",
                            "default": 45,
                        },
                    },
                    "required": ["message"],
                },
            ),
            Tool(
                name="browser_screenshot",
                description=(
                    "Take a screenshot of the current page and save it to task/ folder. "
                    "Returns the file path. Call sandbox read('task/<filename>') to inspect it visually."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "full_page": {
                            "type": "boolean",
                            "description": "Capture full scrollable page (default: false)",
                            "default": False,
                        },
                    },
                },
            ),
        ]


    # Tool execution

    # Dispatch MCP tool calls to browser actions
    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> CallToolResult:
        """Execute the requested Browser Agent tool."""

        import browser as _browser_module

        # Block new actions while waiting for manual user input.
        if _browser_module._waiting_for_user and name != "browser_wait_for_user":
            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=(
                            "⛔ BLOCKED: browser is waiting for user action.\n"
                            "The user has not finished yet (login / CAPTCHA / confirmation).\n"
                            "You MUST call browser_wait_for_user again to wait longer, "
                            "or call it with a short timeout to check if the user is done."
                        ),
                    ),
                ]
            )

        await state.ensure_open()

        # Most tools require an already opened page.
        no_page_tools = ("browser_navigate",)
        if name not in no_page_tools:
            current_url = state.page.url if state.page else "about:blank"
            if not current_url or current_url in ("about:blank", ""):
                return CallToolResult(
                    content=[
                        TextContent(
                            type="text",
                            text=(
                                "❌ No page is open yet. Call browser_navigate(url) first.\n"
                                f"After navigation completes, you can use {name} and other tools."
                            ),
                        ),
                    ]
                )

        try:
            # Navigation and snapshots
            if name == "browser_navigate":
                target_url = arguments["url"]
                if not target_url.startswith("http"):
                    target_url = "https://" + target_url

                log.info(f"Navigating to: {target_url}")

                async def _navigate() -> None:
                    """Open the target URL and wait for SPA content to settle."""

                    await state.page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                    await _wait_for_spa_content(state.page, timeout_ms=6000)

                await _run_with_keepalive(_navigate(), message=f"navigating to {target_url}…")

                new_url = state.page.url
                action_context = f"Navigated to {new_url}"
                if new_url != target_url:
                    action_context = f"Navigation: {target_url} → {new_url} (redirected)"

                content = await _take_snapshot(action_context=action_context, run_dismiss=True)

            elif name == "browser_snapshot":
                scroll = arguments.get("scroll")
                if scroll:
                    amount = arguments.get("amount", 500)
                    delta = amount if scroll == "down" else -amount
                    await state.page.mouse.wheel(0, delta)
                    await state.page.wait_for_timeout(600)

                content = await _take_snapshot(
                    action_context=f"Scrolled {scroll} {arguments.get('amount', 500)}px" if scroll else None
                )

            # Interaction tools
            elif name == "browser_click":
                key = arguments.get("key")
                ref = arguments.get("ref")
                refs = arguments.get("refs")

                if key and not ref and not refs:
                    log.info(f"Pressing key: {key}")
                    await state.page.keyboard.press(key)
                    await state.page.wait_for_timeout(800)
                    content = await _take_compact_snapshot(action_context=f"Pressed {key}")

                elif refs:
                    log.info(f"Batch clicking {len(refs)} elements: {refs}")

                    clicked_refs: list[str] = []
                    errors: list[str] = []

                    for ref_value in refs:
                        ref_value = str(ref_value)
                        try:
                            await _click_by_role_and_name(ref_value)
                            clicked_refs.append(ref_value)
                            await state.page.wait_for_timeout(500)
                        except Exception as exc:
                            errors.append(f"[{ref_value}]: {exc}")

                    await state.page.wait_for_timeout(800)

                    action_desc = f"Batch clicked [{', '.join(clicked_refs)}]"
                    if errors:
                        action_desc += f" (errors: {'; '.join(errors)})"

                    content = await _take_compact_snapshot(action_context=action_desc)

                else:
                    ref = str(ref)
                    previous_url = state.page.url

                    log.info(f"Clicking element: {ref}")

                    await _click_by_role_and_name(ref)
                    await state.page.wait_for_timeout(1500)

                    new_url = state.page.url
                    if new_url != previous_url:
                        content = await _take_snapshot(
                            action_context=f"Clicked [{ref}] → navigated to {new_url}"
                        )
                    else:
                        content = await _take_compact_snapshot(action_context=f"Clicked [{ref}]")

            elif name == "browser_type":
                ref = str(arguments["ref"])
                text = str(arguments["text"])
                press_enter = arguments.get("press_enter", False)

                log.info(f"Typing into {ref}: '{text[:50]}'")

                await _fill_by_role_and_name(ref, text, clear=True, press_enter=press_enter)
                await state.page.wait_for_timeout(1000)

                content = await _take_compact_snapshot(action_context=f"Typed '{text[:40]}' into [{ref}]")

            # User-assisted flow
            elif name == "browser_wait_for_user":
                message = str(arguments.get("message", "Please interact with the browser."))
                timeout_seconds = int(arguments.get("timeout_seconds", 45))

                log.info(f"Waiting {timeout_seconds}s for user: {message}")

                print(f"\n{'=' * 60}", file=sys.stderr)
                print("[browser-agent] USER ACTION REQUIRED:", file=sys.stderr)
                print(f"  {message}", file=sys.stderr)
                print(f"  Waiting {timeout_seconds} seconds...", file=sys.stderr)
                print(f"{'=' * 60}\n", file=sys.stderr)
                sys.stderr.flush()

                _browser_module._waiting_for_user = True
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
                    _browser_module._waiting_for_user = False

                log.info("Wait complete, resuming.")

                content = await _take_snapshot(
                    action_context=f"Resumed after {timeout_seconds}s user wait",
                    run_dismiss=True,
                )

            # Artifacts
            elif name == "browser_screenshot":
                full_page = arguments.get("full_page", False)

                DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

                import time as _time

                file_name = f"screenshot_{int(_time.time())}.png"
                file_path = DOWNLOADS_DIR / file_name

                await state.page.screenshot(path=str(file_path), full_page=bool(full_page))
                log.info(f"Screenshot saved: {file_path}")

                relative_path = f"task/{file_name}"
                content = [
                    TextContent(
                        type="text",
                        text=(
                            f"Screenshot saved: {file_path}\n"
                            f"Call read('{relative_path}') to inspect visually."
                        ),
                    )
                ]

            else:
                content = [TextContent(type="text", text=f"Unknown tool: {name}")]

        except Exception as exc:
            log.error(f"Tool '{name}' error: {exc}")
            content = [
                TextContent(
                    type="text",
                    text=f"Error: {type(exc).__name__}: {exc}",
                )
            ]

        return CallToolResult(content=content)
