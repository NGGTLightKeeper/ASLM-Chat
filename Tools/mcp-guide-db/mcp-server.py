# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SERVER_ROOT = Path(__file__).resolve().parent
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

MCP_SERVER = {
    "id": "guide_db",
    "name": "Guide DB",
    "description": "Browse and maintain the internal tool guide database.",
}

TOOLS = [
    {
        "id": "list_guides",
        "name": "List Guides",
        "description": "List all available tool guides in the guide database.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "id": "get_guide",
        "name": "Get Guide",
        "description": "Retrieve the assembled content of a specific guide by name or index. Supports modes: core, core+recipes, full.",
        "parameters": {
            "type": "object",
            "properties": {
                "name_or_index": {
                    "type": "string",
                    "description": "Guide name (full or partial) or 1-based index as a string.",
                },
                "mode": {
                    "type": "string",
                    "enum": ["core", "core+recipes", "full"],
                    "description": "Output mode. core = guide + recipe titles + snippets. core+recipes = guide + full recipes + snippets. full = same as core+recipes.",
                    "default": "core",
                },
            },
            "required": ["name_or_index"],
        },
    },
    {
        "id": "list_recipes",
        "name": "List Recipes",
        "description": "List available workflow recipes. Optionally filter by guide name.",
        "parameters": {
            "type": "object",
            "properties": {
                "guide": {
                    "type": "string",
                    "description": "Optional guide name to filter recipes by.",
                },
            },
        },
    },
    {
        "id": "get_recipe",
        "name": "Get Recipe",
        "description": "Retrieve a specific workflow recipe by name or search query.",
        "parameters": {
            "type": "object",
            "properties": {
                "name_or_query": {
                    "type": "string",
                    "description": "Recipe slug (e.g. 'repo-analysis'), partial name, or search query.",
                },
            },
            "required": ["name_or_query"],
        },
    },
    {
        "id": "list_snippets",
        "name": "List Snippets",
        "description": "List snippet modules for one guide.",
        "parameters": {
            "type": "object",
            "properties": {
                "guide": {
                    "type": "string",
                    "description": "Guide folder name, for example mcp-web-search.",
                },
                "include_deprecated": {
                    "type": "boolean",
                    "description": "Include snippets already moved into _deprecated.",
                    "default": False,
                },
            },
            "required": ["guide"],
        },
    },
    {
        "id": "create_snippet",
        "name": "Create Snippet",
        "description": "Create a new reusable snippet module for a guide.",
        "parameters": {
            "type": "object",
            "properties": {
                "guide": {"type": "string"},
                "slug": {"type": "string", "description": "File slug without .md"},
                "title": {"type": "string"},
                "kind": {
                    "type": "string",
                    "enum": ["example", "pattern", "pitfall", "synergy"],
                },
                "body": {"type": "string"},
                "source_task": {"type": "string"},
                "related_tools": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional related tool names for cross-guide retrieval.",
                },
            },
            "required": ["guide", "slug", "title", "kind", "body", "source_task"],
        },
    },
    {
        "id": "append_snippet",
        "name": "Append Snippet",
        "description": "Append an addendum block to an existing active snippet.",
        "parameters": {
            "type": "object",
            "properties": {
                "guide": {"type": "string"},
                "snippet": {"type": "string", "description": "Snippet slug or filename"},
                "content": {"type": "string"},
                "note": {"type": "string", "description": "Short note explaining this addendum."},
            },
            "required": ["guide", "snippet", "content", "note"],
        },
    },
    {
        "id": "deprecate_snippet",
        "name": "Deprecate Snippet",
        "description": "Soft-delete a snippet by moving it into _deprecated with a recorded reason.",
        "parameters": {
            "type": "object",
            "properties": {
                "guide": {"type": "string"},
                "snippet": {"type": "string", "description": "Snippet slug or filename"},
                "reason": {"type": "string"},
            },
            "required": ["guide", "snippet", "reason"],
        },
    },
]


