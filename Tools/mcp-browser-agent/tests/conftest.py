# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

PKG_ROOT = Path(__file__).resolve().parents[1]
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))


# Module-scoped fixture: load mcp-server.py bridge for contract tests.

@pytest.fixture(scope="module")
def bridge_module():
    bridge_path = PKG_ROOT / "mcp-server.py"
    spec = importlib.util.spec_from_file_location("browser_agent_mcp_bridge_test", bridge_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
