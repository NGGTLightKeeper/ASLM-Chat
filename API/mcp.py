"""Local MCP-style server discovery and execution helpers for ASLM-Chat."""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
import json
import logging
import re
from pathlib import Path
from types import ModuleType
from typing import Any

logger = logging.getLogger(__name__)

TOOLS_DIR = Path(__file__).resolve().parent.parent / "Tools"
SERVER_FILENAME = "mcp-server.py"
_SERVER_CACHE_SIGNATURE: tuple[tuple[str, int], ...] | None = None
_SERVER_CACHE: dict[str, dict[str, Any]] = {}


def reset_cache() -> None:
    """Clear cached server discovery so tests and local edits are picked up."""
    global _SERVER_CACHE_SIGNATURE, _SERVER_CACHE
    _SERVER_CACHE_SIGNATURE = None
    _SERVER_CACHE = {}


def _server_signature() -> tuple[tuple[str, int], ...]:
    """Return a stable filesystem signature for all ``Tools/*/mcp-server.py`` files."""
    if not TOOLS_DIR.exists():
        return ()

    entries: list[tuple[str, int]] = []
    for child in sorted(TOOLS_DIR.iterdir(), key=lambda item: item.name.casefold()):
        server_file = child / SERVER_FILENAME
        if not child.is_dir() or not server_file.is_file():
            continue
        try:
            stat = server_file.stat()
        except OSError:
            continue
        entries.append((str(server_file), stat.st_mtime_ns))
    return tuple(entries)


def _slugify(value: str) -> str:
    """Normalize identifiers from folder names or public metadata."""
    normalized = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")
    return normalized or "tool"


def _load_module(server_file: Path) -> ModuleType:
    """Load an ``mcp-server.py`` file as an isolated Python module."""
    module_name = f"aslm_chat_mcp_server_{_slugify(server_file.parent.name)}"
    spec = importlib.util.spec_from_file_location(module_name, server_file)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load MCP server module from {server_file}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _normalize_schema(schema: Any) -> dict[str, Any]:
    """Return a JSON-schema-like mapping suitable for Ollama tools."""
    if not isinstance(schema, dict):
        return {"type": "object", "properties": {}}

    normalized = dict(schema)
    normalized.setdefault("type", "object")
    normalized.setdefault("properties", {})
    if not isinstance(normalized.get("properties"), dict):
        normalized["properties"] = {}
    return normalized


def _resolve_server_callable(module: ModuleType):
    """Return the generic server dispatcher callable when one is provided."""
    for attr_name in ("call_tool", "run_tool", "execute_tool", "execute"):
        candidate = getattr(module, attr_name, None)
        if callable(candidate):
            return candidate
    return None


def _normalize_tool_handlers(module: ModuleType) -> dict[str, Any]:
    """Return explicit per-tool handlers exported by a server module."""
    raw_handlers = getattr(module, "TOOL_HANDLERS", None)
    if raw_handlers is None:
        raw_handlers = getattr(module, "TOOL_EXECUTORS", None)
    if not isinstance(raw_handlers, dict):
        return {}

    normalized: dict[str, Any] = {}
    for raw_key, raw_value in raw_handlers.items():
        if callable(raw_value):
            normalized[_slugify(str(raw_key or ""))] = raw_value
    return normalized


def _normalize_server_tools(raw_tools: Any, server_id: str) -> list[dict[str, Any]]:
    """Validate and normalize the tool definitions exposed by one server."""
    if not isinstance(raw_tools, list) or not raw_tools:
        raise ValueError("MCP server module must expose a non-empty TOOLS list")

    normalized_tools: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for index, raw_tool in enumerate(raw_tools, start=1):
        if not isinstance(raw_tool, dict):
            raise ValueError("Each MCP server tool definition must be a dictionary")

        tool_id = _slugify(str(raw_tool.get("id") or f"tool_{index}"))
        if tool_id in seen_ids:
            raise ValueError(f"Duplicate tool id '{tool_id}' in server '{server_id}'")
        seen_ids.add(tool_id)

        name = str(raw_tool.get("name") or tool_id).strip() or tool_id
        description = str(raw_tool.get("description") or "").strip()
        parameters = _normalize_schema(raw_tool.get("parameters"))
        alias = f"{server_id}__{tool_id}"

        normalized_tools.append(
            {
                "id": tool_id,
                "alias": alias,
                "name": name,
                "description": description,
                "parameters": parameters,
            }
        )

    return normalized_tools


