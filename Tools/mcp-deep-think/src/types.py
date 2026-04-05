# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


# Enum models

# Normalize risk severity labels
class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "med"
    HIGH = "high"

    @classmethod
    def normalize(cls, value: Any) -> str:
        if not isinstance(value, str):
            return value
        lowered = value.lower()
        if lowered in {"medium", "med", "moderate"}:
            return cls.MEDIUM.value
        if lowered in {"high", "critical", "blocking"}:
            return cls.HIGH.value
        if lowered in {"low", "info", "minor"}:
            return cls.LOW.value
        return lowered


# Normalize claim verification labels
class VerificationStatus(str, Enum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    CONTRADICTED = "contradicted"

    @classmethod
    def normalize(cls, value: Any) -> str:
        if not isinstance(value, str):
            return value
        lowered = value.lower()
        if lowered == "unknown":
            return cls.UNVERIFIED.value
        return lowered


# Evidence source categories
class SourceType(str, Enum):
    OFFICIAL = "official"
    PAPER = "paper"
    DOCS = "docs"
    VENDOR = "vendor"
    BLOG = "blog"
    SOCIAL = "social"
    SEARCH = "search"
    COMPUTE = "compute"
    INTERNAL = "internal"


# Agent action categories
class ActionType(str, Enum):
    REFLECT = "reflect"
    SEARCH = "search"
    PYTHON = "python"
    FINISH = "finish"


# Tool execution statuses
class ToolCallStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"


# Final synthesis tags
class SynthesisTag(str, Enum):
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    SECURITY = "SECURITY"
    TRADEOFF = "TRADEOFF"


# Evidence and verification models

# Store one normalized evidence item
class EvidenceItem(BaseModel):
    id: str
    agent_id: str
    iteration: int
    source: SourceType
    title: str = ""
    ref: str = ""
    note: str = ""
    excerpt: str = ""
    domain: str = ""


# Store one evidence reference for a critical claim
class ClaimEvidence(BaseModel):
    source: SourceType
    ref: str
    note: str

    @field_validator("source", mode="before")
    @classmethod
    def normalize_source(cls, value: Any) -> Any:
        if isinstance(value, SourceType):
            return value
        if not isinstance(value, str):
            return SourceType.SEARCH.value
        lowered = value.lower().strip()
        for member in SourceType:
            if member.value == lowered:
                return lowered
        if "official" in lowered:
            return SourceType.OFFICIAL.value
        if "doc" in lowered:
            return SourceType.DOCS.value
        if "paper" in lowered or "study" in lowered:
            return SourceType.PAPER.value
        if "social" in lowered or "reddit" in lowered or "twitter" in lowered or "x.com" in lowered:
            return SourceType.SOCIAL.value
        if "compute" in lowered or "python" in lowered:
            return SourceType.COMPUTE.value
        return SourceType.SEARCH.value


# Store one critical claim and its verification state
class Claim(BaseModel):
    claim: str
    status: VerificationStatus
    evidence: list[ClaimEvidence] = Field(default_factory=list)
    notes: str = ""
    block_inference: bool = False

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, value: Any) -> Any:
        return VerificationStatus.normalize(value)


# Store the verification block for an agent report
class CriticalVerification(BaseModel):
    claims: list[Claim] = Field(default_factory=list)
    global_block: bool = False


# Store one identified risk
class Risk(BaseModel):
    name: str
    severity: Severity
    details: str
    mitigation: str | None = None

    @field_validator("severity", mode="before")
    @classmethod
    def normalize_severity(cls, value: Any) -> Any:
        return Severity.normalize(value)


