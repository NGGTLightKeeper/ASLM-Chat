# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

import json
from datetime import datetime, timezone

import mcp.types as types


# Standalone tool dispatcher — callable without a live MCP server.

async def dispatch_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """Execute the requested GuideDB tool and return text content."""

    import db as _db
    from db import (
        VALID_KIND,
        _assemble_guide_content,
        _ensure_guide_layout,
        _get_guides,
        _list_snippet_records,
        _normalize_related_tools,
        _read_snippet_file,
        _resolve_guide,
        _safe_segment,
        _snippet_exists,
        _snippet_path,
        _utc_now,
        _write_snippet_file,
        shutil,
    )

    DB_DIR = _db.DB_DIR

    try:
        # Guide listing and retrieval
        if name == "list_guides":
            guides = _get_guides()
            if not guides:
                return [types.TextContent(type="text", text=f"No guides found in: {DB_DIR}")]

            lines = [f"Available tool guides ({len(guides)} total):", ""]
            for idx, guide in enumerate(guides, start=1):
                lines.append(f"  [{idx}] {guide.name}")
            lines.append(f"\nGuide DB path: {DB_DIR}")
            lines.append("\nUse get_guide(name_or_index) to read any guide.")
            return [types.TextContent(type="text", text="\n".join(lines))]

        if name == "get_guide":
            query = str(arguments.get("name_or_index", "")).strip()
            if not query:
                return [types.TextContent(type="text", text="Error: name_or_index is required.")]

            guide = _resolve_guide(query)
            if guide is None:
                guides = _get_guides()
                available = ", ".join(f"[{idx}] {entry.name}" for idx, entry in enumerate(guides, start=1))
                return [
                    types.TextContent(
                        type="text",
                        text=f"Guide not found: '{query}'\nAvailable: {available or 'none'}",
                    )
                ]

            return [types.TextContent(type="text", text=_assemble_guide_content(guide))]

        # Snippet listing
        if name == "list_snippets":
            guide = str(arguments["guide"])
            include_deprecated = bool(arguments.get("include_deprecated", False))
            records = _list_snippet_records(guide, include_deprecated)
            return [types.TextContent(type="text", text=json.dumps(records, indent=2))]

        # Snippet creation
        if name == "create_snippet":
            guide = str(arguments["guide"])
            slug = _safe_segment(arguments["slug"], "slug")
            title = str(arguments["title"]).strip()
            kind = str(arguments["kind"]).strip().lower()
            body = str(arguments["body"]).strip()
            source_task = str(arguments["source_task"]).strip()
            related_tools = list(_normalize_related_tools(arguments.get("related_tools")))

            if kind not in VALID_KIND:
                raise ValueError(f"Invalid kind: {kind}. Valid values: {', '.join(sorted(VALID_KIND))}")
            if not title:
                raise ValueError("title is required.")
            if not body:
                raise ValueError("body is required.")
            if not source_task:
                raise ValueError("source_task is required.")

            _ensure_guide_layout(guide)
            if _snippet_exists(guide, slug):
                raise ValueError(f"Snippet already exists: {guide}/{slug}.md")

            timestamp = _utc_now()
            snippet_path = _snippet_path(guide, slug)
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
            _write_snippet_file(snippet_path, meta, body)
            return [
                types.TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "status": "created",
                            "guide": guide,
                            "slug": slug,
                            "path": str(snippet_path.relative_to(DB_DIR)),
                            "verification": "unverified",
                        },
                        indent=2,
                    ),
                )
            ]

        # Snippet updates
        if name == "append_snippet":
            guide = str(arguments["guide"])
            snippet = str(arguments["snippet"])
            content = str(arguments["content"]).strip()
            note = str(arguments["note"]).strip()

            if not content:
                raise ValueError("content is required.")
            if not note:
                raise ValueError("note is required.")

            _ensure_guide_layout(guide)
            snippet_path = _snippet_path(guide, snippet)
            if not snippet_path.exists():
                raise ValueError(f"Active snippet not found: {guide}/{snippet}")

            meta, body = _read_snippet_file(snippet_path)
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
            meta["updated_at"] = _utc_now()
            _write_snippet_file(snippet_path, meta, addendum)
            return [
                types.TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "status": "appended",
                            "guide": guide,
                            "slug": snippet_path.stem,
                            "path": str(snippet_path.relative_to(DB_DIR)),
                            "updated_at": meta["updated_at"],
                        },
                        indent=2,
                    ),
                )
            ]

        # Snippet deprecation
        if name == "deprecate_snippet":
            guide = str(arguments["guide"])
            snippet = str(arguments["snippet"])
            reason = str(arguments["reason"]).strip()

            if not reason:
                raise ValueError("reason is required.")

            _ensure_guide_layout(guide)
            active_path = _snippet_path(guide, snippet)
            deprecated_path = _snippet_path(guide, snippet, deprecated=True)

            if not active_path.exists():
                raise ValueError(f"Active snippet not found: {guide}/{snippet}")
            if deprecated_path.exists():
                raise ValueError(f"Deprecated snippet already exists: {guide}/{deprecated_path.name}")

            meta, body = _read_snippet_file(active_path)
            timestamp = _utc_now()
            meta["status"] = "deprecated"
            meta["updated_at"] = timestamp
            meta["deprecated_at"] = timestamp
            meta["deprecation_reason"] = reason

            _write_snippet_file(active_path, meta, body)
            deprecated_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(active_path), str(deprecated_path))
            return [
                types.TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "status": "deprecated",
                            "guide": guide,
                            "slug": deprecated_path.stem,
                            "path": str(deprecated_path.relative_to(DB_DIR)),
                            "deprecated_at": timestamp,
                        },
                        indent=2,
                    ),
                )
            ]

        return [types.TextContent(type="text", text=f"Unknown tool: {name}")]
    except Exception as exc:
        return [types.TextContent(type="text", text=f"Error: {exc}")]


