# Copyright NGGT.LightKeeper. All Rights Reserved.

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

MCP_SERVER = {
    "id": "time_suite",
    "name": "Time Suite",
    "description": "Time helpers for quick local and UTC lookups.",
}

TOOLS = [
    {
        "id": "time_now",
        "name": "Current Time",
        "description": "Get the current local time and timezone.",
        "parameters": {
            "type": "object",
            "properties": {
                "label": {
                    "type": "string",
                    "description": "Optional label describing why the time was requested.",
                },
            },
        },
    },
    {
        "id": "utc_now",
        "name": "Current UTC Time",
        "description": "Get the current UTC timestamp.",
        "parameters": {
            "type": "object",
            "properties": {
                "label": {
                    "type": "string",
                    "description": "Optional label describing why the time was requested.",
                },
            },
        },
    },
]


# Check tool availability
def supports(engine: str | None = None, model_name: str | None = None) -> bool:
    """Expose this tool server for every ASLM chat engine with tool calling."""

    return engine in ("ollama-service", "lms", "openai", "google-genai")


# Read optional label
def _get_label(arguments: dict[str, Any] | None) -> str | None:
    """Return the optional label passed by the caller."""

    return str((arguments or {}).get("label", "")).strip() or None

# Read server display name
def _get_server_name(context: dict[str, Any] | None) -> str:
    """Return the visible server name for tool responses."""

    return str((context or {}).get("server_name") or MCP_SERVER["name"])


# Build local time payload
def _time_now(arguments: dict[str, Any] | None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the current local time in ISO format."""

    local_now = datetime.now().astimezone()

    return {
        "label": _get_label(arguments),
        "local_time": local_now.isoformat(),
        "timezone": str(local_now.tzinfo),
        "server": _get_server_name(context),
    }

# Build UTC time payload
def _utc_now(arguments: dict[str, Any] | None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the current UTC time in ISO format."""

    utc_now = datetime.now(UTC)

    return {
        "label": _get_label(arguments),
        "utc_time": utc_now.isoformat(),
        "timezone": "UTC",
        "server": _get_server_name(context),
    }


TOOL_HANDLERS = {
    "time_now": _time_now,
    "utc_now": _utc_now,
}
