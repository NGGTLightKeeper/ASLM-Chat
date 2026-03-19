"""Example local MCP-style server that exposes multiple time tools."""

from __future__ import annotations

from datetime import UTC, datetime

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


def supports(engine=None, model_name=None):
    """Expose the example only for Ollama while tool calling is implemented there."""
    return engine == "ollama-service"


def _get_label(arguments):
    return str((arguments or {}).get("label", "")).strip() or None


def _time_now(arguments, context=None):
    """Return current local timestamps in ISO format."""
    local_now = datetime.now().astimezone()
    return {
        "label": _get_label(arguments),
        "local_time": local_now.isoformat(),
        "timezone": str(local_now.tzinfo),
        "server": (context or {}).get("server_name", MCP_SERVER["name"]),
    }


def _utc_now(arguments, context=None):
    """Return the current UTC timestamp in ISO format."""
    utc_now = datetime.now(UTC)
    return {
        "label": _get_label(arguments),
        "utc_time": utc_now.isoformat(),
        "timezone": "UTC",
        "server": (context or {}).get("server_name", MCP_SERVER["name"]),
    }


TOOL_HANDLERS = {
    "time_now": _time_now,
    "utc_now": _utc_now,
}
