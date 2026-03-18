"""Example tool that returns current local and UTC time."""

from __future__ import annotations

from datetime import UTC, datetime

TOOL = {
    "id": "time_now",
    "name": "Current Time",
    "description": "Get the current local and UTC time for quick time-aware answers.",
    "parameters": {
        "type": "object",
        "properties": {
            "label": {
                "type": "string",
                "description": "Optional label describing why the time was requested.",
            },
        },
    },
}


def supports(engine=None, model_name=None):
    """Expose the example only for Ollama while tool calling is implemented there."""
    return engine == "ollama-service"


def call_tool(arguments, context=None):
    """Return current timestamps in ISO format."""
    label = str((arguments or {}).get("label", "")).strip()
    local_now = datetime.now().astimezone()
    utc_now = datetime.now(UTC)
    return {
        "label": label or None,
        "local_time": local_now.isoformat(),
        "utc_time": utc_now.isoformat(),
        "timezone": str(local_now.tzinfo),
    }