# Store report artifacts
class Artifacts(BaseModel):
    code_snippets: list[str] = Field(default_factory=list)
    configs: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)

    @field_validator("code_snippets", "configs", "links", mode="before")
    @classmethod
    def ensure_str_list(cls, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        result: list[str] = []
        for item in value:
            result.append(str(item))
        return result


# Agent loop models

# Record one tool call made by an agent
class ToolCallRecord(BaseModel):
    iteration: int
    action: ActionType
    input_text: str = ""
    status: ToolCallStatus
    output_summary: str = ""
    raw_output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


# Record one agent iteration
class AgentIterationTrace(BaseModel):
    iteration: int
    thought: str = ""
    action: ActionType
    action_input: str = ""
    observation: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    stop: bool = False


# Record one model decision inside the agent loop
class AgentStepDecision(BaseModel):
    thought: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    action: ActionType
    action_input: str = ""
    required_tools: list[ActionType] = Field(default_factory=list)
    finish_blockers: list[str] = Field(default_factory=list)
    report: dict[str, Any] | None = None

    @field_validator("required_tools", mode="before")
    @classmethod
    def normalize_required_tools(cls, value: Any) -> list[Any]:
        if value is None:
            return []
        if not isinstance(value, list):
            value = [value]
        normalized: list[Any] = []
        valid = {member.value for member in ActionType if member != ActionType.FINISH}
        for item in value:
            if isinstance(item, ActionType):
                if item != ActionType.FINISH:
                    normalized.append(item.value)
                continue
            if not isinstance(item, str):
                continue
            lowered = item.lower().strip()
            if lowered in valid:
                normalized.append(lowered)
        return normalized

    @field_validator("finish_blockers", mode="before")
    @classmethod
    def normalize_finish_blockers(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            value = [value]
        return [str(item).strip() for item in value if str(item).strip()]


# Agent report models

# Store the draft report generated by one agent
class AgentReportDraft(BaseModel):
    summary: str
    key_points: list[str] = Field(default_factory=list)
    risks: list[Risk] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    artifacts: Artifacts = Field(default_factory=Artifacts)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    critical_verification: CriticalVerification | None = None


# Store the final report emitted by one agent
class AgentReport(BaseModel):
    role: str
    summary: str
    key_points: list[str] = Field(default_factory=list)
    risks: list[Risk] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    artifacts: Artifacts = Field(default_factory=Artifacts)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    iterations: list[AgentIterationTrace] = Field(default_factory=list)
    scratchpad: str = ""
    stop_reason: str = ""
    critical_verification: CriticalVerification | None = None

    @field_validator("risks", mode="before")
    @classmethod
    def normalize_risk_strings(cls, value: Any) -> list[Any]:
        if not isinstance(value, list):
            return []
        normalized: list[Any] = []
        for item in value:
            if isinstance(item, str):
                normalized.append(
                    {
                        "name": item[:80] or "Reported risk",
                        "severity": "med",
                        "details": item,
                    }
                )
            else:
                normalized.append(item)
        return normalized


# Selection and synthesis models

# Store the selected agent ids for a run
class AgentSelection(BaseModel):
    selected_agent_ids: list[str] = Field(default_factory=list, min_length=1)
    reasoning: str = ""
    deterministic_agent_ids: list[str] = Field(default_factory=list)
    llm_refined: bool = False


# Store one synthesized point in the final report
class SynthesizedPoint(BaseModel):
    content: str
    tag: SynthesisTag
    source_agents: list[str] = Field(default_factory=list)

    @field_validator("tag", mode="before")
    @classmethod
    def normalize_tag(cls, value: Any) -> str:
        if isinstance(value, SynthesisTag):
            return value.value
        if not isinstance(value, str):
            return SynthesisTag.UNVERIFIED.value
        parts = [part.strip().upper() for part in value.split("|")]
        valid = {member.value for member in SynthesisTag}
        for part in parts:
            if part in valid:
                return part
        return SynthesisTag.UNVERIFIED.value


# Store the persisted final report
class FinalReport(BaseModel):
    query: str
    task_id: str = ""
    profile: str = ""
    executive_summary: str
    detailed_points: list[SynthesizedPoint] = Field(default_factory=list)
    blocked_claims: list[str] = Field(default_factory=list)
    security_warnings: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    participating_agents: list[str] = Field(default_factory=list)
    overall_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    raw_agent_reports: list[AgentReport] = Field(default_factory=list)
    selection_reasoning: str = ""
    output_dir: str = ""


# Store the arbiter output before final report assembly
class SynthesisResponse(BaseModel):
    executive_summary: str
    detailed_points: list[SynthesizedPoint] = Field(default_factory=list)
    blocked_claims: list[str] = Field(default_factory=list)
    security_warnings: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    overall_confidence: float = Field(default=0.5, ge=0.0, le=1.0)


# Trace models

# Store one run event
class RunEvent(BaseModel):
    event: str
    payload: dict[str, Any] = Field(default_factory=dict)


# Store the execution trace for a run
class RunTrace(BaseModel):
    task_id: str
    query: str
    profile: str
    selected_agents: list[str] = Field(default_factory=list)
    selection_reasoning: str = ""
    events: list[RunEvent] = Field(default_factory=list)
    final_report: FinalReport | None = None


# Tool observation models

# Store search output returned to the agent
class SearchObservation(BaseModel):
    query: str
    results: list[EvidenceItem] = Field(default_factory=list)


# Store raw sandbox execution output
class PythonExecutionResult(BaseModel):
    ok: bool
    stdout: str = ""
    stderr: str = ""
    error: str | None = None
    elapsed_ms: int = 0
    truncated: bool = False


# Store python output plus the generated evidence item
class PythonObservation(BaseModel):
    code: str
    result: PythonExecutionResult
    evidence: EvidenceItem | None = None


# Agent runtime context
class AgentTaskContext(BaseModel):
    query: str
    profile: str
    task_id: str
    max_iterations: int
    sandbox_enabled: bool
    sandbox_timeout_seconds: int = 20
    search_limit: int


# Mutable state carried across agent iterations
class AgentState(BaseModel):
    task: AgentTaskContext
    objective: str
    scratchpad: str = ""
    evidence: list[EvidenceItem] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    iterations: list[AgentIterationTrace] = Field(default_factory=list)
    reflect_streak: int = 0
    stop_reason: str = ""
    report_draft: AgentReportDraft | None = None
    pending_required_tools: list[ActionType] = Field(default_factory=list)
    finish_blockers: list[str] = Field(default_factory=list)
    last_blackboard_read: float = 0.0
    blackboard_signals_seen: int = 0

    def observation_summary(self) -> str:
        """Build a short evidence summary for the next agent prompt."""

        snippets: list[str] = []
        for item in self.evidence[-6:]:
            if item.source == SourceType.SEARCH and item.excerpt:
                excerpt = item.excerpt[:260].replace("\n", " ")
                snippets.append(f"{item.title or item.ref} | {excerpt}")
                continue
            pieces = [item.title or item.ref, item.note or item.excerpt]
            snippets.append(" | ".join(part for part in pieces if part))
        return "\n".join(f"- {snippet}" for snippet in snippets) or "(no evidence yet)"

    @model_validator(mode="after")
    def ensure_objective(self) -> "AgentState":
        """Backfill the objective from the task query when needed."""

        if not self.objective:
            self.objective = self.task.query
        return self
