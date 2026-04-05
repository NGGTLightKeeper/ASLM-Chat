# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

from dataclasses import dataclass, field

from .config import settings


# Agent definitions

# Describe a single Deep Think specialist
@dataclass
class AgentDefinition:
    id: str
    name: str
    emoji: str
    description: str
    specialty: str
    system_prompt: str
    priority: int = 50
    tags: list[str] = field(default_factory=list)

    @property
    def runtime(self):
        """Return runtime settings for this agent."""

        return settings.agent_runtime(self.id)

    @property
    def enabled(self) -> bool:
        """Return whether this agent is enabled."""

        return self.runtime.enabled

    @property
    def has_search(self) -> bool:
        """Return whether this agent may use search."""

        return self.runtime.has_search

    @property
    def has_python(self) -> bool:
        """Return whether this agent may use the sandbox."""

        return self.runtime.has_python

    @property
    def temperature(self) -> float:
        """Return the default sampling temperature for this agent."""

        return self.runtime.temperature

    @property
    def max_tokens(self) -> int:
        """Return the default token budget for this agent."""

        return self.runtime.max_tokens


AGENTS: dict[str, AgentDefinition] = {
    "fact_checker": AgentDefinition(
        id="fact_checker",
        name="Fact Checker",
        emoji="FC",
        description="Verifies external claims and blocks unsupported conclusions.",
        specialty="factual verification, named entities, versions, dates, product claims",
        priority=100,
        tags=["facts", "verification", "dates"],
        system_prompt=(
            "You are a skeptical verifier. Prefer retrieved evidence over memory, "
            "separate verified from unverified claims, and explicitly block inference "
            "when evidence is weak. "
            "For any numeric claim — statistics, counts, calculations, ratios — "
            "you MUST verify it by running Python code rather than computing in your head. "
            "Mental arithmetic is unreliable; the sandbox gives deterministic results."
        ),
    ),
    "secops": AgentDefinition(
        id="secops",
        name="SecOps",
        emoji="SO",
        description="Finds security, privacy, abuse, and trust risks.",
        specialty="security review, privacy risks, secrets, auth, prompt abuse",
        priority=90,
        tags=["security", "privacy", "abuse"],
        system_prompt=(
            "You are a security reviewer. Focus on abuse paths, data exposure, "
            "unsafe defaults, and concrete mitigations."
        ),
    ),
    "architect": AgentDefinition(
        id="architect",
        name="Architect",
        emoji="AR",
        description="Designs modules, interfaces, and execution flow.",
        specialty="architecture, module boundaries, interfaces, maintainability",
        priority=80,
        tags=["architecture", "design"],
        system_prompt=(
            "You are a system architect. Focus on runtime boundaries, interfaces, "
            "state flow, and durable structure."
        ),
    ),
    "implementer": AgentDefinition(
        id="implementer",
        name="Implementer",
        emoji="IM",
        description="Translates ideas into practical code and implementation steps.",
        specialty="implementation, code organization, libraries, migration steps",
        priority=80,
        tags=["implementation", "code"],
        system_prompt=(
            "You are a senior implementer. Focus on practical code paths, migration "
            "strategy, tool integration, and failure handling."
        ),
    ),
    "performance": AgentDefinition(
        id="performance",
        name="Performance",
        emoji="PF",
        description="Analyzes latency, throughput, and resource usage.",
        specialty="performance, scaling, bottlenecks, capacity",
        priority=70,
        tags=["performance", "scaling"],
        system_prompt=(
            "You are a performance engineer. Focus on throughput, bottlenecks, "
            "resource pressure, and measurable guardrails."
        ),
    ),
    "ux_ethics": AgentDefinition(
        id="ux_ethics",
        name="UX Ethics",
        emoji="UX",
        description="Represents user experience, safety, and policy concerns.",
        specialty="UX, accessibility, failure modes, ethical consequences",
        priority=50,
        tags=["ux", "policy", "ethics"],
        system_prompt=(
            "You are a UX and ethics reviewer. Focus on user workflows, confusing "
            "failure modes, trust, and usability tradeoffs."
        ),
    ),
    "creative": AgentDefinition(
        id="creative",
        name="Creative",
        emoji="CR",
        description="Suggests unconventional but concrete alternatives.",
        specialty="alternatives, ideation, speculative approaches",
        priority=40,
        tags=["creative", "alternatives"],
        system_prompt=(
            "You are a creative strategist. Suggest alternative approaches, but "
            "label speculation clearly and stay grounded in the task."
        ),
    ),
    "historian": AgentDefinition(
        id="historian",
        name="Historian",
        emoji="HS",
        description="Brings precedent, prior art, and comparison context.",
        specialty="prior art, comparisons, recurring mistakes, patterns",
        priority=45,
        tags=["precedent", "comparison"],
        system_prompt=(
            "You are a historian of systems and tools. Bring precedent, comparisons, "
            "and recurring success or failure patterns."
        ),
    ),
}


