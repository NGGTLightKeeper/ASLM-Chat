# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import urlparse

from pydantic import ValidationError

from .prompts import AgentDefinition, build_agent_finalize_prompt, build_agent_step_prompt
from .search_client import SearchResult, search_client
from .sandbox_adapter import sandbox_adapter
from .types import (
    ActionType,
    AgentIterationTrace,
    AgentReport,
    AgentReportDraft,
    AgentState,
    AgentStepDecision,
    AgentTaskContext,
    EvidenceItem,
    PythonObservation,
    SearchObservation,
    SourceType,
    ToolCallRecord,
    ToolCallStatus,
)

logger = logging.getLogger(__name__)


# Agent runtime

# Run one specialist through an iterative think-search-python loop
class ToolDrivenResearchAgent:
    """Execute one agent loop and turn its work into a structured report."""

    def __init__(
        self,
        definition: AgentDefinition,
        llm=None,
        search=None,
        sandbox=None,
        max_reflect_without_tool: int = 2,
        blackboard=None,
    ):
        """Initialize the runtime with shared service dependencies."""

        from .llm_client import llm_client

        self.definition = definition
        self.id = definition.id
        self.llm = llm or llm_client
        self.search = search or search_client
        self.sandbox = sandbox or sandbox_adapter
        self.max_reflect_without_tool = max_reflect_without_tool
        self.blackboard = blackboard


    # Main loop
    async def run(self, task: AgentTaskContext) -> AgentReport:
        """Run the agent until it finishes or the iteration budget is exhausted."""

        state = AgentState(task=task, objective=task.query)

        # Let the model drive the main tool loop within the configured budget.
        for iteration in range(1, task.max_iterations + 1):
            # Read blackboard signals from other agents (skip iteration 1).
            if self.blackboard is not None and iteration > 1:
                signals = await self.blackboard.read_since(
                    self.id, state.last_blackboard_read,
                )
                state.last_blackboard_read = __import__("time").time()
                if signals:
                    state.blackboard_signals_seen += len(signals)
                    bb_context = self.blackboard.summary_for_prompt(signals)
                    self._append_scratchpad(
                        state,
                        f"[Blackboard signals from other agents]\n{bb_context}",
                    )

            decision = await self._decide(state, iteration)
            report = await self._apply_decision(state, iteration, decision)

            # Publish a signal after each productive iteration.
            if self.blackboard is not None and state.evidence:
                signal = self._extract_signal_from_iteration(state, iteration)
                if signal is not None:
                    await self.blackboard.publish(signal)

            if report is not None:
                return report

        # Force a last python pass when the task still requires computed output.
        if self._should_force_python_before_finish(state):
            generated_code = await self._generate_python_code(state)
            python_observation = await self._run_python(task.max_iterations + 1, generated_code, state)
            observation = self._python_observation_summary(python_observation)
            state.iterations.append(
                AgentIterationTrace(
                    iteration=task.max_iterations + 1,
                    thought="Iteration budget was exhausted before a required python-backed result was produced. Executing forced python fallback.",
                    action=ActionType.PYTHON,
                    action_input=generated_code,
                    observation=observation,
                    confidence=0.4,
                    stop=False,
                )
            )
            self._append_scratchpad(
                state,
                f"[Iteration {task.max_iterations + 1}] Forced python fallback.\nObservation: {observation}",
            )

        return await self._finalize(state, reason="iteration_limit")


    # Model decisions
    async def _decide(self, state: AgentState, iteration: int) -> AgentStepDecision:
        """Ask the LLM for the next action in the current agent loop."""

        prompt = build_agent_step_prompt(
            agent=self.definition,
            query=state.task.query,
            scratchpad=state.scratchpad,
            evidence_summary=state.observation_summary(),
            iteration=iteration,
            max_iterations=state.task.max_iterations,
        )
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": "Choose the next action."},
        ]
        try:
            payload = await self.llm.chat_completion_json(
                messages=messages,
                temperature=self.definition.temperature,
                max_tokens=self.definition.max_tokens,
            )
            return AgentStepDecision.model_validate(payload)
        except (ValidationError, json.JSONDecodeError) as exc:
            logger.warning("[%s] Step decision parse failed: %s", self.id, exc)
        except Exception as exc:
            logger.warning("[%s] Step decision failed: %s", self.id, exc)

        return AgentStepDecision(
            thought="Decision parsing failed, ending with best available evidence.",
            confidence=0.0,
            action=ActionType.FINISH,
            action_input="",
            report={
                "summary": "The agent encountered a structured output failure and is stopping.",
                "uncertainties": ["Decision parsing failed"],
                "confidence": 0.0,
            },
        )

    async def _apply_decision(
        self,
        state: AgentState,
        iteration: int,
        decision: AgentStepDecision,
    ) -> AgentReport | None:
        """Apply one model decision and optionally return a completed report."""

        self._merge_requirements(state, decision)
        action = decision.action
        action_input = (decision.action_input or "").strip()

        # Downgrade unsupported tool requests into pure reflection.
        if action == ActionType.SEARCH and not self.definition.has_search:
            action = ActionType.REFLECT
            action_input = ""
        if action == ActionType.PYTHON and (not self.definition.has_python or not state.task.sandbox_enabled):
            action = ActionType.REFLECT
            action_input = ""

        observation = ""

        # Execute the selected tool or fallback action.
        if action == ActionType.SEARCH:
            search_observation = await self._run_search(iteration, action_input, state)
            observation = self._search_observation_summary(search_observation)
            state.reflect_streak = 0
            if search_observation.results:
                self._mark_tool_satisfied(state, ActionType.SEARCH)
        elif action == ActionType.PYTHON:
            python_observation = await self._run_python(iteration, action_input, state)
            observation = self._python_observation_summary(python_observation)
            state.reflect_streak = 0
            if python_observation.result.ok:
                self._mark_tool_satisfied(state, ActionType.PYTHON)
        elif action == ActionType.REFLECT:
            state.reflect_streak += 1
            observation = "Reflection only."
            if state.reflect_streak > self.max_reflect_without_tool and (self.definition.has_search or self.definition.has_python):
                forced_action = ActionType.SEARCH if self.definition.has_search else ActionType.PYTHON
                seed_input = state.task.query if forced_action == ActionType.SEARCH else "print('No computation requested.')"
                decision = AgentStepDecision(
                    thought=f"{decision.thought} Forced tool usage after repeated reflection.",
                    confidence=decision.confidence,
                    action=forced_action,
                    action_input=seed_input,
                    report=decision.report,
                )
                return await self._apply_decision(state, iteration, decision)
        elif action == ActionType.FINISH:
            required_search = self._requires_tool_before_finish(state, ActionType.SEARCH)
            required_python = self._requires_tool_before_finish(state, ActionType.PYTHON)
            if required_search:
                search_query = self._build_forced_search_query(state)
                search_observation = await self._run_search(iteration, search_query, state)
                observation = self._search_observation_summary(search_observation)
                if search_observation.results:
                    self._mark_tool_satisfied(state, ActionType.SEARCH)
                state.iterations.append(
                    AgentIterationTrace(
                        iteration=iteration,
                        thought=f"{decision.thought} Finish was deferred because search grounding is still required.",
                        action=ActionType.SEARCH,
                        action_input=search_query,
                        observation=observation,
                        confidence=min(decision.confidence, 0.6),
                        stop=False,
                    )
                )
                self._append_scratchpad(
                    state,
                    f"[Iteration {iteration}] Finish deferred; forced search grounding.\nObservation: {observation}",
                )
                return None
            if required_python:
                generated_code = await self._generate_python_code(state)
                python_observation = await self._run_python(iteration, generated_code, state)
                observation = self._python_observation_summary(python_observation)
                if python_observation.result.ok:
                    self._mark_tool_satisfied(state, ActionType.PYTHON)
                state.iterations.append(
                    AgentIterationTrace(
                        iteration=iteration,
                        thought=f"{decision.thought} Finish was deferred because python-backed computation is still required.",
                        action=ActionType.PYTHON,
                        action_input=generated_code,
                        observation=observation,
                        confidence=decision.confidence,
                        stop=False,
                    )
                )
                self._append_scratchpad(
                    state,
                    f"[Iteration {iteration}] Finish deferred; forced python execution.\nObservation: {observation}",
                )
                return None
            state.stop_reason = "agent_finish"
            state.report_draft = self._coerce_report_draft(decision.report)
            state.iterations.append(
                AgentIterationTrace(
                    iteration=iteration,
                    thought=decision.thought,
                    action=ActionType.FINISH,
                    action_input=action_input,
                    observation="Agent submitted final report.",
                    confidence=decision.confidence,
                    stop=True,
                )
            )
            return await self._finalize(state, reason="agent_finish")

        # Persist the iteration trace and scratchpad for later synthesis/finalization.
        state.iterations.append(
            AgentIterationTrace(
                iteration=iteration,
                thought=decision.thought,
                action=action,
                action_input=action_input,
                observation=observation,
                confidence=decision.confidence,
                stop=False,
            )
        )

        self._append_scratchpad(
            state,
            f"[Iteration {iteration}] {decision.thought}\nAction: {action.value}\nObservation: {observation}",
        )
        return None


    # Requirement tracking
    def _merge_requirements(self, state: AgentState, decision: AgentStepDecision) -> None:
        """Merge must-use tools and finish blockers into agent state."""

        for tool in decision.required_tools:
            if tool == ActionType.FINISH:
                continue
            if tool not in state.pending_required_tools:
                state.pending_required_tools.append(tool)
        for blocker in decision.finish_blockers:
            if blocker not in state.finish_blockers:
                state.finish_blockers.append(blocker)

    def _mark_tool_satisfied(self, state: AgentState, tool: ActionType) -> None:
        """Clear a required tool once a successful run has been recorded."""

        state.pending_required_tools = [item for item in state.pending_required_tools if item != tool]

    def _requires_tool_before_finish(self, state: AgentState, tool: ActionType) -> bool:
        """Return whether a specific tool must run before the agent may finish."""

        if tool == ActionType.SEARCH and not self.definition.has_search:
            return False
        if tool == ActionType.PYTHON and (not self.definition.has_python or not state.task.sandbox_enabled):
            return False
        if tool in state.pending_required_tools:
            return True
        if tool == ActionType.SEARCH:
            return self._should_force_search_before_finish(state)
        if tool == ActionType.PYTHON:
            return self._should_force_python_before_finish(state)
        return False


    # Tool execution
    async def _run_search(self, iteration: int, query: str, state: AgentState) -> SearchObservation:
        """Run the shared search client and capture evidence plus tool-call metadata."""

        if not query:
            query = state.task.query
        try:
            results = await self.search.search(query, limit=state.task.search_limit)
            evidence = [self._search_result_to_evidence(item, iteration) for item in results]
            state.evidence.extend(evidence)
            state.tool_calls.append(
                ToolCallRecord(
                    iteration=iteration,
                    action=ActionType.SEARCH,
                    input_text=query,
                    status=ToolCallStatus.SUCCESS,
                    output_summary=f"{len(evidence)} search results",
                    raw_output={"results": [item.model_dump() for item in results]},
                )
            )
            return SearchObservation(query=query, results=evidence)
        except Exception as exc:
            state.tool_calls.append(
                ToolCallRecord(
                    iteration=iteration,
                    action=ActionType.SEARCH,
                    input_text=query,
                    status=ToolCallStatus.ERROR,
                    output_summary="search failed",
                    error=str(exc),
                )
            )
            return SearchObservation(query=query, results=[])

    async def _run_python(self, iteration: int, code: str, state: AgentState) -> PythonObservation:
        """Run sandboxed Python and convert the result into evidence plus trace data."""

        if not code:
            code = "print('No code provided.')"
        result = await self.sandbox.run(code, timeout_seconds=state.task.sandbox_timeout_seconds)
        evidence = EvidenceItem(
            id=f"{self.id}-python-{iteration}",
            agent_id=self.id,
            iteration=iteration,
            source=SourceType.COMPUTE,
            title="Python execution result",
            ref="mcp-sandbox",
            note="Computation result from the sandbox runtime.",
            excerpt=(result.stdout or result.stderr or result.error or "")[:800],
            domain="mcp-sandbox",
        )
        state.evidence.append(evidence)
        status = ToolCallStatus.SUCCESS if result.ok else ToolCallStatus.ERROR
        if result.error and "timed out" in result.error.lower():
            status = ToolCallStatus.TIMEOUT
        state.tool_calls.append(
            ToolCallRecord(
                iteration=iteration,
                action=ActionType.PYTHON,
                input_text=code,
                status=status,
                output_summary=(result.stdout or result.stderr or result.error or "")[:200],
                raw_output=result.model_dump(),
                error=result.error,
            )
        )
        return PythonObservation(code=code, result=result, evidence=evidence)


    # Final report assembly
    async def _finalize(self, state: AgentState, reason: str) -> AgentReport:
        """Finalize the agent report using the current draft or a last LLM pass."""

        state.stop_reason = reason
        draft = state.report_draft
        if draft is None:
            prompt = build_agent_finalize_prompt(
                self.definition,
                query=state.task.query,
                scratchpad=state.scratchpad,
                evidence_summary=state.observation_summary(),
            )
            try:
                payload = await self.llm.chat_completion_json(
                    messages=[{"role": "system", "content": prompt}, {"role": "user", "content": "Finalize the report."}],
                    temperature=self.definition.temperature,
                    max_tokens=self.definition.max_tokens,
                )
                draft = AgentReportDraft.model_validate(payload)
            except Exception as exc:
                logger.warning("[%s] Finalize failed: %s", self.id, exc)
                draft = AgentReportDraft(
                    summary="The agent could not finalize cleanly and is returning a fallback summary.",
                    key_points=[],
                    uncertainties=["Finalization failed"],
                    confidence=0.0,
                )

        return AgentReport(
            role=self.id,
            summary=draft.summary,
            key_points=draft.key_points,
            risks=draft.risks,
            uncertainties=draft.uncertainties,
            actions=draft.actions,
            artifacts=draft.artifacts,
            confidence=draft.confidence,
            evidence=state.evidence,
            tool_calls=state.tool_calls,
            iterations=state.iterations,
            scratchpad=state.scratchpad,
            stop_reason=state.stop_reason,
            critical_verification=draft.critical_verification,
        )


    # Blackboard helpers
    def _extract_signal_from_iteration(self, state: AgentState, iteration: int):
        """Create a Signal from the most recent evidence item, if any."""

        from .blackboard import Signal

        if not state.evidence:
            return None
        latest = state.evidence[-1]
        # Determine signal type from the latest evidence.
        content = latest.note or latest.excerpt or ""
        if not content:
            return None
        signal_type = "finding"
        content_lower = content.lower()
        if any(w in content_lower for w in ("contradict", "conflict", "disagree", "incorrect")):
            signal_type = "contradiction"
        return Signal(
            agent_id=self.id,
            iteration=iteration,
            signal_type=signal_type,
            content=content[:300],
            confidence=0.5,
            references=[latest.ref] if latest.ref else [],
        )

    # Evidence helpers
    def _search_result_to_evidence(self, result: SearchResult, iteration: int) -> EvidenceItem:
        """Convert one search result into a normalized evidence record."""

        domain = urlparse(result.url).netloc
        excerpt = result.page_text[:1600] if result.page_text else result.content[:500]
        note = result.content[:240]
        if result.page_text:
            note = f"{result.content[:140]} | lightweight-read attached"
        return EvidenceItem(
            id=f"{self.id}-search-{iteration}-{abs(hash(result.url)) % 10_000}",
            agent_id=self.id,
            iteration=iteration,
            source=SourceType.SEARCH,
            title=result.title,
            ref=result.url,
            note=note,
            excerpt=excerpt,
            domain=domain,
        )

    def _append_scratchpad(self, state: AgentState, text: str) -> None:
        """Append one scratchpad entry while preserving existing notes."""

        state.scratchpad = (state.scratchpad + "\n\n" + text).strip()

    def _coerce_report_draft(self, payload: dict[str, Any] | None) -> AgentReportDraft:
        """Coerce a possibly partial payload into a valid report draft."""

        if not payload:
            return AgentReportDraft(
                summary="No final report payload was provided.",
                uncertainties=["The agent stopped without structured findings."],
                confidence=0.0,
            )
        try:
            return AgentReportDraft.model_validate(payload)
        except ValidationError:
            return AgentReportDraft(
                summary=str(payload.get("summary") or "Structured report payload was invalid."),
                key_points=[str(item) for item in payload.get("key_points", []) if str(item).strip()],
                uncertainties=["The final report payload was only partially valid."],
                confidence=float(payload.get("confidence", 0.0) or 0.0),
            )


    # Observation summaries
    def _search_observation_summary(self, observation: SearchObservation) -> str:
        """Summarize search output for the iteration scratchpad."""

        if not observation.results:
            return f"Search for '{observation.query}' returned no results."
        top = observation.results[:3]
        joined = "; ".join(item.title or item.ref for item in top)
        enriched = sum(1 for item in observation.results if item.excerpt and len(item.excerpt) > 200)
        suffix = f"; {enriched} result(s) include lightweight page text" if enriched else ""
        return f"Search for '{observation.query}' returned {len(observation.results)} results: {joined}{suffix}"

    def _python_observation_summary(self, observation: PythonObservation) -> str:
        """Summarize Python execution output for the iteration scratchpad."""

        result = observation.result
        text = result.stdout or result.stderr or result.error or "No output."
        return f"Python execution {'succeeded' if result.ok else 'failed'}: {text[:180]}"


    # Finish guards
    def _query_needs_python(self, query: str) -> bool:
        """Return whether the query likely needs a computed result."""

        # This is only a soft fallback; the primary mechanism is model-declared required tools.
        normalized = query.lower()
        keywords = (
            "count", "compute", "calculate", "ratio", "mean", "median", "average",
            "standard deviation", "std", "factorial", "sum", "difference",
            "convert", "mentions", "frequency",
            "посчитай", "вычисли", "рассчитай", "сумм", "суммар", "средн",
            "медиан", "отношен", "конверт", "перевед", "упоминан", "частот",
        )
        return any(keyword in normalized for keyword in keywords)

    def _query_needs_search_grounding(self, query: str) -> bool:
        """Return whether the query likely needs external grounding before finish."""

        # This is only a soft fallback; the primary mechanism is model-declared required tools.
        normalized = query.lower()
        keywords = (
            "compare", "comparison", "advantages", "disadvantages", "pros", "cons",
            "better", "worse", "best for", "suited", "suitable", "limitations",
            "current", "latest", "recent", "today", "why", "tradeoff",
            "сравни", "преимуществ", "недостатк", "лучше", "хуже", "подходит",
            "ограничени", "текущ", "последн", "сегодня", "почему",
        )
        return any(keyword in normalized for keyword in keywords)

    def _has_successful_search(self, state: AgentState) -> bool:
        """Return whether the agent already completed a successful search step."""

        return any(
            call.action == ActionType.SEARCH and call.status == ToolCallStatus.SUCCESS
            for call in state.tool_calls
        )

    def _should_force_search_before_finish(self, state: AgentState) -> bool:
        """Return whether a finalizing agent still needs search grounding."""

        if not self.definition.has_search:
            return False
        if not self._query_needs_search_grounding(state.task.query):
            return False
        return not self._has_successful_search(state)

    def _build_forced_search_query(self, state: AgentState) -> str:
        """Build a compact fallback query from the task text."""

        normalized = " ".join(state.task.query.split())
        return normalized[:180]

    def _has_successful_python(self, state: AgentState) -> bool:
        """Return whether the agent already completed a successful python step."""

        return any(
            call.action == ActionType.PYTHON and call.status == ToolCallStatus.SUCCESS
            for call in state.tool_calls
        )

    def _should_force_python_before_finish(self, state: AgentState) -> bool:
        """Return whether a finalizing agent still needs a computed result."""

        if not self.definition.has_python or not state.task.sandbox_enabled:
            return False
        if not self._query_needs_python(state.task.query):
            return False
        return not self._has_successful_python(state)


    # Python generation
    async def _generate_python_code(self, state: AgentState) -> str:
        """Generate fallback python code from recent evidence snippets."""

        evidence_chunks = []
        for item in state.evidence[-4:]:
            blob = item.excerpt or item.note
            if blob:
                evidence_chunks.append(blob[:1400])
        evidence_blob = "\n\n".join(evidence_chunks) or "(no external evidence)"

        prompt = f"""Write Python code only.

Task:
{state.task.query}

Available evidence text:
{evidence_blob}

Rules:
- Use only the Python standard library.
- Print the final numeric answer or counts clearly.
- If the task asks for word counts, count case-insensitively in the provided evidence text.
- Do not explain anything outside the code.
"""
        try:
            # Ask the model for code first so computed answers stay task-specific.
            code = await self.llm.chat_completion(
                messages=[{"role": "system", "content": prompt}, {"role": "user", "content": "Return Python code only."}],
                temperature=0.1,
                max_tokens=700,
            )
        except Exception:
            code = ""

        # Strip common Markdown fencing before executing the generated code.
        code = code.strip()
        if code.startswith("```"):
            code = code.strip("`")
            if code.startswith("python"):
                code = code[len("python"):].strip()
        if code:
            return code

        # Fall back to a deterministic counting snippet when generation fails.
        evidence_literal = json.dumps(evidence_blob)
        return (
            "import math\n"
            f"text = {evidence_literal}\n"
            "normalized = text.lower()\n"
            "targets = ['attention', 'token', 'embedding']\n"
            "for target in targets:\n"
            "    print(f'{target}: {normalized.count(target)}')\n"
        )


ResearchAgent = ToolDrivenResearchAgent
