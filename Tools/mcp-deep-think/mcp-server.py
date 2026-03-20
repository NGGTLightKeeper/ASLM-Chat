# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

SERVER_ROOT = Path(__file__).resolve().parent
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))


# MCP tool registration

# Register Deep Think tools on the MCP server
def register_tools(mcp) -> None:
    """Attach Deep Think tools to the provided MCP server."""

    from src.orchestrator import orchestrator


    # Execution helpers
    async def _keepalive(coro, interval: float = 10.0):
        """Run a coroutine while periodically pinging the MCP session."""

        result = None
        done = asyncio.Event()

        async def _ping_loop() -> None:
            """Send debug keepalives until the main coroutine completes."""

            try:
                session = mcp._mcp_server.request_context.session
            except (LookupError, AttributeError):
                return

            while not done.is_set():
                try:
                    await asyncio.wait_for(asyncio.shield(done.wait()), timeout=interval)
                except asyncio.TimeoutError:
                    pass

                if done.is_set():
                    continue

                try:
                    await session.send_log_message(level="debug", data="thinking…", logger="deep-think")
                except Exception:
                    pass

        async def _run() -> None:
            """Capture the coroutine result and end the keepalive loop."""

            nonlocal result
            result = await coro
            done.set()

        await asyncio.gather(_run(), _ping_loop())
        return result


    # Tool handlers
    @mcp.tool()
    async def deep_think(query: str, mode: str = "full") -> str:
        """Run the Deep Think research swarm and return the formatted report."""

        normalized_mode = "quick" if str(mode).lower() == "quick" else "full"
        logger.info("Deep Think started: %s... (mode=%s)", query[:100], normalized_mode)

        try:
            report = await _keepalive(orchestrator.run(query=query, mode=normalized_mode))
            formatted = orchestrator.format_report_for_llm(
                report,
                include_raw_reports=normalized_mode == "full",
            )
            logger.info("Deep Think completed successfully (%s)", report.task_id)
            return formatted
        except Exception as exc:
            logger.exception("Deep Think failed")
            return f"Deep Think Error: {exc}"