def supports(engine: str | None = None, model_name: str | None = None) -> bool:
    """Expose this tool server for engines that support tool-calling."""

    return engine in ("ollama-service", "lms")


def _load_db_dependencies():
    """Import shared Guide DB helpers lazily."""

    from db import (
        DB_DIR,
        VALID_KIND,
        _assemble_guide_content,
        _ensure_guide_layout,
        _get_all_recipes,
        _get_guides,
        _get_recipes,
        _list_snippet_records,
        _normalize_related_tools,
        _read_snippet_file,
        _render_recipe_full,
        _resolve_guide,
        _resolve_recipe,
        _safe_segment,
        _search_recipes,
        _snippet_exists,
        _snippet_path,
        _utc_now,
        _write_snippet_file,
        shutil,
    )

    return {
        "DB_DIR": DB_DIR,
        "VALID_KIND": VALID_KIND,
        "assemble_guide_content": _assemble_guide_content,
        "ensure_guide_layout": _ensure_guide_layout,
        "get_all_recipes": _get_all_recipes,
        "get_guides": _get_guides,
        "get_recipes": _get_recipes,
        "list_snippet_records": _list_snippet_records,
        "normalize_related_tools": _normalize_related_tools,
        "read_snippet_file": _read_snippet_file,
        "render_recipe_full": _render_recipe_full,
        "resolve_guide": _resolve_guide,
        "resolve_recipe": _resolve_recipe,
        "safe_segment": _safe_segment,
        "search_recipes": _search_recipes,
        "snippet_exists": _snippet_exists,
        "snippet_path": _snippet_path,
        "utc_now": _utc_now,
        "write_snippet_file": _write_snippet_file,
        "shutil": shutil,
    }


def _list_guides(arguments: dict[str, Any] | None, context: dict[str, Any] | None = None) -> str:
    """Return a formatted list of available guides."""

    deps = _load_db_dependencies()
    guides = deps["get_guides"]()
    if not guides:
        return f"No guides found in: {deps['DB_DIR']}"

    lines = [f"Available tool guides ({len(guides)} total):", ""]
    for idx, guide in enumerate(guides, start=1):
        lines.append(f"  [{idx}] {guide.name}")
    lines.append(f"\nGuide DB path: {deps['DB_DIR']}")
    lines.append("\nUse get_guide(name_or_index) to read any guide.")
    return "\n".join(lines)


def _get_guide(arguments: dict[str, Any] | None, context: dict[str, Any] | None = None) -> str:
    """Return one assembled guide."""

    deps = _load_db_dependencies()
    query = str((arguments or {}).get("name_or_index", "")).strip()
    mode = str((arguments or {}).get("mode", "core")).strip().lower()
    if mode not in ("core", "core+recipes", "full"):
        mode = "core"
    if not query:
        return "Error: name_or_index is required."

    guide = deps["resolve_guide"](query)
    if guide is None:
        guides = deps["get_guides"]()
        available = ", ".join(f"[{idx}] {entry.name}" for idx, entry in enumerate(guides, start=1))
        return f"Guide not found: '{query}'\nAvailable: {available or 'none'}"

    return deps["assemble_guide_content"](guide, mode=mode)


def _list_recipes(arguments: dict[str, Any] | None, context: dict[str, Any] | None = None) -> str:
    """Return a formatted list of available recipes."""

    deps = _load_db_dependencies()
    args = arguments or {}
    guide_filter = str(args.get("guide", "")).strip() if args.get("guide") else None

    if guide_filter:
        guide = deps["resolve_guide"](guide_filter)
        if guide is None:
            return f"Guide not found: '{guide_filter}'"
        recipes = deps["get_recipes"](guide)
    else:
        recipes = deps["get_all_recipes"]()

    if not recipes:
        return "No recipes found."

    lines = [f"Available recipes ({len(recipes)} total):", ""]
    for recipe in recipes:
        trigger_short = recipe.trigger[:60] + "..." if len(recipe.trigger) > 60 else recipe.trigger
        lines.append(
            f"  [{recipe.owner_guide}] {recipe.slug} -- {recipe.title}"
            f"  (domain: {recipe.domain}, trigger: {trigger_short})"
        )
    lines.append("")
    lines.append("Use get_recipe(name_or_query) to load a specific recipe.")
    return "\n".join(lines)


