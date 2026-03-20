# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .config import settings
from .types import FinalReport, RunTrace


# Artifact writing

# Persist Deep Think outputs for a single task
class ArtifactWriter:
    """Write task artifacts into the configured output directory."""

    def __init__(self, task_id: str):
        """Prepare the task output directory."""

        self.task_id = task_id
        self.output_dir = settings.output_root / task_id
        self.output_dir.mkdir(parents=True, exist_ok=True)


    # Write JSON artifacts
    def write_report_json(self, report: FinalReport) -> Path:
        """Write the final report as JSON."""

        path = self.output_dir / "report.json"
        path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        return path

    def write_trace_json(self, trace: RunTrace) -> Path:
        """Write the execution trace as JSON."""

        path = self.output_dir / "trace.json"
        path.write_text(trace.model_dump_json(indent=2), encoding="utf-8")
        return path

    def write_events_jsonl(self, trace: RunTrace) -> Path | None:
        """Write trace events as JSONL when enabled in settings."""

        if not settings.output.write_events_jsonl:
            return None

        path = self.output_dir / "events.jsonl"
        with path.open("w", encoding="utf-8") as handle:
            for event in trace.events:
                handle.write(json.dumps(event.model_dump(), ensure_ascii=False) + "\n")

        return path


    # Write text artifacts
    def write_report_markdown(self, report: FinalReport, include_raw_reports: bool) -> Path | None:
        """Write the final report as Markdown when enabled in settings."""

        if not settings.output.write_markdown:
            return None

        lines = [
            "# Deep Think Report",
            "",
            f"Task ID: `{report.task_id}`",
            f"Profile: `{report.profile}`",
            "",
            "## Query",
            report.query,
            "",
            "## Executive Summary",
            report.executive_summary,
            "",
            "## Detailed Findings",
        ]

        for point in report.detailed_points:
            sources = ", ".join(point.source_agents) if point.source_agents else "unknown"
            lines.append(f"- [{point.tag.value}] {point.content} ({sources})")

        if report.blocked_claims:
            lines.extend(["", "## Blocked Claims"])
            lines.extend(f"- {claim}" for claim in report.blocked_claims)

        if report.security_warnings:
            lines.extend(["", "## Security Warnings"])
            lines.extend(f"- {warning}" for warning in report.security_warnings)

        if report.recommended_actions:
            lines.extend(["", "## Recommended Actions"])
            lines.extend(f"- {action}" for action in report.recommended_actions)

        lines.extend(["", f"Overall Confidence: `{report.overall_confidence:.0%}`"])

        # Append raw agent reports only for full report mode.
        if include_raw_reports and report.raw_agent_reports:
            lines.extend(["", "## Raw Agent Reports"])
            for raw in report.raw_agent_reports:
                lines.extend(["", f"### {raw.role}", raw.summary])
                if raw.key_points:
                    lines.extend(f"- {point}" for point in raw.key_points)
                if raw.actions:
                    lines.append("")
                    lines.append("Actions:")
                    lines.extend(f"- {action}" for action in raw.actions)

        path = self.output_dir / "report.md"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path


# Task id helpers

# Generate a timestamped task id
def generate_task_id(prefix: str = "deepthink") -> str:
    """Generate a stable task identifier for a Deep Think run."""

    return f"{prefix}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
