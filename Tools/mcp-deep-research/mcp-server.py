# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


SERVER_ROOT = Path(__file__).resolve().parent
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from deep_research import run_deep_research
from Tools import deep_research_control as research_control


MCP_SERVER = {
    "id": "deep_research",
    "name": "Deep Research",
    "fresh_process_per_call": True,
    "description": (
        "Run an isolated, approval-gated research session with the currently selected model, "
        "deliberate query reflection, web search, and page reading."
    ),
}

TOOLS = [
    {
        "id": "deep_research",
        "name": "Deep Research",
        "description": (
            "Research a complex question with an approved plan, deliberate reflection between "
            "limited search batches, source reading, and a final cited report."
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
                    "minimum": 2,
                    "maximum": 10,
                    "default": 6,
                    "description": "Maximum reflection and search checkpoints. Each uses at most two queries.",
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
        max_rounds = min(10, max(2, int(args.get("max_rounds") or 6)))
    except (TypeError, ValueError):
        max_rounds = 6
    session_id = research_control.new_session_id()
    canonical = {
        "topic": topic,
        "instructions": str(args.get("instructions") or "").strip(),
        "max_rounds": max_rounds,
        "session_id": session_id,
        "approval_timeout_s": 900,
        "timeout_s": 3600,
    }
    research_control.create_session(
        session_id,
        topic=topic,
        extra={
            "status": "planning",
            "phase": "planning",
            "query_budget": max_rounds * 2,
            "can_approve": False,
            "can_edit": False,
            "can_stop": True,
        },
    )
    return {
        "ok": True,
        "arguments": canonical,
        "tool_ui": {
            "kind": "deep_research",
            "status": "planning",
            "topic": topic,
            "session_id": session_id,
            "plan_version": 0,
            "checklist": [],
            "queries_used": 0,
            "query_budget": max_rounds * 2,
            "can_approve": False,
            "can_edit": False,
            "can_stop": True,
        },
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
