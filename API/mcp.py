"""Local tool discovery and execution helpers for ASLM-Chat."""

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
_TOOL_CACHE_SIGNATURE: tuple[tuple[str, int], ...] | None = None
_TOOL_CACHE: dict[str, dict[str, Any]] = {}


def reset_cache() -> None:
    """Clear the cached tool registry so tests and local edits are picked up."""
    global _TOOL_CACHE_SIGNATURE, _TOOL_CACHE
    _TOOL_CACHE_SIGNATURE = None
    _TOOL_CACHE = {}


def _tool_signature() -> tuple[tuple[str, int], ...]:
    """Return a stable filesystem signature for all ``Tools/*/tool.py`` files."""
    if not TOOLS_DIR.exists():
        return ()

    entries: list[tuple[str, int]] = []
    for child in sorted(TOOLS_DIR.iterdir(), key=lambda item: item.name.casefold()):
        tool_file = child / 'tool.py'
        if not child.is_dir() or not tool_file.is_file():
            continue
        try:
            stat = tool_file.stat()
        except OSError:
            continue
        entries.append((str(tool_file), stat.st_mtime_ns))
    return tuple(entries)


def _slugify(value: str) -> str:
    """Normalize identifiers from folder names or tool metadata."""
    normalized = re.sub(r'[^a-z0-9]+', '_', str(value or '').strip().lower()).strip('_')
    return normalized or 'tool'


def _load_module(tool_file: Path) -> ModuleType:
    """Load a ``tool.py`` file as an isolated Python module."""
    module_name = f"aslm_chat_tool_{_slugify(tool_file.parent.name)}"
    spec = importlib.util.spec_from_file_location(module_name, tool_file)
    if spec is None or spec.loader is None:
        raise ImportError(f'Could not load tool module from {tool_file}')

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _normalize_schema(schema: Any) -> dict[str, Any]:
    """Return a JSON-schema-like mapping suitable for Ollama tools."""
    if not isinstance(schema, dict):
        return {'type': 'object', 'properties': {}}

    normalized = dict(schema)
    normalized.setdefault('type', 'object')
    normalized.setdefault('properties', {})
    if not isinstance(normalized.get('properties'), dict):
        normalized['properties'] = {}
    return normalized


def _get_tool_callable(module: ModuleType):
    """Return the function used to execute a local tool definition."""
    for attr_name in ('call_tool', 'run_tool', 'execute'):
        candidate = getattr(module, attr_name, None)
        if callable(candidate):
            return candidate
    raise ValueError("Tool module must expose call_tool(arguments, context=None)")


def _extract_tool_definition(module: ModuleType, folder_name: str, tool_file: Path) -> dict[str, Any]:
    """Validate a tool module and normalize its public metadata."""
    raw_definition = getattr(module, 'TOOL', None)
    if not isinstance(raw_definition, dict):
        raise ValueError("Tool module must expose a TOOL dictionary")

    tool_id = _slugify(str(raw_definition.get('id') or folder_name))
    name = str(raw_definition.get('name') or folder_name).strip() or folder_name
    description = str(raw_definition.get('description') or '').strip()
    parameters = _normalize_schema(raw_definition.get('parameters'))
    callable_fn = _get_tool_callable(module)
    supports_fn = getattr(module, 'supports', None)

    return {
        'id': tool_id,
        'name': name,
        'description': description,
        'parameters': parameters,
        'module': module,
        'callable': callable_fn,
        'supports': supports_fn if callable(supports_fn) else None,
        'tool_file': tool_file,
    }


def _ensure_registry_loaded() -> dict[str, dict[str, Any]]:
    """Discover all valid local tool modules under ``Tools``."""
    global _TOOL_CACHE_SIGNATURE, _TOOL_CACHE

    signature = _tool_signature()
    if signature == _TOOL_CACHE_SIGNATURE:
        return _TOOL_CACHE

    discovered: dict[str, dict[str, Any]] = {}
    for tool_path_str, _mtime in signature:
        tool_file = Path(tool_path_str)
        folder_name = tool_file.parent.name
        try:
            module = _load_module(tool_file)
            tool_definition = _extract_tool_definition(module, folder_name, tool_file)
            discovered[tool_definition['id']] = tool_definition
        except Exception as exc:
            logger.warning('Skipping invalid tool module %s: %s', tool_file, exc)

    _TOOL_CACHE_SIGNATURE = signature
    _TOOL_CACHE = discovered
    return _TOOL_CACHE


