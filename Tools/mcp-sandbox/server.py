# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from pathlib import Path
import sys
from importlib.util import module_from_spec, spec_from_file_location

from mcp.server.fastmcp import FastMCP

SRC_ROOT = Path(__file__).resolve().parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from sandbox.container import _ensure_container_running


def _load_register_tools():
    """Load register_tools from the root mcp-server.py file."""

    module_path = Path(__file__).resolve().with_name("mcp-server.py")
    spec = spec_from_file_location("sandbox_mcp_server", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load MCP tools module: {module_path}")

    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.register_tools


register_tools = _load_register_tools()


# Server lifecycle.

def main() -> None:
    """Run the MCP sandbox server."""

    mcp = FastMCP("Sandbox")
    register_tools(mcp)

    import threading
    threading.Thread(target=_ensure_container_running, daemon=True).start()

    mcp.run()


if __name__ == "__main__":
    main()
