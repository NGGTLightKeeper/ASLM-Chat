# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

import argparse
import asyncio
import logging
import sys

from mcp.server import Server
from mcp.server.stdio import stdio_server

from tools import register_tools


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

# Run MCP over stdio
async def _run_stdio() -> None:
    """Start the MCP server with stdio transport."""

    log.info("Starting browser-agent MCP server (stdio)...")

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


# Run MCP over HTTP
async def _run_http(host: str, port: int) -> None:
    """Start the MCP server with streamable HTTP transport."""

    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.routing import Mount
    import uvicorn

    session_manager = StreamableHTTPSessionManager(app=server, stateless=False)

    async def handle_mcp(scope, receive, send) -> None:
        """Proxy Starlette requests into the MCP session manager."""

        request = Request(scope, receive)
        await session_manager.handle_request(request, send)

    starlette_app = Starlette(routes=[Mount("/mcp", app=handle_mcp)])

    log.info(f"Starting browser-agent MCP server (HTTP) on {host}:{port}/mcp ...")

    config = uvicorn.Config(starlette_app, host=host, port=port, log_level="warning")
    userver = uvicorn.Server(config)

    async with session_manager.run():
        await userver.serve()


# CLI entry point

# Parse arguments and launch the selected transport
def main() -> None:
    """Parse CLI arguments and start the server."""

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
