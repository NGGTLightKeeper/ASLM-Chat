# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


SERVER_ROOT = Path(__file__).resolve().parent
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from deep_research import run_deep_research


MCP_SERVER = {
    "id": "deep_research",
    "name": "Deep Research",
    "fresh_process_per_call": True,
    "description": (
        "Run an isolated, multi-step research session with the currently selected model, "
        "web search, page reading, and sandboxed bash."
    ),
}

TOOLS = [
    {
        "id": "deep_research",
        "name": "Deep Research",
        "description": (
            "Research a complex question exhaustively. The current model first creates a plan, "
            "then iteratively searches, reads sources, analyzes evidence, and returns a cited report."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "The complete question or topic to research.",
                },
                "instructions": {
                    "type": "string",
                    "description": "Optional scope, output, locale, or evidence requirements.",
                },
                "max_rounds": {
                    "type": "integer",
                    "minimum": 4,
                    "maximum": 24,
                    "default": 12,
                    "description": "Maximum model/tool iterations after the planning pass.",
                },
            },
            "required": ["topic"],
        },
    }
]


def prepare_deep_research(arguments: dict[str, Any] | None) -> dict[str, Any]:
    args = dict(arguments or {})
    topic = str(args.get("topic") or "").strip()
    if not topic:
        message = "Deep research requires a non-empty topic."
        return {
            "ok": False,
            "arguments": {},
            "tool_ui": {"kind": "deep_research", "status": "error"},
            "error_result": {
                "model_context": message,
                "sources": [],
                "ui": {"kind": "deep_research", "status": "error"},
            },
        }

    try:
        max_rounds = min(24, max(4, int(args.get("max_rounds") or 12)))
    except (TypeError, ValueError):
        max_rounds = 12
    canonical = {
        "topic": topic,
        "instructions": str(args.get("instructions") or "").strip(),
        "max_rounds": max_rounds,
        "timeout_s": 3600,
    }
    return {
        "ok": True,
        "arguments": canonical,
        "tool_ui": {"kind": "deep_research", "status": "running", "topic": topic},
    }


TOOL_PREPARERS = {"deep_research": prepare_deep_research}


def supports(engine: str | None = None, model_name: str | None = None) -> bool:
    return engine in (None, "ollama-service", "lms", "openai", "google-genai")


def call_tool(
    tool_id: str,
    arguments: dict[str, Any] | None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if tool_id != "deep_research":
        raise ValueError(f"Unknown tool: {tool_id}")
    return run_deep_research(arguments or {}, context or {})
