# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

import argparse
import asyncio
import logging
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server


# Load register_tools from the root mcp-server.py file.
def _load_register_tools():
    module_path = Path(__file__).resolve().with_name("mcp-server.py")
    spec = spec_from_file_location("browser_agent_mcp_server", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load MCP tools module: {module_path}")

    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.register_tools


register_tools = _load_register_tools()


# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("browser-agent")


# Server bootstrap
server = Server("browser-agent")
register_tools(server)


# Transport runners

# Run MCP over stdio.
async def _run_stdio() -> None:
    log.info("Starting browser-agent MCP server (stdio)...")

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


# Run MCP over streamable HTTP.
async def _run_http(host: str, port: int) -> None:
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.routing import Mount
    import uvicorn

    session_manager = StreamableHTTPSessionManager(app=server, stateless=False)

    # Proxy Starlette requests into the MCP session manager.
    async def handle_mcp(scope, receive, send) -> None:
        request = Request(scope, receive)
        await session_manager.handle_request(request, send)

    starlette_app = Starlette(routes=[Mount("/mcp", app=handle_mcp)])

    log.info(f"Starting browser-agent MCP server (HTTP) on {host}:{port}/mcp ...")

    config = uvicorn.Config(starlette_app, host=host, port=port, log_level="warning")
    userver = uvicorn.Server(config)

    async with session_manager.run():
        await userver.serve()


# CLI entry point

# Parse CLI arguments and launch the selected transport.
def main() -> None:
    parser = argparse.ArgumentParser(description="Browser Agent MCP Server")
    parser.add_argument("--http", action="store_true", help="Use HTTP transport instead of stdio")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=7821, help="HTTP port (default: 7821)")
    args = parser.parse_args()

    if args.http:
        asyncio.run(_run_http(args.host, args.port))
        return

    asyncio.run(_run_stdio())


if __name__ == "__main__":
    main()