# Selector prompts

# Build the prompt used to refine deterministic agent selection
def get_selector_prompt(
    query: str,
    deterministic_ids: list[str],
    available_ids: list[str],
    max_agents: int,
) -> str:
    """Build the selector refinement prompt."""

    return f"""You are a lightweight selector refinement step for a Deep Think multi-agent swarm.

User query:
{query}

Deterministic shortlist:
{deterministic_ids}

Available agent ids:
{available_ids}

Rules:
- Keep every deterministic agent.
- You may add at most one extra agent from the available list.
- Do not exceed {max_agents} total agents.
- If the shortlist is already sufficient, return it unchanged.
- For retrieval, extraction, current-info, Reddit, YouTube, or Wikipedia tasks, prefer tool-capable agents and avoid adding non-search specialists unless they are essential.

Respond with JSON only:
{{
  "selected_agent_ids": ["agent_id"],
  "reasoning": "short reason"
}}"""


# Agent prompts

# Build the prompt for one agent loop step
def build_agent_step_prompt(
    agent: AgentDefinition,
    query: str,
    scratchpad: str,
    evidence_summary: str,
    iteration: int,
    max_iterations: int,
    blackboard_context: str = "",
) -> str:
    """Build the prompt used for one agent decision step."""

    tool_lines = ["- reflect: think without using a tool"]
    if agent.has_search:
        tool_lines.append(
            "- search: issue a compact search query; top results may include lightweight page reads, YouTube transcripts, or Reddit thread text"
        )
    if agent.has_python:
        tool_lines.append("- python: run short Python code for counting, parsing, or simulation")
    tool_lines.append("- finish: stop and submit your structured report")
    tools_text = "\n".join(tool_lines)

    return f"""You are {agent.name}, a specialist in {agent.specialty}.
{agent.system_prompt}

Task:
{query}

Current iteration: {iteration}/{max_iterations}

Scratchpad:
{scratchpad or "(empty)"}

Current evidence:
{evidence_summary}

{f"Signals from other agents:{chr(10)}{blackboard_context}{chr(10)}" if blackboard_context else ""}Allowed actions:
{tools_text}

Rules:
- Use search before making strong external factual claims when search is available.
- For factual comparisons, pros/cons questions, "best for / worse for" questions, or current-state questions, do not finish before at least one successful search when search is available.
- Compose search queries in English by default for better web coverage. Only use another language when the task is explicitly local, language-specific, or source-language-specific.
- Search may already return lightweight page content from the best URLs, so use that evidence instead of asking for a full crawler workflow.
- If the task asks to count, compute, compare numerically, or produce a numeric answer from retrieved text, do not finish before a successful python step when python is available.
- Use python only for bounded computations or tiny simulations. No package installs. Available: stdlib, numpy, beautifulsoup4, regex, ujson, python-dateutil.
- Declare any must-use tools in required_tools and explain unresolved blockers in finish_blockers.
- If enough evidence is already available, choose finish.
- Keep action_input compact. For search use plain keywords. For python return executable code only.

Respond with JSON only:
{{
  "thought": "brief reasoning",
  "confidence": 0.0,
  "action": "reflect|search|python|finish",
  "action_input": "query or code or empty string",
  "required_tools": ["search|python"],
  "finish_blockers": ["short blocker reason"],
  "report": {{
    "summary": "required only when action is finish",
    "key_points": ["..."],
    "risks": [{{"name": "...", "severity": "low|med|high", "details": "...", "mitigation": "..."}}],
    "uncertainties": ["..."],
    "actions": ["..."],
    "artifacts": {{
      "code_snippets": ["..."],
      "configs": ["..."],
      "links": ["..."]
    }},
    "confidence": 0.0,
    "critical_verification": {{
      "claims": [
        {{
          "claim": "...",
          "status": "verified|unverified|contradicted",
          "evidence": [{{"source": "official|docs|paper|vendor|blog|social|search|compute", "ref": "...", "note": "..."}}],
          "notes": "...",
          "block_inference": false
        }}
      ],
      "global_block": false
    }}
  }}
}}"""

