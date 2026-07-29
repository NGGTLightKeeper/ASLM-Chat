"""Application-level Deep Research service.

Deep Research is a first-class chat mode, not a model-selectable MCP tool.  The
orchestrator still reuses the existing isolated research implementation and its
web/sandbox dependencies, but callers enter through this module instead of the
tool registry.
"""

from __future__ import annotations

from typing import Any, Mapping

from . import control


def _implementation():
    # Avoid loading model and sandbox integrations during ordinary chat startup.
    from . import runner

    return runner


def prepare_research(topic: str, *, instructions: str = "", max_rounds: int = 6) -> dict[str, Any]:
    """Create the durable session before the long-running response starts."""

    clean_topic = str(topic or "").strip()
    if not clean_topic:
        raise ValueError("Deep research requires a non-empty topic.")
    try:
        rounds = min(25, max(2, int(max_rounds or 6)))
    except (TypeError, ValueError):
        rounds = 6

    session_id = control.new_session_id()
    arguments = {
        "topic": clean_topic,
        "instructions": str(instructions or "").strip(),
        "max_rounds": rounds,
        "session_id": session_id,
        "approval_timeout_s": 900,
        "timeout_s": 3600,
    }
    tool_ui = {
        "kind": "deep_research",
        "status": "planning",
        "topic": clean_topic,
        "session_id": session_id,
        "plan_version": 0,
        "checklist": [],
        "queries_used": 0,
        "query_budget": rounds * 2,
        "can_approve": False,
        "can_edit": False,
        "can_stop": True,
    }
    control.create_session(
        session_id,
        topic=clean_topic,
        extra={
            "status": "planning",
            "phase": "planning",
            "query_budget": rounds * 2,
            "can_approve": False,
            "can_edit": False,
            "can_stop": True,
        },
    )
    return {"arguments": arguments, "tool_ui": tool_ui}


def run_research(arguments: Mapping[str, Any], context: Mapping[str, Any]) -> dict[str, Any]:
    """Run the existing deterministic orchestrator through the app service contract."""

    return _implementation().run_deep_research(arguments, context)
