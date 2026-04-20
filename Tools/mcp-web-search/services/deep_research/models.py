# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Data models for the agentic deep research runtime."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal


ActionName = Literal["reflect", "web_search", "academic_search", "read_page", "site_map", "python", "import_web_file", "finish"]


@dataclass
class SourceCard:
    id: str
    url: str
    title: str
    snippet: str = ""
    trust_tier: str = "?"
    score: float = 0.0
    engine: str = ""
    read_artifact_ids: list[str] = field(default_factory=list)


@dataclass
class ReadArtifact:
    id: str
    source_id: str
    url: str
    mode: str
    content: str
    chunks: list[str] = field(default_factory=list)
    query: str = ""
    char_count: int = 0
    truncated: bool = False


@dataclass
class ToolTrace:
    step: int
    action: str
    input: dict[str, Any]
    status: str
    output_summary: str
    elapsed_ms: int = 0
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class PythonResult:
    ok: bool
    stdout: str = ""
    stderr: str = ""
    error: str | None = None
    elapsed_ms: int = 0
    truncated: bool = False


@dataclass
class AgentDecision:
    thought: str
    action: ActionName
    action_input: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.5


@dataclass
class ResearchBrief:
    summary: str = ""
    claims: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    used_source_ids: list[str] = field(default_factory=list)
    recommended_followups: list[str] = field(default_factory=list)
    synthesis_ready: bool = True


@dataclass
class ResearchSession:
    question: str
    config: Any
    started_at: float = field(default_factory=time.time)
    source_pool: list[SourceCard] = field(default_factory=list)
    read_artifacts: list[ReadArtifact] = field(default_factory=list)
    tool_trace: list[ToolTrace] = field(default_factory=list)
    reflection_log: list[str] = field(default_factory=list)
    claims: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    console_outputs: list[str] = field(default_factory=list)
    final_brief: ResearchBrief | None = None
    errors: list[str] = field(default_factory=list)

    # Overdrive: ephemeral Docker sandbox attached on start, destroyed on stop.
    sandbox: Any = field(default=None, repr=False)
    overdrive_settings: Any = field(default=None, repr=False)
    runtime_logger: Any = field(default=None, repr=False)

    search_calls: int = 0
    read_calls: int = 0
    python_calls: int = 0
    site_map_calls: int = 0
    import_file_calls: int = 0
    reflect_streak: int = 0

    # Extra quota granted once when the model explicitly requests it.
    extra_quota_used: bool = False
    extra_search_quota: int = 0
    extra_read_quota: int = 0

    _url_to_source_id: dict[str, str] = field(default_factory=dict, repr=False)

    @property
    def elapsed(self) -> float:
        return time.time() - self.started_at

    def add_sources(self, sources: list[SourceCard]) -> list[SourceCard]:
        """Add unique source cards and return newly inserted cards."""

        inserted: list[SourceCard] = []
        for source in sources:
            url_key = source.url.strip().lower()
            if not url_key or url_key in self._url_to_source_id:
                continue
            if len(self.source_pool) >= int(self.config.max_sources):
                break
            source.id = f"S{len(self.source_pool) + 1:03d}"
            self._url_to_source_id[url_key] = source.id
            self.source_pool.append(source)
            inserted.append(source)
        return inserted

    def source_by_id_or_url(self, value: str) -> SourceCard | None:
        needle = (value or "").strip()
        if not needle:
            return None
        for source in self.source_pool:
            if source.id == needle or source.url == needle:
                return source
        source_id = self._url_to_source_id.get(needle.lower())
        if source_id:
            return self.source_by_id_or_url(source_id)
        return None

    def add_read_artifact(
        self,
        source: SourceCard,
        *,
        mode: str,
        content: str,
        chunks: list[str],
        query: str = "",
        truncated: bool = False,
    ) -> ReadArtifact:
        artifact = ReadArtifact(
            id=f"R{len(self.read_artifacts) + 1:03d}",
            source_id=source.id,
            url=source.url,
            mode=mode,
            content=content,
            chunks=chunks,
            query=query,
            char_count=len(content),
            truncated=truncated,
        )
        self.read_artifacts.append(artifact)
        source.read_artifact_ids.append(artifact.id)
        return artifact

    def add_trace(self, trace: ToolTrace) -> None:
        self.tool_trace.append(trace)

    def compact_sources(self, max_chars: int = 16_000) -> str:
        lines: list[str] = []
        used = 0
        for source in self.source_pool:
            block = (
                f"{source.id}. {source.title}\n"
                f"URL: {source.url}\n"
                f"Trust: {source.trust_tier} Score: {source.score:.2f} Engine: {source.engine}\n"
                f"Snippet: {source.snippet[:700]}\n"
            )
            if used + len(block) > max_chars:
                break
            lines.append(block)
            used += len(block)
        return "\n".join(lines) or "(no sources yet)"

    def compact_reads(self, max_chars: int = 24_000) -> str:
        lines: list[str] = []
        used = 0
        for artifact in self.read_artifacts:
            body = artifact.content[: max(500, min(5_000, max_chars - used))]
            block = (
                f"{artifact.id} from {artifact.source_id} mode={artifact.mode} url={artifact.url}\n"
                f"{body}\n"
            )
            if used + len(block) > max_chars:
                break
            lines.append(block)
            used += len(block)
        return "\n".join(lines) or "(no pages read yet)"

    def compact_reads_index(self, preview_chars: int = 180) -> str:
        """Locator-only view: id, source, mode, size, short preview.

        Used in the controller prompt so artifact content never bleeds into
        the search-phase context window. Full content is reserved for synthesis.
        """
        if not self.read_artifacts:
            return "(no pages read yet)"
        lines: list[str] = []
        for artifact in self.read_artifacts:
            preview = artifact.content[:preview_chars].replace("\n", " ").strip()
            if len(artifact.content) > preview_chars:
                preview += "…"
            lines.append(
                f"{artifact.id} [{artifact.source_id}, {artifact.mode}, {artifact.char_count:,} chars] "
                f"{artifact.url}\n  {preview}"
            )
        return "\n".join(lines)

    def synthesis_context_estimate(self) -> int:
        """Estimate chars in the synthesis prompt (full artifact content included)."""
        return (
            len(self.compact_sources(max_chars=200_000))
            + len(self.compact_reads(max_chars=200_000))
            + sum(len(item) for item in self.console_outputs[-8:])
            + sum(len(item) for item in self.reflection_log)
        )

    def compact_tool_trace(self, max_chars: int = 12_000) -> str:
        lines: list[str] = []
        used = 0
        for trace in self.tool_trace[-20:]:
            block = (
                f"Step {trace.step}: {trace.action} status={trace.status} "
                f"input={trace.input} output={trace.output_summary}\n"
            )
            if used + len(block) > max_chars:
                break
            lines.append(block)
            used += len(block)
        return "".join(lines) or "(no tool calls yet)"

    def context_size_estimate(self) -> int:
        # Uses the locator index (not full content) to match what the controller
        # actually sees in its prompt — prevents premature budget exhaustion.
        return (
            len(self.compact_sources(max_chars=200_000))
            + len(self.compact_reads_index())
            + len(self.compact_tool_trace(max_chars=100_000))
            + sum(len(item) for item in self.console_outputs)
            + sum(len(item) for item in self.reflection_log)
        )