def build_agent_finalize_prompt(
    agent: AgentDefinition,
    query: str,
    scratchpad: str,
    evidence_summary: str,
) -> str:
    """Build the prompt used when the agent needs a final report draft."""

    return f"""You are {agent.name}. The tool loop has ended.

Task:
{query}

Scratchpad:
{scratchpad or "(empty)"}

Evidence summary:
{evidence_summary}

Produce the final structured report as JSON only:
{{
  "summary": "3-5 line synthesis",
  "key_points": ["..."],
  "risks": [{{"name": "...", "severity": "low|med|high", "details": "...", "mitigation": "..."}}],
  "uncertainties": ["..."],
  "actions": ["..."],
  "artifacts": {{
    "code_snippets": ["..."],
    "configs": ["..."],
    "links": ["..."]
  }},
  "confidence": 0.0,
  "critical_verification": {{
    "claims": [
      {{
        "claim": "...",
        "status": "verified|unverified|contradicted",
        "evidence": [{{"source": "official|docs|paper|vendor|blog|social|search|compute", "ref": "...", "note": "..."}}],
        "notes": "...",
        "block_inference": false
      }}
    ],
    "global_block": false
  }}
}}"""


# Synthesis prompts

# Build the final arbiter prompt that merges all agent reports
def build_synthesis_prompt(query: str, selection_reasoning: str, agent_payload: str) -> str:
    """Build the synthesis prompt for the final Deep Think report."""

    return f"""You are the Deep Think Arbiter. Synthesize agent findings into one final report.

User query:
{query}

Selection reasoning:
{selection_reasoning}

Agent reports:
{agent_payload}

Rules:
- Only treat claims as VERIFIED when they are supported by the fact_checker or clearly source-backed evidence.
- If the fact_checker failed, timed out, or returned no useful verification, reduce confidence and prefer UNVERIFIED unless another agent clearly shows grounded evidence.
- High severity secops concerns belong in security_warnings.
- Do not emit security_warnings for general educational questions unless security is a central part of the user query or a concrete high-severity risk is directly relevant.
- Unsupported factual claims must stay UNVERIFIED.
- Preserve useful evidence-backed implementation advice and tradeoffs.

Respond with JSON only:
{{
  "executive_summary": "short synthesis",
  "detailed_points": [
    {{"content": "point", "tag": "VERIFIED|UNVERIFIED|SECURITY|TRADEOFF", "source_agents": ["agent_id"]}}
  ],
  "blocked_claims": ["..."],
  "security_warnings": ["..."],
  "recommended_actions": ["..."],
  "overall_confidence": 0.0
}}"""
