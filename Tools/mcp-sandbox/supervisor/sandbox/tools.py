# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import asyncio
import inspect
from typing import Any

from mcp.server.fastmcp import Context

from sandbox.api import TOOLS, handle_tool

TOOL_META = {
    "x-aslm-server": "aslm-chat-sandbox",
    "x-aslm-runtime": "fastmcp-stdio",
    "x-aslm-workspace-root": ".",
}


async def _report_progress(ctx: Context | None, progress: float, message: str) -> None:
    """Send a best-effort progress notification when the client supports it."""

    if ctx is None:
        return

    try:
        await ctx.report_progress(progress, 100, message)
    except Exception:
        pass


def register_tools(mcp) -> None:
    """Register sandbox tools on a FastMCP instance."""

    for tool_definition in TOOLS:
        tool_id = tool_definition["id"]
        parameters = tool_definition.get("parameters", {}).get("properties", {})

        async def _tool_impl(
            _tool_id: str = tool_id,
            ctx: Context | None = None,
            **kwargs: Any,
        ) -> dict[str, Any]:
            loop = asyncio.get_running_loop()

            def _progress(progress: float, message: str) -> None:
                asyncio.run_coroutine_threadsafe(
                    _report_progress(ctx, progress, message),
                    loop,
                )

            if _tool_id == "bash":
                await _report_progress(ctx, 5, f"Starting {_tool_id}")
                return await asyncio.to_thread(
                    handle_tool,
                    _tool_id,
                    kwargs,
                    {},
                    progress_callback=_progress,
                )

            label = kwargs.get("path") or kwargs.get("src") or kwargs.get("pattern") or _tool_id
            await _report_progress(ctx, 10, f"Running {_tool_id}: {label}")
            return await asyncio.to_thread(handle_tool, _tool_id, kwargs, {})

        _tool_impl.__name__ = f"sandbox_{tool_id}"
        _tool_impl.__doc__ = tool_definition["description"]
        _tool_impl.__annotations__ = {key: Any for key in parameters}
        _tool_impl.__annotations__["ctx"] = Context | None
        _tool_impl.__annotations__["return"] = dict[str, Any]
        signature_parameters = []
        required = set(tool_definition.get("parameters", {}).get("required", []))
        for key, schema in parameters.items():
            default = inspect._empty if key in required else schema.get("default", None)
            signature_parameters.append(
                inspect.Parameter(
                    key,
                    inspect.Parameter.KEYWORD_ONLY,
                    default=default,
                    annotation=Any,
                )
            )
        signature_parameters.append(
            inspect.Parameter(
                "ctx",
                inspect.Parameter.KEYWORD_ONLY,
                default=None,
                annotation=Context | None,
            )
        )
        _tool_impl.__signature__ = inspect.Signature(
            parameters=signature_parameters,
            return_annotation=dict[str, Any],
        )

        mcp.tool(name=tool_id, meta=TOOL_META)(_tool_impl)