def _get_recipe(arguments: dict[str, Any] | None, context: dict[str, Any] | None = None) -> str:
    """Return one recipe by name or search query."""

    deps = _load_db_dependencies()
    query = str((arguments or {}).get("name_or_query", "")).strip()
    if not query:
        return "Error: name_or_query is required."

    recipe = deps["resolve_recipe"](query)
    if recipe is not None:
        return deps["render_recipe_full"](recipe)

    # Try search fallback
    results = deps["search_recipes"](query)
    if len(results) == 1:
        return deps["render_recipe_full"](results[0])
    if len(results) > 1:
        lines = [f"Multiple recipes match '{query}':"]
        for r in results:
            lines.append(f"  - {r.slug} ({r.owner_guide}) -- {r.title}")
        lines.append("")
        lines.append("Specify the exact slug to load one.")
        return "\n".join(lines)

    all_recipes = deps["get_all_recipes"]()
    available = ", ".join(r.slug for r in all_recipes)
    return f"Recipe not found: '{query}'\nAvailable: {available or 'none'}"


def _list_snippets(arguments: dict[str, Any] | None, context: dict[str, Any] | None = None) -> str:
    """Return snippet records for one guide as JSON."""

    deps = _load_db_dependencies()
    guide = str((arguments or {}).get("guide", "")).strip()
    if not guide:
        return "Error: guide is required."

    include_deprecated = bool((arguments or {}).get("include_deprecated", False))
    records = deps["list_snippet_records"](guide, include_deprecated)
    return json.dumps(records, indent=2, ensure_ascii=False)