def _tool_is_supported(tool_definition: dict[str, Any], engine: str | None, model_name: str | None) -> bool:
    """Return whether a tool opts into the current engine/model context."""
    supports_fn = tool_definition.get('supports')
    if not callable(supports_fn):
        return True

    try:
        return bool(supports_fn(engine=engine, model_name=model_name))
    except TypeError:
        try:
            return bool(supports_fn(engine, model_name))
        except Exception as exc:
            logger.warning('Tool %s support check failed: %s', tool_definition['id'], exc)
            return False
    except Exception as exc:
        logger.warning('Tool %s support check failed: %s', tool_definition['id'], exc)
        return False


def _serialize_tool(tool_definition: dict[str, Any]) -> dict[str, Any]:
    """Return the frontend-facing representation of a discovered tool."""
    return {
        'id': tool_definition['id'],
        'name': tool_definition['name'],
        'description': tool_definition['description'],
    }


def list_tools(engine: str | None = None, model_name: str | None = None) -> list[dict[str, Any]]:
    """Return all discovered tools that support the current engine/model."""
    registry = _ensure_registry_loaded()
    return [
        _serialize_tool(tool_definition)
        for tool_definition in registry.values()
        if _tool_is_supported(tool_definition, engine, model_name)
    ]


def get_tool(tool_id: str | None, engine: str | None = None, model_name: str | None = None) -> dict[str, Any] | None:
    """Return a discovered tool definition by id when it is available."""
    normalized_id = _slugify(str(tool_id or ''))
    if not normalized_id:
        return None

    registry = _ensure_registry_loaded()
    tool_definition = registry.get(normalized_id)
    if not tool_definition:
        return None
    if not _tool_is_supported(tool_definition, engine, model_name):
        return None
    return tool_definition


def build_ollama_tools(tool_id: str | None, engine: str | None = None, model_name: str | None = None) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Return a single Ollama-compatible tool registration for the selected tool."""
    tool_definition = get_tool(tool_id, engine=engine, model_name=model_name)
    if not tool_definition:
        return [], {}

    alias = tool_definition['id']
    return (
        [{
            'type': 'function',
            'function': {
                'name': alias,
                'description': tool_definition['description'] or tool_definition['name'],
                'parameters': tool_definition['parameters'],
            },
        }],
        {alias: tool_definition},
    )


async def _run_async_callable(callable_fn, arguments: dict[str, Any], context: dict[str, Any]) -> Any:
    """Execute an async tool callable with either one or two parameters."""
    signature = inspect.signature(callable_fn)
    if len(signature.parameters) <= 1:
        return await callable_fn(arguments)
    return await callable_fn(arguments, context)


def _run_sync_callable(callable_fn, arguments: dict[str, Any], context: dict[str, Any]) -> Any:
    """Execute a sync tool callable with either one or two parameters."""
    signature = inspect.signature(callable_fn)
    if len(signature.parameters) <= 1:
        return callable_fn(arguments)
    return callable_fn(arguments, context)


def _serialize_tool_result(result: Any) -> str:
    """Convert a local tool result into text suitable for a model tool message."""
    if result is None:
        return 'Tool returned no content.'
    if isinstance(result, str):
        return result
    if isinstance(result, (dict, list, tuple, int, float, bool)):
        return json.dumps(result, ensure_ascii=False, indent=2)
    return str(result)


def call_ollama_tool(tool_lookup: dict[str, dict[str, Any]], alias: str, arguments: dict[str, Any] | None, context: dict[str, Any] | None = None) -> str:
    """Execute the selected local tool and serialize its result."""
    tool_definition = tool_lookup.get(alias)
    if not tool_definition:
        return f'Unknown tool: {alias}'

    callable_fn = tool_definition['callable']
    call_arguments = arguments if isinstance(arguments, dict) else {}
    call_context = dict(context or {})
    call_context.setdefault('tool_id', tool_definition['id'])
    call_context.setdefault('tool_name', tool_definition['name'])
    call_context.setdefault('tool_file', str(tool_definition['tool_file']))
    call_context.setdefault('tools_dir', str(TOOLS_DIR))

    try:
        if inspect.iscoroutinefunction(callable_fn):
            result = asyncio.run(_run_async_callable(callable_fn, call_arguments, call_context))
        else:
            result = _run_sync_callable(callable_fn, call_arguments, call_context)
        return _serialize_tool_result(result)
    except Exception as exc:
        logger.exception('Tool execution failed for %s', tool_definition['id'])
        return f'Tool execution failed: {exc}'
