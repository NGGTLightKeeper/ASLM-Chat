# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Local run artifacts for agentic deep research."""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from services.deep_research.models import ResearchSession


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _slug(text: str, limit: int = 48) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", text.strip())[:limit].strip("_")
    return cleaned or "research"


def _json_default(value: Any) -> str:
    return str(value)


def persist_run_artifacts(session: ResearchSession, report: str) -> Path:
    """Write a compact, non-COT trace for one research run and return its directory."""

    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_dir = _repo_root() / "logs" / "deep_research" / "agentic" / f"{stamp}_{_slug(session.question)}"
    run_dir.mkdir(parents=True, exist_ok=True)

    (run_dir / "report.md").write_text(report, encoding="utf-8")

    summary = {
        "question": session.question,
        "elapsed_sec": round(session.elapsed, 2),
        "sources": len(session.source_pool),
        "reads": len(session.read_artifacts),
        "tool_calls": len(session.tool_trace),
        "search_calls": session.search_calls,
        "read_calls": session.read_calls,
        "python_calls": session.python_calls,
        "site_map_calls": session.site_map_calls,
        "import_file_calls": session.import_file_calls,
        "errors": list(session.errors),
        "final_brief": asdict(session.final_brief) if session.final_brief else None,
        "config": asdict(session.config),
    }
    (run_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )

    trace = {
        "tool_trace": [asdict(item) for item in session.tool_trace],
        "sources": [asdict(item) for item in session.source_pool],
        "read_artifacts": [asdict(item) for item in session.read_artifacts],
        "console_outputs": list(session.console_outputs),
    }
    (run_dir / "trace.json").write_text(
        json.dumps(trace, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )

    reflection_lines = ["# Reflection Log", ""]
    if session.claims:
        reflection_lines.extend(["## Claims", *[f"- {item}" for item in session.claims], ""])
    if session.gaps:
        reflection_lines.extend(["## Gaps", *[f"- {item}" for item in session.gaps], ""])
    if session.reflection_log:
        reflection_lines.append("## Notes")
        reflection_lines.extend(f"- {item}" for item in session.reflection_log)
    (run_dir / "reflection.md").write_text("\n".join(reflection_lines).strip() + "\n", encoding="utf-8")

    return run_dir
