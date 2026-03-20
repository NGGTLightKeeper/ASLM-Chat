# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import asyncio
import json
import logging
from statistics import mean

from pydantic import ValidationError

from .agent import ResearchAgent
from .artifacts import ArtifactWriter, generate_task_id
from .config import settings
from .llm_client import llm_client
from .prompts import AGENTS, build_synthesis_prompt
from .sandbox_adapter import sandbox_adapter
from .search_client import search_client
from .selector import selector
from .types import (
    AgentReport,
    AgentSelection,
    AgentTaskContext,
    FinalReport,
    RunEvent,
    RunTrace,
    Severity,
    SynthesisResponse,
    SynthesisTag,
    SynthesizedPoint,
    ToolCallStatus,
    VerificationStatus,
)

logger = logging.getLogger(__name__)


# Orchestration engine

# Coordinate selection, agent execution, synthesis, and artifact writing
class DeepThinkEngine:
    """Run the full Deep Think workflow for one user query."""

    def __init__(self, llm=None, search=None, sandbox=None):
        """Store shared service dependencies and lazily cached agents."""

        self.llm = llm or llm_client
        self.search = search or search_client
        self.sandbox = sandbox or sandbox_adapter
        self._agents_cache: dict[str, ResearchAgent] = {}


    # Confidence helpers
    def _has_grounded_evidence(self, report: AgentReport) -> bool:
        """Return whether a report contains grounded evidence or verified claims."""

        if report.critical_verification:
            for claim in report.critical_verification.claims:
                if claim.status == VerificationStatus.VERIFIED and claim.evidence:
                    return True
        return bool(report.evidence or report.tool_calls)

    def _confidence_penalty(self, reports: list[AgentReport]) -> float:
        """Compute a bounded confidence penalty for unhealthy agent runs."""

        penalty = 0.0
        fact_checker = next((report for report in reports if report.role == "fact_checker"), None)
        if fact_checker and fact_checker.confidence <= 0.05:
            penalty += 0.2
        if any(report.stop_reason in {"timeout", "error"} for report in reports):
            penalty += 0.1
        return min(penalty, 0.45)

    def _profile_value(self, profile_name: str, attr: str, default):
        """Resolve a profile override with a fallback default."""

        profile = settings.get_profile(profile_name)
        value = getattr(profile, attr)
        return default if value is None else value


    # Agent lifecycle
    def _get_agent(self, agent_id: str) -> ResearchAgent:
        """Return a cached agent instance for the requested definition."""

        if agent_id not in self._agents_cache:
            definition = AGENTS[agent_id]
            self._agents_cache[agent_id] = ResearchAgent(
                definition=definition,
                llm=self.llm,
                search=self.search,
                sandbox=self.sandbox,
                max_reflect_without_tool=settings.limits.max_reflect_without_tool,
            )
        return self._agents_cache[agent_id]

    async def _run_one_agent(
        self,
        agent_id: str,
        query: str,
        profile_name: str,
        task_id: str,
    ) -> AgentReport:
        """Run one agent with profile-specific runtime limits."""

        max_iterations = self._profile_value(
            profile_name,
            "max_iterations_per_agent",
            settings.limits.max_iterations_per_agent,
        )
        search_limit = self._profile_value(
            profile_name,
            "search_results_limit",
            settings.search.results_limit,
        )
        context = AgentTaskContext(
            query=query,
            profile=profile_name,
            task_id=task_id,
            max_iterations=max_iterations,
            sandbox_enabled=settings.sandbox.enabled and AGENTS[agent_id].has_python,
            sandbox_timeout_seconds=self._profile_value(
                profile_name,
                "sandbox_timeout_seconds",
                settings.sandbox.timeout_seconds,
            ),
            search_limit=search_limit,
        )
        timeout_seconds = self._profile_value(
            profile_name,
            "per_agent_timeout_seconds",
            settings.limits.per_agent_timeout_seconds,
        )
        agent = self._get_agent(agent_id)
        try:
            return await asyncio.wait_for(agent.run(context), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            # Timeouts become explicit low-confidence reports instead of aborting the whole run.
            return AgentReport(
                role=agent_id,
                summary=f"Agent timed out after {timeout_seconds} seconds.",
                uncertainties=["Execution timed out"],
                confidence=0.0,
                stop_reason="timeout",
            )
        except Exception as exc:  # pragma: no cover - defensive runtime behavior
            logger.exception("Agent %s failed", agent_id)
            return AgentReport(
                role=agent_id,
                summary=f"Agent failed with error: {exc}",
                uncertainties=["Execution failed"],
                confidence=0.0,
                stop_reason="error",
            )

    async def _execute_agents(
        self,
        selection: AgentSelection,
        query: str,
        profile_name: str,
        task_id: str,
        trace: RunTrace,
    ) -> list[AgentReport]:
        """Run all selected agents concurrently and append a trace event."""

        tasks = [
            self._run_one_agent(agent_id, query, profile_name, task_id)
            for agent_id in selection.selected_agent_ids
        ]
        reports = await asyncio.gather(*tasks)
        trace.events.append(
            RunEvent(
                event="agents_completed",
                payload={
                    "agents": [
                        {
                            "role": report.role,
                            "confidence": report.confidence,
                            "stop_reason": report.stop_reason,
                            "tool_calls": len(report.tool_calls),
                        }
                        for report in reports
                    ]
                },
            )
        )
        return reports


    # Synthesis helpers
    def _payload_for_synthesis(self, reports: list[AgentReport]) -> str:
        """Convert agent reports into the JSON payload passed to the arbiter."""

        payload = []
        for report in reports:
            payload.append(
                {
                    "role": report.role,
                    "summary": report.summary,
                    "key_points": report.key_points,
                    "risks": [risk.model_dump() for risk in report.risks],
                    "uncertainties": report.uncertainties,
                    "actions": report.actions,
                    "confidence": report.confidence,
                    "critical_verification": (
                        report.critical_verification.model_dump() if report.critical_verification else None
                    ),
                    "tool_calls": [call.model_dump() for call in report.tool_calls],
                    "evidence": [item.model_dump() for item in report.evidence],
                }
            )
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def _normalize_synthesis(self, synthesis: SynthesisResponse, reports: list[AgentReport]) -> SynthesisResponse:
        """Downgrade overconfident synthesis points when grounding is weak."""

        fact_checker = next((report for report in reports if report.role == "fact_checker"), None)
        fact_checker_healthy = bool(fact_checker and fact_checker.confidence > 0.05 and self._has_grounded_evidence(fact_checker))
        grounded_roles = {report.role for report in reports if self._has_grounded_evidence(report)}

        for point in synthesis.detailed_points:
            if point.tag != SynthesisTag.VERIFIED:
                continue
            source_roles = set(point.source_agents)
            if fact_checker_healthy and "fact_checker" in source_roles:
                continue
            if source_roles and source_roles.issubset(grounded_roles):
                point.tag = SynthesisTag.TRADEOFF
            else:
                point.tag = SynthesisTag.UNVERIFIED

        if not fact_checker_healthy:
            synthesis.overall_confidence = max(0.0, synthesis.overall_confidence - 0.2)

        synthesis.overall_confidence = max(0.0, min(1.0, synthesis.overall_confidence - self._confidence_penalty(reports)))
        return synthesis

    def _fallback_synthesis(self, query: str, reports: list[AgentReport]) -> SynthesisResponse:
        """Build a deterministic synthesis when the arbiter response is unavailable."""

        detailed_points: list[SynthesizedPoint] = []
        blocked_claims: list[str] = []
        security_warnings: list[str] = []
        recommended_actions: list[str] = []

        # Reuse the role semantics so the fallback still preserves verification intent.
        for report in reports:
            tag = SynthesisTag.TRADEOFF
            if report.role == "fact_checker":
                tag = SynthesisTag.VERIFIED
                if report.critical_verification:
                    for claim in report.critical_verification.claims:
                        if claim.status != VerificationStatus.VERIFIED and claim.block_inference:
                            blocked_claims.append(claim.claim)
            elif report.role == "secops":
                tag = SynthesisTag.SECURITY
                for risk in report.risks:
                    if risk.severity == Severity.HIGH:
                        security_warnings.append(f"{risk.name}: {risk.details}")
            elif report.role in {"architect", "implementer", "performance"}:
                tag = SynthesisTag.TRADEOFF
            else:
                tag = SynthesisTag.UNVERIFIED

            for point in report.key_points[:3]:
                detailed_points.append(
                    SynthesizedPoint(
                        content=point,
                        tag=tag,
                        source_agents=[report.role],
                    )
                )
            recommended_actions.extend(report.actions)

        if not detailed_points:
            detailed_points = [
                SynthesizedPoint(
                    content=report.summary,
                    tag=SynthesisTag.UNVERIFIED,
                    source_agents=[report.role],
                )
                for report in reports
            ]

        executive_summary = " ".join(report.summary for report in reports[:3]) or "No agents completed successfully."
        overall_confidence = mean(report.confidence for report in reports) if reports else 0.0
        overall_confidence = max(0.0, min(1.0, overall_confidence - self._confidence_penalty(reports)))

        return SynthesisResponse(
            executive_summary=executive_summary,
            detailed_points=detailed_points,
            blocked_claims=list(dict.fromkeys(blocked_claims)),
            security_warnings=list(dict.fromkeys(security_warnings)),
            recommended_actions=list(dict.fromkeys(recommended_actions))[:8],
            overall_confidence=overall_confidence,
        )

    async def _synthesize(
        self,
        query: str,
        selection: AgentSelection,
        reports: list[AgentReport],
        profile_name: str,
        trace: RunTrace,
    ) -> SynthesisResponse:
        """Request the final synthesis and fall back to deterministic merging on failure."""

        if not reports:
            return SynthesisResponse(
                executive_summary="No agents completed successfully.",
                overall_confidence=0.0,
            )

        prompt = build_synthesis_prompt(
            query=query,
            selection_reasoning=selection.reasoning,
            agent_payload=self._payload_for_synthesis(reports),
        )
        try:
            payload = await self.llm.chat_completion_json(
                messages=[{"role": "system", "content": prompt}, {"role": "user", "content": "Synthesize the final report."}],
                temperature=settings.llm.synthesis_temperature,
                max_tokens=self._profile_value(
                    profile_name,
                    "synthesis_max_tokens",
                    settings.llm.synthesis_max_tokens,
                ),
            )
            synthesis = SynthesisResponse.model_validate(payload)
            synthesis = self._normalize_synthesis(synthesis, reports)
            trace.events.append(
                RunEvent(
                    event="synthesis_completed",
                    payload={
                        "detailed_points": len(synthesis.detailed_points),
                        "confidence": synthesis.overall_confidence,
                    },
                )
            )
            return synthesis
        except (ValidationError, json.JSONDecodeError) as exc:
            logger.warning("Synthesis parse failed: %s", exc)
        except Exception as exc:
            logger.warning("Synthesis failed: %s", exc)

        fallback = self._fallback_synthesis(query, reports)
        trace.events.append(RunEvent(event="synthesis_fallback", payload={"reason": "llm_failure"}))
        return fallback


    # Public run flow
    async def run(
        self,
        query: str,
        mode: str = "full",
        profile: str | None = None,
        task_id: str | None = None,
    ) -> FinalReport:
        """Execute the full Deep Think pipeline and persist artifacts."""

        profile_name = profile or settings.mcp.default_profile
        run_task_id = task_id or generate_task_id()
        writer = ArtifactWriter(run_task_id)
        trace = RunTrace(task_id=run_task_id, query=query, profile=profile_name)

        max_agents = self._profile_value(
            profile_name,
            "max_active_agents",
            settings.limits.max_active_agents,
        )

        selection = await selector.select(query, max_agents=max_agents)
        trace.selected_agents = list(selection.selected_agent_ids)
        trace.selection_reasoning = selection.reasoning
        trace.events.append(
            RunEvent(
                event="selection_completed",
                payload=selection.model_dump(),
            )
        )

        reports = await self._execute_agents(selection, query, profile_name, run_task_id, trace)
        synthesis = await self._synthesize(query, selection, reports, profile_name, trace)

        final_report = FinalReport(
            query=query,
            task_id=run_task_id,
            profile=profile_name,
            executive_summary=synthesis.executive_summary,
            detailed_points=synthesis.detailed_points,
            blocked_claims=synthesis.blocked_claims,
            security_warnings=synthesis.security_warnings,
            recommended_actions=synthesis.recommended_actions,
            participating_agents=[report.role for report in reports],
            overall_confidence=synthesis.overall_confidence,
            raw_agent_reports=reports,
            selection_reasoning=selection.reasoning,
            output_dir=str(writer.output_dir),
        )

        trace.final_report = final_report
        writer.write_report_json(final_report)
        writer.write_trace_json(trace)
        writer.write_events_jsonl(trace)
        writer.write_report_markdown(final_report, include_raw_reports=mode == "full")
        return final_report

    def format_report_for_llm(self, report: FinalReport, include_raw_reports: bool = False) -> str:
        """Format the final report as a plain-text block for MCP or CLI output."""

        lines = [
            "=" * 60,
            "DEEP THINK: TOOL-DRIVEN RESEARCH SWARM",
            "=" * 60,
            "",
            f"QUERY: {report.query}",
            f"TASK ID: {report.task_id}",
            f"PROFILE: {report.profile}",
            "",
            "EXECUTIVE SUMMARY:",
            report.executive_summary,
            "",
        ]

        if report.blocked_claims:
            lines.append("BLOCKED CLAIMS:")
            lines.extend(f"  - {claim}" for claim in report.blocked_claims)
            lines.append("")

        if report.security_warnings:
            lines.append("SECURITY WARNINGS:")
            lines.extend(f"  - {warning}" for warning in report.security_warnings)
            lines.append("")

        lines.append("DETAILED FINDINGS:")
        for point in report.detailed_points:
            sources = ", ".join(point.source_agents) if point.source_agents else "unknown"
            lines.append(f"  [{point.tag.value}] {point.content}")
            lines.append(f"       (sources: {sources})")
        lines.append("")

        if report.recommended_actions:
            lines.append("RECOMMENDED ACTIONS:")
            lines.extend(f"  - {action}" for action in report.recommended_actions)
            lines.append("")

        lines.append(f"Overall Confidence: {report.overall_confidence:.0%}")
        lines.append(f"Participating Agents: {', '.join(report.participating_agents)}")
        lines.append(f"Artifacts: {report.output_dir}")

        if include_raw_reports and report.raw_agent_reports:
            lines.extend(["", "=" * 60, "RAW AGENT REPORTS", "=" * 60])
            for raw in report.raw_agent_reports:
                lines.extend(
                    [
                        "",
                        f"--- {raw.role} (confidence: {raw.confidence:.2f}, stop: {raw.stop_reason}) ---",
                        f"Summary: {raw.summary}",
                    ]
                )
                if raw.key_points:
                    lines.append("Key Points:")
                    lines.extend(f"  - {point}" for point in raw.key_points)
                if raw.tool_calls:
                    lines.append("Tool Calls:")
                    for call in raw.tool_calls:
                        status = call.status.value if isinstance(call.status, ToolCallStatus) else str(call.status)
                        lines.append(f"  - [{status}] {call.action.value}: {call.output_summary}")

        return "\n".join(lines)


orchestrator = DeepThinkEngine()