# MCP tool registration

# Register all GuideDB tools on the MCP server
def register_tools(server) -> None:
    """Attach GuideDB tools to the provided server."""

    from db import VALID_KIND

    # Tool declarations
    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        """Return the list of MCP tools exposed by GuideDB."""

        return [
            types.Tool(
                name="list_guides",
                description=(
                    "List all available tool guides in the guide database. "
                    "Returns an indexed list of guide names."
                ),
                inputSchema={"type": "object", "properties": {}},
            ),
            types.Tool(
                name="get_guide",
                description=(
                    "Retrieve the assembled content of a specific tool guide by name or index. "
                    "This includes the main guide plus active snippet modules."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name_or_index": {
                            "type": "string",
                            "description": (
                                "Guide name (full or partial) or 1-based index as a string. "
                                'Always pass as a string - e.g. "1", "2", "mcp-web-search".'
                            ),
                        }
                    },
                    "required": ["name_or_index"],
                },
            ),
            types.Tool(
                name="list_snippets",
                description="List guide snippet modules for one guide.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "guide": {"type": "string", "description": "Guide folder name, e.g. mcp-web-search"},
                        "include_deprecated": {
                            "type": "boolean",
                            "default": False,
                            "description": "Include snippets already moved into _deprecated.",
                        },
                    },
                    "required": ["guide"],
                },
            ),
            types.Tool(
                name="create_snippet",
                description=(
                    "Create a new snippet module for a guide. "
                    "Use only when a reusable tool pattern proved useful in the current task."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "guide": {"type": "string"},
                        "slug": {"type": "string", "description": "File slug without .md"},
                        "title": {"type": "string"},
                        "kind": {"type": "string", "enum": sorted(VALID_KIND)},
                        "body": {"type": "string"},
                        "source_task": {"type": "string"},
                        "related_tools": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional related tool names for cross-guide synergy retrieval.",
                        },
                    },
                    "required": ["guide", "slug", "title", "kind", "body", "source_task"],
                },
            ),
            types.Tool(
                name="append_snippet",
                description="Append an addendum block to an existing active snippet and refresh updated_at.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "guide": {"type": "string"},
                        "snippet": {"type": "string", "description": "Snippet slug or filename"},
                        "content": {"type": "string"},
                        "note": {"type": "string", "description": "Short note explaining this addendum."},
                    },
                    "required": ["guide", "snippet", "content", "note"],
                },
            ),
            types.Tool(
                name="deprecate_snippet",
                description="Soft-delete a snippet by moving it into _deprecated with a recorded reason.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "guide": {"type": "string"},
                        "snippet": {"type": "string", "description": "Snippet slug or filename"},
                        "reason": {"type": "string"},
                    },
                    "required": ["guide", "snippet", "reason"],
                },
            ),
        ]

    # Tool execution
    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
        """Execute the requested GuideDB tool and return text content."""

        return await dispatch_tool(name, arguments)
