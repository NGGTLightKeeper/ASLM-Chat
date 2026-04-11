from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

SRC_ROOT = Path(__file__).resolve().parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from sandbox.api import MCP_SERVER, TOOL_HANDLERS, TOOLS, handle_tool


def supports(engine: str | None = None, model_name: str | None = None) -> bool:
    """Expose this tool server for engines that support tool-calling."""

    return engine in ("ollama-service", "lms", "openai", "google-genai")


def call_tool(
    tool_id: str,
    arguments: dict[str, Any] | None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Dispatch one sandbox v2 tool."""

    return handle_tool(tool_id, arguments or {}, context or {})


def register_tools(mcp) -> None:
    """Register sandbox tools on a FastMCP instance."""

    from sandbox.tools import register_tools as register_fastmcp_tools

    register_fastmcp_tools(mcp)
