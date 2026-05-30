# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest


# Module-scoped fixture: load mcp-server.py bridge for contract tests.

@pytest.fixture(scope="module")
def bridge_module():
    bridge_path = Path(__file__).resolve().parents[1] / "mcp-server.py"
    spec = importlib.util.spec_from_file_location("mcp_server_bridge_under_test", bridge_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# web_search — reject spam queries before calling the service.

@pytest.mark.unit
def test_web_search_rejects_spam_before_service(bridge_module) -> None:
    with patch.object(bridge_module, "write_search_io_event"):
        result = asyncio.run(
            bridge_module.call_tool(
                "web_search",
                {"query": "best ultimate comprehensive complete guide amazing"},
            )
        )
    assert result["ui"]["status"] == "rejected"
    assert result["sources"] == []
    assert str(result["model_context"]).startswith("BAD_QUERY:")


# web_search — pass coerced query and effort through to run_web_search_rich.

@pytest.mark.unit
def test_web_search_passes_coerced_query_and_effort_to_service(bridge_module) -> None:
    rich = {
        "query": "pytorch cuda install",
        "search_id": "test",
        "sources": [],
        "model_context": "ok",
        "ui": {"status": "done", "result_count": 0, "compact": {}},
    }
    with patch("services.run_web_search_rich", new_callable=AsyncMock, return_value=rich) as mock_run:
        with patch.object(bridge_module, "write_search_io_event"):
            result = asyncio.run(
                bridge_module.call_tool(
                    "web_search",
                    {"query": "pytorch cuda install", "effort": "high"},
                )
            )

    assert result is rich
    mock_run.assert_awaited_once()
    args, kwargs = mock_run.await_args
    assert args[0] == "pytorch cuda install"
    assert kwargs.get("effort") == "high"