def _extract_server_definition(module: ModuleType, folder_name: str, server_file: Path) -> dict[str, Any]:
    """Validate an MCP server module and normalize its metadata."""
    raw_server = getattr(module, "MCP_SERVER", None)
    if raw_server is None:
        raw_server = getattr(module, "SERVER", None)
    if raw_server is None:
        raw_server = {}
    if not isinstance(raw_server, dict):
        raise ValueError("MCP server module must expose an MCP_SERVER dictionary")

    raw_tools = getattr(module, "TOOLS", None)
    if raw_tools is None:
        legacy_tool = getattr(module, "TOOL", None)
        if isinstance(legacy_tool, dict):
            raw_tools = [legacy_tool]

    server_id = _slugify(str(raw_server.get("id") or folder_name))
    server_name = str(raw_server.get("name") or folder_name).strip() or folder_name
    description = str(raw_server.get("description") or "").strip()
    supports_fn = getattr(module, "supports", None)
    tool_handlers = _normalize_tool_handlers(module)
    server_callable = _resolve_server_callable(module)
    tools = _normalize_server_tools(raw_tools, server_id)

    if not tool_handlers and server_callable is None:
        raise ValueError(
            "MCP server module must expose TOOL_HANDLERS or a generic call_tool/tool dispatcher"
        )

    return {
        "id": server_id,
        "name": server_name,
        "description": description,
        "tools": tools,
        "module": module,
        "supports": supports_fn if callable(supports_fn) else None,
        "server_callable": server_callable,
        "tool_handlers": tool_handlers,
        "server_file": server_file,
    }


def _ensure_registry_loaded() -> dict[str, dict[str, Any]]:
    """Discover all valid local MCP-style server modules under ``Tools``."""
    global _SERVER_CACHE_SIGNATURE, _SERVER_CACHE

    signature = _server_signature()
    if signature == _SERVER_CACHE_SIGNATURE:
        return _SERVER_CACHE

    discovered: dict[str, dict[str, Any]] = {}
    for server_path_str, _mtime in signature:
        server_file = Path(server_path_str)
        folder_name = server_file.parent.name
        try:
            module = _load_module(server_file)
            server_definition = _extract_server_definition(module, folder_name, server_file)
            discovered[server_definition["id"]] = server_definition
        except Exception as exc:
            logger.warning("Skipping invalid MCP server module %s: %s", server_file, exc)

    _SERVER_CACHE_SIGNATURE = signature
    _SERVER_CACHE = discovered
    return _SERVER_CACHE


def _server_is_supported(server_definition: dict[str, Any], engine: str | None, model_name: str | None) -> bool:
    """Return whether a server opts into the current engine/model context."""
    supports_fn = server_definition.get("supports")
    if not callable(supports_fn):
        return True

    try:
        return bool(supports_fn(engine=engine, model_name=model_name))
    except TypeError:
        try:
            return bool(supports_fn(engine, model_name))
        except Exception as exc:
            logger.warning("Server %s support check failed: %s", server_definition["id"], exc)
            return False
    except Exception as exc:
        logger.warning("Server %s support check failed: %s", server_definition["id"], exc)
        return False


def _serialize_tool(tool_definition: dict[str, Any]) -> dict[str, Any]:
    """Return a frontend-facing representation of one tool inside a server."""
    return {
        "id": tool_definition["id"],
        "name": tool_definition["name"],
        "description": tool_definition["description"],
    }


def _serialize_server(server_definition: dict[str, Any]) -> dict[str, Any]:
    """Return the frontend-facing representation of a discovered tool server."""
    tools = [_serialize_tool(tool_definition) for tool_definition in server_definition["tools"]]
    return {
        "id": server_definition["id"],
        "name": server_definition["name"],
        "description": server_definition["description"],
        "tool_count": len(tools),
        "tools": tools,
    }


def list_servers(engine: str | None = None, model_name: str | None = None) -> list[dict[str, Any]]:
    """Return all discovered tool servers that support the current engine/model."""
    registry = _ensure_registry_loaded()
    return [
        _serialize_server(server_definition)
        for server_definition in registry.values()
        if _server_is_supported(server_definition, engine, model_name)
    ]


def get_server(server_id: str | None, engine: str | None = None, model_name: str | None = None) -> dict[str, Any] | None:
    """Return a discovered tool server by id when it is available."""
    normalized_id = _slugify(str(server_id or ""))
    if not normalized_id:
        return None

    registry = _ensure_registry_loaded()
    server_definition = registry.get(normalized_id)
    if not server_definition:
        return None
    if not _server_is_supported(server_definition, engine, model_name):
        return None
    return server_definition


