# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, patch

import pytest


# MCP server metadata and exposed browser tool ids.

@pytest.mark.unit
def test_mcp_server_metadata_and_tool_surface(bridge_module) -> None:
    assert bridge_module.MCP_SERVER["id"] == "browser_agent"
    tool_ids = {tool["id"] for tool in bridge_module.TOOLS}
    assert tool_ids == {
        "browser_navigate",
        "browser_snapshot",
        "browser_click",
        "browser_key",
        "browser_scroll",
        "browser_text",
        "browser_wait_for_user",
        "browser_screenshot",
    }
    assert set(bridge_module.TOOL_HANDLERS) == tool_ids


# supports() — known LLM engines vs unknown.

@pytest.mark.unit
@pytest.mark.parametrize(
    "engine",
    ["ollama-service", "lms", "openai", "google-genai", "unknown-engine"],
)
def test_supports_known_engines(bridge_module, engine: str) -> None:
    expected = engine in ("ollama-service", "lms", "openai", "google-genai")
    assert bridge_module.supports(engine=engine) is expected


# _flatten_content — plain string vs list of text blocks.

@pytest.mark.unit
def test_flatten_content_joins_text_chunks(bridge_module) -> None:
    class Block:
        def __init__(self, text: str) -> None:
            self.text = text

    assert bridge_module._flatten_content("plain") == "plain"
    assert bridge_module._flatten_content([Block("a"), Block("b")]) == "a\n\nb"


# _browser_keepalive_settings — normalize bare host to https for navigate.

@pytest.mark.unit
def test_browser_keepalive_settings_normalizes_navigate_url(bridge_module) -> None:
    interval, message = bridge_module._browser_keepalive_settings(
        "browser_navigate",
        {"url": "example.com"},
    )
    assert interval == 3.0
    assert "https://example.com" in message


# call_tool — inline mode delegates to _execute_browser_tool.

@pytest.mark.unit
def test_call_tool_delegates_to_execute_browser_tool(bridge_module, monkeypatch) -> None:
    monkeypatch.setenv("ASLM_BROWSER_AGENT_INLINE", "1")
    with patch.object(
        bridge_module,
        "_execute_browser_tool",
        new_callable=AsyncMock,
        return_value="ok",
    ) as execute:
        result = asyncio.run(
            bridge_module.call_tool("browser_snapshot", {"full": False}, {})
        )
    execute.assert_awaited_once_with("browser_snapshot", {"full": False}, {})
    assert result == "ok"


# _execute_browser_tool_local — block interaction while waiting for user.

@pytest.mark.unit
def test_execute_browser_tool_local_blocked_while_waiting(bridge_module, monkeypatch) -> None:
    monkeypatch.setenv("ASLM_BROWSER_AGENT_INLINE", "1")
    import browser as browser_module

    monkeypatch.setattr(browser_module, "_waiting_for_user", True)
    result = asyncio.run(
        bridge_module._execute_browser_tool_local(
            "browser_click",
            {"ref": "e0"},
            {},
        )
    )
    if isinstance(result, dict):
        text = str(result.get("model_context") or "")
    else:
        text = str(result)
    assert text.startswith("BLOCKED:")
