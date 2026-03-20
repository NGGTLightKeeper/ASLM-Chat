# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

import asyncio
import os
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server


def _load_register_tools():
    """Load register_tools from the root mcp-server.py file."""

    module_path = Path(__file__).resolve().with_name("mcp-server.py")
    spec = spec_from_file_location("guide_db_mcp_server", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load MCP tools module: {module_path}")

    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.register_tools


register_tools = _load_register_tools()


# Windows event loop setup
if os.name == "nt":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


# Server bootstrap
server = Server("GuideDB")
register_tools(server)


# Entrypoint

# Run the MCP server over stdio
async def main():
    """Start the GuideDB MCP server over stdio."""

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