def build_ollama_tools(server_id: str | None, engine: str | None = None, model_name: str | None = None) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Return Ollama-compatible tools for the selected local MCP-style server."""
    server_definition = get_server(server_id, engine=engine, model_name=model_name)
    if not server_definition:
        return [], {}

    tools: list[dict[str, Any]] = []
    tool_lookup: dict[str, dict[str, Any]] = {}
    for tool_definition in server_definition["tools"]:
        alias = tool_definition["alias"]
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": alias,
                    "description": tool_definition["description"] or tool_definition["name"],
                    "parameters": tool_definition["parameters"],
                },
            }
        )
        tool_lookup[alias] = {
            "server": server_definition,
            "tool": tool_definition,
        }

    return tools, tool_lookup


async def _run_async_callable(callable_fn, *args: Any) -> Any:
    """Execute an async callable with the provided arguments."""
    return await callable_fn(*args)


def _run_sync_callable(callable_fn, *args: Any) -> Any:
    """Execute a sync callable with the provided arguments."""
    return callable_fn(*args)


def _execute_callable(callable_fn, *args: Any) -> Any:
    """Execute sync or async callables with a unified helper."""
    if inspect.iscoroutinefunction(callable_fn):
        return asyncio.run(_run_async_callable(callable_fn, *args))
    return _run_sync_callable(callable_fn, *args)


def _dispatch_server_callable(callable_fn, tool_id: str, arguments: dict[str, Any], context: dict[str, Any]) -> Any:
    """Call a generic server dispatcher with a tolerant signature strategy."""
    signature = inspect.signature(callable_fn)
    parameter_names = list(signature.parameters)

    if len(parameter_names) <= 1:
        return _execute_callable(callable_fn, arguments)
    if len(parameter_names) == 2:
        first_name = parameter_names[0].lower()
        if first_name in {"tool_id", "tool", "name", "tool_name"}:
            return _execute_callable(callable_fn, tool_id, arguments)
        return _execute_callable(callable_fn, arguments, context)
    return _execute_callable(callable_fn, tool_id, arguments, context)


def _serialize_tool_result(result: Any) -> str:
    """Convert a local tool result into text suitable for a model tool message."""
    if result is None:
        return "Tool returned no content."
    if isinstance(result, str):
        return result
    if isinstance(result, (dict, list, tuple, int, float, bool)):
        return json.dumps(result, ensure_ascii=False, indent=2)
    return str(result)


def call_ollama_tool(tool_lookup: dict[str, dict[str, Any]], alias: str, arguments: dict[str, Any] | None, context: dict[str, Any] | None = None) -> str:
    """Execute a tool from the selected local MCP-style server and serialize its result."""
    lookup_entry = tool_lookup.get(alias)
    if not lookup_entry:
        return f"Unknown tool: {alias}"

    server_definition = lookup_entry["server"]
    tool_definition = lookup_entry["tool"]
    call_arguments = arguments if isinstance(arguments, dict) else {}
    call_context = dict(context or {})
    call_context.setdefault("server_id", server_definition["id"])
    call_context.setdefault("server_name", server_definition["name"])
    call_context.setdefault("tool_id", tool_definition["id"])
    call_context.setdefault("tool_name", tool_definition["name"])
    call_context.setdefault("tool_alias", tool_definition["alias"])
    call_context.setdefault("server_file", str(server_definition["server_file"]))
    call_context.setdefault("tools_dir", str(TOOLS_DIR))

    try:
        handler = server_definition["tool_handlers"].get(tool_definition["id"])
        if handler is None:
            handler = server_definition["tool_handlers"].get(tool_definition["alias"])

        if handler is not None:
            signature = inspect.signature(handler)
            if len(signature.parameters) <= 1:
                result = _execute_callable(handler, call_arguments)
            else:
                result = _execute_callable(handler, call_arguments, call_context)
        elif server_definition["server_callable"] is not None:
            result = _dispatch_server_callable(
                server_definition["server_callable"],
                tool_definition["id"],
                call_arguments,
                call_context,
            )
        else:
            return f"Tool execution failed: no handler registered for {tool_definition['id']}"

        return _serialize_tool_result(result)
    except Exception as exc:
        logger.exception("Tool execution failed for %s.%s", server_definition["id"], tool_definition["id"])
        return f"Tool execution failed: {exc}"