def _create_snippet(arguments: dict[str, Any] | None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create a new guide snippet."""

    deps = _load_db_dependencies()
    args = arguments or {}

    guide = str(args.get("guide", "")).strip()
    slug_raw = args.get("slug", "")
    title = str(args.get("title", "")).strip()
    kind = str(args.get("kind", "")).strip().lower()
    body = str(args.get("body", "")).strip()
    source_task = str(args.get("source_task", "")).strip()
    related_tools = list(deps["normalize_related_tools"](args.get("related_tools")))

    if not guide:
        raise ValueError("guide is required.")

    slug = deps["safe_segment"](slug_raw, "slug")
    if kind not in deps["VALID_KIND"]:
        raise ValueError(f"Invalid kind: {kind}. Valid values: {', '.join(sorted(deps['VALID_KIND']))}")
    if not title:
        raise ValueError("title is required.")
    if not body:
        raise ValueError("body is required.")
    if not source_task:
        raise ValueError("source_task is required.")

    deps["ensure_guide_layout"](guide)
    if deps["snippet_exists"](guide, slug):
        raise ValueError(f"Snippet already exists: {guide}/{slug}.md")

    timestamp = deps["utc_now"]()
    snippet_path = deps["snippet_path"](guide, slug)
    meta = {
        "title": title,
        "kind": kind,
        "status": "active",
        "verification": "unverified",
        "created_at": timestamp,
        "updated_at": timestamp,
        "source_task": source_task,
        "related_tools": related_tools,
    }
    deps["write_snippet_file"](snippet_path, meta, body)
    return {
        "status": "created",
        "guide": guide,
        "slug": slug,
        "path": str(snippet_path.relative_to(deps["DB_DIR"])),
        "verification": "unverified",
    }


def _append_snippet(arguments: dict[str, Any] | None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Append an addendum to an active snippet."""

    deps = _load_db_dependencies()
    args = arguments or {}

    guide = str(args.get("guide", "")).strip()
    snippet = str(args.get("snippet", "")).strip()
    content = str(args.get("content", "")).strip()
    note = str(args.get("note", "")).strip()

    if not guide:
        raise ValueError("guide is required.")
    if not snippet:
        raise ValueError("snippet is required.")
    if not content:
        raise ValueError("content is required.")
    if not note:
        raise ValueError("note is required.")

    deps["ensure_guide_layout"](guide)
    snippet_path = deps["snippet_path"](guide, snippet)
    if not snippet_path.exists():
        raise ValueError(f"Active snippet not found: {guide}/{snippet}")

    meta, body = deps["read_snippet_file"](snippet_path)
    if str(meta.get("status", "active")).lower() != "active":
        raise ValueError("Only active snippets can be appended.")

    today = datetime.now(timezone.utc).date().isoformat()
    addendum = "\n\n".join(
        [
            body.strip(),
            f"## Addendum ({today})",
            f"Note: {note}",
            content,
        ]
    )
    meta["updated_at"] = deps["utc_now"]()
    deps["write_snippet_file"](snippet_path, meta, addendum)
    return {
        "status": "appended",
        "guide": guide,
        "slug": snippet_path.stem,
        "path": str(snippet_path.relative_to(deps["DB_DIR"])),
        "updated_at": meta["updated_at"],
    }


def _deprecate_snippet(arguments: dict[str, Any] | None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Move an active snippet into the deprecated area."""

    deps = _load_db_dependencies()
    args = arguments or {}

    guide = str(args.get("guide", "")).strip()
    snippet = str(args.get("snippet", "")).strip()
    reason = str(args.get("reason", "")).strip()

    if not guide:
        raise ValueError("guide is required.")
    if not snippet:
        raise ValueError("snippet is required.")
    if not reason:
        raise ValueError("reason is required.")

    deps["ensure_guide_layout"](guide)
    active_path = deps["snippet_path"](guide, snippet)
    deprecated_path = deps["snippet_path"](guide, snippet, deprecated=True)

    if not active_path.exists():
        raise ValueError(f"Active snippet not found: {guide}/{snippet}")
    if deprecated_path.exists():
        raise ValueError(f"Deprecated snippet already exists: {guide}/{deprecated_path.name}")

    meta, body = deps["read_snippet_file"](active_path)
    timestamp = deps["utc_now"]()
    meta["status"] = "deprecated"
    meta["updated_at"] = timestamp
    meta["deprecated_at"] = timestamp
    meta["deprecation_reason"] = reason

    deps["write_snippet_file"](active_path, meta, body)
    deprecated_path.parent.mkdir(parents=True, exist_ok=True)
    deps["shutil"].move(str(active_path), str(deprecated_path))
    return {
        "status": "deprecated",
        "guide": guide,
        "slug": deprecated_path.stem,
        "path": str(deprecated_path.relative_to(deps["DB_DIR"])),
        "deprecated_at": timestamp,
    }


TOOL_HANDLERS = {
    "list_guides": _list_guides,
    "get_guide": _get_guide,
    "list_recipes": _list_recipes,
    "get_recipe": _get_recipe,
    "list_snippets": _list_snippets,
    "create_snippet": _create_snippet,
    "append_snippet": _append_snippet,
    "deprecate_snippet": _deprecate_snippet,
}


def register_tools(server) -> None:
    """Attach Guide DB tools to the provided MCP server."""

    import mcp.types as types

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        """Return the list of MCP tools exposed by Guide DB."""

        return [
            types.Tool(
                name=tool["id"],
                description=tool["description"],
                inputSchema=tool["parameters"],
            )
            for tool in TOOLS
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any] | None) -> list[types.TextContent]:
        """Execute the requested Guide DB tool and return text content."""

        handler = TOOL_HANDLERS.get(name)
        if handler is None:
            return [types.TextContent(type="text", text=f"Unknown tool: {name}")]

        try:
            result = handler(arguments or {}, {})
            if isinstance(result, dict):
                text = json.dumps(result, indent=2, ensure_ascii=False)
            else:
                text = str(result)
        except Exception as exc:
            text = f"Error: {exc}"

        return [types.TextContent(type="text", text=text)]
