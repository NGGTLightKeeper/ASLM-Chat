# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

from mcp.server.fastmcp import FastMCP

ASLM_ROOT = Path(__file__).resolve().parents[3]
if str(ASLM_ROOT) not in sys.path:
    sys.path.insert(0, str(ASLM_ROOT))


def _load_register_tools():
    """Load register_tools from the project-root mcp-server.py file."""

    module_path = Path(__file__).resolve().parents[1] / "mcp-server.py"
    spec = spec_from_file_location("web_search_mcp_server", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load MCP tools module: {module_path}")

    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.register_tools


register_tools = _load_register_tools()


# Application bootstrap.
mcp = FastMCP("mcp-web-search")
register_tools(mcp)


# Local runner entry point.
if __name__ == "__main__":
    yacy_started = False
    try:
        try:
            from Services import yacy_service

            yacy_started = yacy_service.start_yacy(log=True)
        except Exception:
            yacy_started = False

        mcp.run()
    finally:
        if yacy_started:
            try:
                from Services import yacy_service

                yacy_service.stop_yacy(log=True)
            except Exception:
                pass
