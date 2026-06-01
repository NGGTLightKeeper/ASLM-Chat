# Copyright NGGT.LightKeeper. All Rights Reserved.

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamablehttp_client

from Settings.mcp_json import UserMcpServerEntry, _slugify

logger = logging.getLogger(__name__)

LIST_TOOLS_TIMEOUT = 15.0
CALL_TOOL_TIMEOUT = 120.0

_locks: defaultdict[str, threading.Lock] = defaultdict(threading.Lock)


# Release per-server locks (reserved for future persistent sessions).
def shutdown_all() -> None:
    _locks.clear()


# Normalize MCP tool input schemas into JSON Schema objects.
def _normalize_parameters_schema(schema: Any) -> dict[str, Any]:
    if schema is None:
        return {"type": "object", "properties": {}}
    if hasattr(schema, "model_dump"):
        dumped = schema.model_dump(mode="python", exclude_none=True)
    elif isinstance(schema, dict):
        dumped = dict(schema)
    else:
        dumped = {"type": "object", "properties": {}}

    if not isinstance(dumped, dict):
        return {"type": "object", "properties": {}}

    normalized = dict(dumped)
    normalized.setdefault("type", "object")
    normalized.setdefault("properties", {})
    if not isinstance(normalized.get("properties"), dict):
        normalized["properties"] = {}
    return normalized


# Convert MCP list_tools results into ASLM tool definition payloads.
def _tool_definitions_from_mcp_tools(
    server_id: str,
    mcp_tools: list[Any],
) -> tuple[list[dict[str, Any]], str | None]:
    definitions: list[dict[str, Any]] = []
    seen_slugs: set[str] = set()
    error: str | None = None

    for index, tool in enumerate(mcp_tools, start=1):
        raw_name = str(getattr(tool, "name", "") or "").strip()
        if not raw_name:
            raw_name = f"tool_{index}"

        # Assign a stable slug and avoid collisions within one server.
        base_slug = _slugify(raw_name)
        slug = base_slug
        suffix = 2
        while slug in seen_slugs:
            slug = f"{base_slug}_{suffix}"
            suffix += 1
        seen_slugs.add(slug)

        description = str(getattr(tool, "description", "") or "").strip()
        input_schema = getattr(tool, "inputSchema", None)

        definitions.append(
            {
                "id": slug,
                "alias": f"{server_id}__{slug}",
                "name": raw_name,
                "description": description,
                "parameters": _normalize_parameters_schema(input_schema),
                "mcp_tool_name": raw_name,
            }
        )

    if not definitions:
        error = "Server returned no tools"
    return definitions, error


# Format one MCP call_tool result as plain text for the chat layer.
def _format_call_tool_result(result: Any) -> str:
    if getattr(result, "isError", False):
        parts: list[str] = []
        for block in getattr(result, "content", []) or []:
            text = getattr(block, "text", None)
            if text:
                parts.append(str(text))
        message = "\n".join(parts).strip() or "Tool reported an error."
        return f"MCP tool error: {message}"

    chunks: list[str] = []
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict) and structured:
        chunks.append(json.dumps(structured, ensure_ascii=False, indent=2))

    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            chunks.append(str(text))

    if not chunks:
        return "Tool returned no textual content."
    return "\n\n".join(chunks).strip()


# Open one short-lived MCP session for stdio or streamable HTTP transport.
@asynccontextmanager
async def _connect_session(entry: UserMcpServerEntry):
    if entry.transport == "http":
        assert entry.url
        headers = dict(entry.headers) if entry.headers else None
        async with streamablehttp_client(
            entry.url,
            headers=headers,
            timeout=30.0,
            sse_read_timeout=300.0,
        ) as streams:
            read_stream, write_stream, _ = streams
            async with ClientSession(read_stream, write_stream) as session:
                await asyncio.wait_for(session.initialize(), timeout=LIST_TOOLS_TIMEOUT)
                yield session
        return

    assert entry.command
    devnull = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    try:
        params = StdioServerParameters(
            command=entry.command,
            args=list(entry.args),
            env=dict(entry.env) if entry.env else None,
            cwd=entry.cwd,
        )
        async with stdio_client(params, errlog=devnull) as streams:
            read_stream, write_stream = streams
            async with ClientSession(read_stream, write_stream) as session:
                await asyncio.wait_for(session.initialize(), timeout=LIST_TOOLS_TIMEOUT)
                yield session
    finally:
        devnull.close()


# List tools from one user MCP server over a fresh connection.
async def _list_tools_async(entry: UserMcpServerEntry) -> tuple[list[dict[str, Any]], str | None]:
    try:
        async with _connect_session(entry) as session:
            listed = await asyncio.wait_for(session.list_tools(), timeout=LIST_TOOLS_TIMEOUT)
            tools = list(getattr(listed, "tools", None) or [])
            return _tool_definitions_from_mcp_tools(entry.server_id, tools)
    except Exception as exc:  # pragma: no cover - runtime / network
        logger.warning("User MCP list_tools failed for %s: %s", entry.server_id, exc)
        return [], f"{type(exc).__name__}: {exc}"


# Invoke one MCP tool over a fresh connection.
async def _call_tool_async(entry: UserMcpServerEntry, mcp_tool_name: str, arguments: dict[str, Any]) -> str:
    try:
        async with _connect_session(entry) as session:
            result = await asyncio.wait_for(
                session.call_tool(mcp_tool_name, arguments or {}),
                timeout=CALL_TOOL_TIMEOUT,
            )
            return _format_call_tool_result(result)
    except Exception as exc:  # pragma: no cover
        logger.exception("User MCP call_tool failed for %s.%s", entry.server_id, mcp_tool_name)
        return f"User MCP tool execution failed: {exc}"


# Connect once, list tools, and disconnect (serialized per server id).
def fetch_tool_definitions(entry: UserMcpServerEntry) -> tuple[list[dict[str, Any]], str | None]:
    lock = _locks[entry.server_id]
    with lock:
        return asyncio.run(_list_tools_async(entry))


# Run one MCP tool call with a new connection per invocation.
def call_user_mcp_tool(entry: UserMcpServerEntry, mcp_tool_name: str, arguments: dict[str, Any]) -> str:
    lock = _locks[entry.server_id]
    with lock:
        return asyncio.run(_call_tool_async(entry, mcp_tool_name, arguments))
