# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import logging
import re

from .config import settings
from .llm_client import llm_client
from .prompts import AGENTS, get_selector_prompt
from .types import AgentSelection

logger = logging.getLogger(__name__)


# Agent selection

# Blend deterministic heuristics with optional LLM refinement
class HybridSelector:
    """Select a compact set of agents for the current query."""

    BUILD_KEYWORDS = {
        "build", "rewrite", "refactor", "implement", "architecture", "design",
        "tool", "script", "agent", "mcp", "module", "system", "pipeline",
        "code", "cli",
    }
    SECURITY_KEYWORDS = {
        "security", "secure", "privacy", "auth", "oauth", "token", "secret",
        "prompt injection", "abuse", "exploit", "vulnerability", "sandbox",
    }
    PERFORMANCE_KEYWORDS = {
        "performance", "latency", "slow", "throughput", "memory", "cpu",
        "scale", "scaling", "optimize", "optimization", "benchmark",
    }
    UX_KEYWORDS = {
        "ux", "ui", "user", "workflow", "experience", "accessibility",
        "policy", "ethics", "safe", "confusing",
    }
    CREATIVE_KEYWORDS = {
        "idea", "ideas", "brainstorm", "creative", "alternative", "alternatives",
        "unconventional", "option", "options",
    }
    HISTORIAN_KEYWORDS = {
        "compare", "comparison", "vs", "versus", "prior art", "precedent",
        "history", "others", "benchmark", "lessons learned", "tradeoff",
    }
    RETRIEVAL_KEYWORDS = {
        "find", "extract", "current", "latest", "recent", "wikipedia", "reddit",
        "youtube", "transcript", "temperature", "thread", "count", "mentions",
        "list", "page", "news",
    }
    FACT_KEYWORDS = {
        "latest", "version", "library", "framework", "vendor", "price", "date",
        "release", "released", "announced", "spec", "specs", "benchmark",
        "review", "model", "models",
    }


    # Query normalization
    def _normalize_query(self, query: str) -> str:
        """Normalize whitespace and case for keyword matching."""

        return " ".join(query.lower().split())

    def _mentions_version_like_tokens(self, query: str) -> bool:
        """Detect version-like tokens that usually imply factual grounding."""

        return bool(re.search(r"\b(v?\d+(?:\.\d+)+|20\d{2}|[A-Z]{2,}\d{2,})\b", query))


    # Deterministic selection
    def _deterministic_ids(self, query: str) -> tuple[list[str], list[str]]:
        """Build the deterministic shortlist and explain why each agent was added."""

        normalized = self._normalize_query(query)
        selected: list[str] = []
        reasons: list[str] = []
        retrieval_heavy = any(keyword in normalized for keyword in self.RETRIEVAL_KEYWORDS)

        def add(agent_id: str, reason: str) -> None:
            if agent_id not in selected and AGENTS[agent_id].enabled:
                selected.append(agent_id)
                reasons.append(reason)

        if any(keyword in normalized for keyword in self.BUILD_KEYWORDS):
            add("architect", "build-or-rewrite task")
            add("implementer", "build-or-rewrite task")

        if retrieval_heavy:
            add("implementer", "retrieval/extraction task")
            add("fact_checker", "retrieval/extraction task needs grounding")

        if any(keyword in normalized for keyword in self.SECURITY_KEYWORDS):
            add("secops", "security/privacy topic")

        if any(keyword in normalized for keyword in self.PERFORMANCE_KEYWORDS):
            add("performance", "performance/scaling topic")

        if any(keyword in normalized for keyword in self.UX_KEYWORDS):
            add("ux_ethics", "user-facing or policy topic")

        if any(keyword in normalized for keyword in self.HISTORIAN_KEYWORDS):
            add("historian", "comparison or precedent topic")

        if any(keyword in normalized for keyword in self.CREATIVE_KEYWORDS):
            add("creative", "ideation or alternatives topic")

        factual = (
            any(keyword in normalized for keyword in self.FACT_KEYWORDS)
            or self._mentions_version_like_tokens(query)
            or any(token in normalized for token in ("http://", "https://"))
        )
        if factual:
            add("fact_checker", "external factual or version-sensitive topic")

        if not selected:
            add("architect", "default architectural baseline")
            add("implementer", "default implementation baseline")

        if "historian" not in selected and any(token in normalized for token in ("compare", "vs", "versus")):
            add("historian", "explicit comparison wording")

        if "fact_checker" not in selected and any(
            token in normalized for token in ("library", "framework", "vendor", "latest")
        ):
            add("fact_checker", "software/library facts")

        # On retrieval-heavy tasks, prefer tool-capable agents over extra commentary.
        if retrieval_heavy and "architect" in selected and "implementer" in selected and len(selected) > 2:
            selected = [agent_id for agent_id in selected if agent_id != "architect"]

        return selected[: settings.max_active_agents], reasons


    # Final selection
    async def select(self, query: str, max_agents: int | None = None) -> AgentSelection:
        """Select agents with deterministic rules and optional LLM refinement."""

        max_agents = max_agents or settings.max_active_agents
        deterministic_ids, reasons = self._deterministic_ids(query)
        deterministic_ids = deterministic_ids[:max_agents]
        reasoning = "; ".join(reasons) or "deterministic defaults"

        if not settings.llm.selector_enabled:
            return AgentSelection(
                selected_agent_ids=deterministic_ids,
                deterministic_agent_ids=list(deterministic_ids),
                reasoning=reasoning,
                llm_refined=False,
            )

        available_ids = [agent_id for agent_id, agent in AGENTS.items() if agent.enabled]
        prompt = get_selector_prompt(query, deterministic_ids, available_ids, max_agents=max_agents)

        try:
            response = await llm_client.chat_completion_json(
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": "Refine the shortlist."},
                ],
                temperature=settings.llm.selector_temperature,
                max_tokens=settings.llm.selector_max_tokens,
            )
        except Exception as exc:
            logger.warning("Selector refinement failed: %s", exc)
            return AgentSelection(
                selected_agent_ids=deterministic_ids,
                deterministic_agent_ids=list(deterministic_ids),
                reasoning=reasoning,
                llm_refined=False,
            )

        proposed = [
            agent_id
            for agent_id in response.get("selected_agent_ids", [])
            if agent_id in AGENTS and AGENTS[agent_id].enabled
        ]
        proposed = proposed[:max_agents]
        if not proposed:
            proposed = deterministic_ids

        # Keep the refinement bounded so the LLM cannot discard deterministic anchors.
        if not set(deterministic_ids).issubset(proposed):
            proposed = deterministic_ids

        if len(set(proposed) - set(deterministic_ids)) > 1:
            proposed = deterministic_ids

        final_reasoning = response.get("reasoning") or reasoning
        return AgentSelection(
            selected_agent_ids=proposed,
            deterministic_agent_ids=list(deterministic_ids),
            reasoning=final_reasoning,
            llm_refined=proposed != deterministic_ids,
        )


selector = HybridSelector()
