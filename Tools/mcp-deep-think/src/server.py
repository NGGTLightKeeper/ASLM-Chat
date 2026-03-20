# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import asyncio
import logging
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .llm_client import llm_client
from .search_client import search_client


def _load_register_tools():
    """Load register_tools from the project-root mcp-server.py file."""

    module_path = Path(__file__).resolve().parents[1] / "mcp-server.py"
    spec = spec_from_file_location("deep_think_mcp_server", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load MCP tools module: {module_path}")

    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.register_tools


register_tools = _load_register_tools()


# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("mcp").setLevel(logging.CRITICAL)
logging.getLogger("fastmcp").setLevel(logging.CRITICAL)
logger = logging.getLogger(__name__)


# MCP bootstrap
mcp = FastMCP("DeepThink")
register_tools(mcp)


# Shutdown helpers

# Close shared clients before process exit
async def cleanup() -> None:
    """Close shared async clients used by the server."""

    await llm_client.close()
    await search_client.close()


# Entrypoint

# Run the MCP server and always clean up shared resources
def main() -> None:
    """Start the Deep Think MCP server."""

    try:
        mcp.run()
    finally:
        asyncio.run(cleanup())


if __name__ == "__main__":
    main()
