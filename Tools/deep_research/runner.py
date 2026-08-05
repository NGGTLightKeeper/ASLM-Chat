# Copyright NEXTGGTECH. Elastic License 2.0.

from __future__ import annotations

import json
import re
import sys
import threading
import uuid
from collections.abc import Iterable, Iterator, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from API import llm_api, mcp as tool_registry
from . import control as research_control


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SANDBOX_ROOT = PROJECT_ROOT / "Tools" / "mcp-sandbox"
for _sandbox_path in (SANDBOX_ROOT / "supervisor", SANDBOX_ROOT / "src"):
    if str(_sandbox_path) not in sys.path:
        sys.path.insert(0, str(_sandbox_path))

from sandbox.temporal import temporal_sandbox
from .orchestrator import run_deep_research_v2


RUNTIME_METADATA_FILE = PROJECT_ROOT / "Tools" / "model_runtime_metadata.json"
LOGS_DIR = research_control.CONTROL_ROOT / "logs"
ALLOWED_TOOL_ALIASES = (
    "web_search__web_search",
    "web_search__read_page",
    "sandbox__bash",
)

PLANNER_SYSTEM_PROMPT = """You are the planning stage of an isolated deep-research session.
Do not answer the user's question yet and do not claim that you searched. Produce a concrete
research plan and the first one or two search requests. Start from the final deliverables, split
them into evidence gaps, name the source class needed for each gap, note dependencies and a clear
success condition. Select web, shopping, academic, or onion search deliberately. Use query
operators only for a stated purpose. The first search requests must be focused and must unlock the
largest number of later verification steps. Keep the plan compact enough to execute."""

RESEARCH_SYSTEM_PROMPT = """You are an isolated deep-research agent. Execute the supplied plan,
inspect evidence, and deliver a self-contained report that answers the original request.

Available tools are exactly:
- web_search__web_search: discovery across web, shopping, academic, and onion verticals;
- web_search__read_page: inspect primary pages and promising results in depth;
- sandbox__bash: calculations, transformations, and temporary evidence analysis in a sandbox.

Research discipline:
- Work on the next unresolved evidence gap, normally with one focused medium-effort query.
- A search call may contain no more than two queries. Request no more than two web_search/read_page
  calls in one assistant turn. After search results, reason about what was established, what
  conflicts, which source classes are still missing, and the most informative next query.
- Bash does not consume the search-call budget. Consecutive bash calls are allowed when they are
  the efficient way to calculate, transform, or inspect sandbox data; no artificial reflection
  step is required between them.
- Measure coverage by answer-critical claims and source classes, not by link count. Prefer primary
  and authoritative evidence, verify important or disputed claims independently, and use read_page
  for details that snippets cannot establish.
- Do not repeat equivalent queries. Change anchors or source class when evidence is weak.
- Use the shopping vertical for prices, sellers, stock, and market candidates; academic for papers,
  authors, DOI records, and scholarly evidence. Web does not replace those verticals.
- Finish only when every answer-critical deliverable has adequate evidence or is explicitly marked
  unresolved. State material limitations and disagreements.

Citation discipline:
- Tool results provide opaque citation handles such as [c0000-1]. Copy those handles exactly next
  to the claims they support. Never invent, alter, or infer a handle.
- Cite only evidence actually returned during this isolated session.
- The final response must contain the researched answer, not a diary of tool calls or hidden chain
  of thought. Answer in the language of the original request. It may briefly summarize methodology
  or limitations when useful.

Report presentation:
- Write structured Markdown with clear sections and comparison tables when they improve scanning.
- Use valid LaTeX delimiters for equations, quantitative models, or scientific notation when useful.
- Use a valid fenced ```mermaid diagram for processes, architectures, timelines, or relationships
  that are materially clearer visually. Do not add decorative diagrams with no analytical value."""

RESEARCH_COMPRESSION_SYSTEM_PROMPT = """Compress completed deep-research history into durable
research memory. Return only these Markdown sections: Research Goal, Plan State, Verified Claims,
Contradictions, Open Evidence Gaps, Source Index, Sandbox Findings, Next Queries.

Preserve every opaque citation handle and its URL exactly. Never invent or renumber handles.
Keep claim-to-source relationships, source-class coverage, failed directions, unresolved
contradictions, and concrete next-query anchors. Summarize verbose snippets and terminal output,
but retain numerical results and assumptions needed to reproduce calculations. Do not answer the
original question and do not include hidden chain of thought."""


class ResearchEventLogger:
    """Persist and publish an ordered event stream for one research session."""

    schema_version = 1

    def __init__(
        self,
        session_id: str,
        *,
        callback=None,
        logs_dir: Path = LOGS_DIR,
    ) -> None:
        self.session_id = str(session_id)
        self.callback = callback if callable(callback) else None
        self.sequence = 0
        self.phase_iterations: dict[str, int] = {}
        self.advance_on_next_model_chunk: set[str] = set()
        self.lock = threading.RLock()
        logs_dir.mkdir(parents=True, exist_ok=True)
        safe_session_id = re.sub(r"[^a-zA-Z0-9_.-]+", "-", self.session_id).strip("-")
        self.path = (logs_dir / f"{safe_session_id}.jsonl").resolve()
        self.handle = self.path.open("a", encoding="utf-8", buffering=1)

    def current_iteration(self, phase: str) -> int:
        return self.phase_iterations.setdefault(str(phase), 1)

    def emit(
        self,
        event_type: str,
        *,
        phase: str,
        data: Any = None,
        iteration: int | None = None,
    ) -> dict[str, Any]:
        with self.lock:
            self.sequence += 1
            record = {
                "schema_version": self.schema_version,
                "session_id": self.session_id,
                "sequence": self.sequence,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "phase": str(phase),
                "iteration": iteration if iteration is not None else self.current_iteration(phase),
                "type": str(event_type),
                "data": data if data is not None else {},
            }
            self.handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
            self.handle.flush()
        if self.callback is not None:
            try:
                self.callback(record)
            except Exception:  # Observers must never interrupt research.
                pass
        return record

    def _advance_iteration_if_needed(self, phase: str) -> None:
        if phase not in self.advance_on_next_model_chunk:
            return
        self.phase_iterations[phase] = self.current_iteration(phase) + 1
        self.advance_on_next_model_chunk.discard(phase)
        self.emit("iteration_started", phase=phase)

    def observe_chunk(self, phase: str, raw_chunk: Any) -> None:
        chunk = _as_dict(raw_chunk)
        message = _as_dict(chunk.get("message"))
        transcript = _as_dict(chunk.get("transcript_message"))
        tool_events = chunk.get("tool_events")
        tool_event = chunk.get("tool_event")
        tool_result = _as_dict(chunk.get("tool_result"))
        tool_progress = _as_dict(chunk.get("tool_progress"))

        if message or transcript or tool_events or tool_event:
            self._advance_iteration_if_needed(phase)

        thinking = message.get("thinking")
        if isinstance(thinking, str) and thinking:
            self.emit(
                "model_output_delta",
                phase=phase,
                data={"channel": "reasoning", "content": thinking},
            )
        content = message.get("content")
        if isinstance(content, str) and content:
            self.emit(
                "model_output_delta",
                phase=phase,
                data={"channel": "content", "content": content},
            )
        if transcript:
            self.emit("model_turn_completed", phase=phase, data=transcript)

        normalized_tool_events = tool_events if isinstance(tool_events, list) else []
        if isinstance(tool_event, dict):
            normalized_tool_events = [*normalized_tool_events, tool_event]
        for event in normalized_tool_events:
            if isinstance(event, dict):
                self.emit("tool_call", phase=phase, data=event)

        if tool_progress:
            self.emit("tool_activity", phase=phase, data=tool_progress)
        if tool_result:
            self.emit("tool_result", phase=phase, data=tool_result)
            self.advance_on_next_model_chunk.add(phase)

        usage = chunk.get("usage")
        if not isinstance(usage, dict):
            usage = {
                key: chunk[key]
                for key in (
                    "prompt_eval_count",
                    "eval_count",
                    "prompt_tokens",
                    "completion_tokens",
                    "total_tokens",
                )
                if chunk.get(key) is not None
            }
        if usage:
            self.emit("usage", phase=phase, data=usage)

    def close(self) -> None:
        with self.lock:
            if not self.handle.closed:
                self.handle.close()


def _read_runtime_metadata(metadata_path: Path = RUNTIME_METADATA_FILE) -> dict[str, Any]:
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not read runtime model metadata: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Runtime model metadata must contain a JSON object.")
    return payload


def resolve_runtime_model(
    context: Mapping[str, Any] | None,
    *,
    metadata_path: Path = RUNTIME_METADATA_FILE,
) -> dict[str, Any]:
    """Resolve the caller's current model and enrich it from the shared runtime JSON."""

    metadata = _read_runtime_metadata(metadata_path)
    active = metadata.get("active") if isinstance(metadata.get("active"), dict) else {}
    caller = context if isinstance(context, Mapping) else {}
    engine = str(caller.get("engine") or active.get("engine") or "").strip()
    model = str(caller.get("model_name") or caller.get("model") or active.get("model") or "").strip()
    if not engine or not model:
        raise RuntimeError("No active engine/model is available for deep research.")

    models = metadata.get("models") if isinstance(metadata.get("models"), dict) else {}
    record = models.get(f"{engine}:{model}")
    if not isinstance(record, dict):
        record = next(
            (
                value
                for value in models.values()
                if isinstance(value, dict)
                and str(value.get("engine") or "").strip() == engine
                and str(value.get("model") or "").strip() == model
            ),
            {},
        )
    capabilities = record.get("capabilities") if isinstance(record.get("capabilities"), dict) else {}
    if capabilities.get("tools") is False:
        raise RuntimeError(f"The selected model '{model}' does not support tool calling.")

    return {
        "engine": engine,
        "model": model,
        "capabilities": dict(capabilities),
        "limits": dict(record.get("limits") or {}) if isinstance(record.get("limits"), dict) else {},
        "metadata_source": (
            "caller_context"
            if caller.get("engine") and (caller.get("model_name") or caller.get("model"))
            else "runtime_active"
        ),
    }


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, Mapping):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        return dumped if isinstance(dumped, dict) else {}
    return {}


def _iter_generation(result: Any) -> Iterator[Any]:
    if result is None:
        return
    if isinstance(result, (dict, Mapping)) or callable(getattr(result, "model_dump", None)):
        yield result
        return
    if isinstance(result, (str, bytes)):
        yield {"message": {"role": "assistant", "content": str(result)}}
        return
    if isinstance(result, Iterable):
        yield from result
        return
    yield result


def _message_from_chunk(chunk: Any, key: str) -> dict[str, Any]:
    chunk_payload = _as_dict(chunk)
    return _as_dict(chunk_payload.get(key))


def _structured_tool_result(chunk: Any) -> dict[str, Any]:
    tool_message = _message_from_chunk(chunk, "tool_result")
    structured = tool_message.get("structured_content") or tool_message.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    content = tool_message.get("content")
    if isinstance(content, dict):
        return content
    if isinstance(content, str):
        try:
            decoded = json.loads(content)
        except json.JSONDecodeError:
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return {}


def replace_citation_handles_with_markdown_links(
    text: str,
    sources: list[dict[str, Any]],
) -> str:
    """Resolve internal citation handles before the report reaches the parent model."""

    source_urls: dict[str, str] = {}
    for source in sources:
        if not isinstance(source, dict):
            continue
        source_id = str(source.get("id") or "").strip().lower()
        source_url = str(source.get("url") or "").strip()
        try:
            parsed_url = urlsplit(source_url)
        except ValueError:
            continue
        if source_id and parsed_url.scheme in {"http", "https"} and parsed_url.netloc:
            source_urls[source_id] = source_url

    handle = r"c[a-z0-9]{3,}-\d+"
    group_pattern = re.compile(
        rf"\[\s*({handle}(?:\s*,\s*{handle})*)\s*\](?!\()",
        flags=re.I,
    )

    def replace_group(match: re.Match[str]) -> str:
        links: list[str] = []
        for raw_id in match.group(1).split(","):
            citation_id = raw_id.strip()
            source_url = source_urls.get(citation_id.lower())
            links.append(
                f"[{citation_id}]({source_url})"
                if source_url
                else f"[{citation_id}]"
            )
        return " ".join(links)

    return group_pattern.sub(replace_group, str(text or ""))


def _collect_generation(
    result: Any,
    *,
    event_logger: ResearchEventLogger | None = None,
    phase: str = "generation",
) -> tuple[str, list[dict[str, Any]]]:
    visible_fragments: list[str] = []
    final_transcript = ""
    sources_by_key: dict[str, dict[str, Any]] = {}

    for raw_chunk in _iter_generation(result):
        if event_logger is not None:
            event_logger.observe_chunk(phase, raw_chunk)
        message = _message_from_chunk(raw_chunk, "message")
        content = message.get("content")
        if isinstance(content, str) and content:
            visible_fragments.append(content)

        transcript = _message_from_chunk(raw_chunk, "transcript_message")
        transcript_content = transcript.get("content")
        if (
            isinstance(transcript_content, str)
            and transcript_content.strip()
            and not transcript.get("tool_calls")
        ):
            final_transcript = transcript_content.strip()

        structured = _structured_tool_result(raw_chunk)
        raw_sources = structured.get("sources") if isinstance(structured, dict) else None
        if not isinstance(raw_sources, list):
            continue
        for raw_source in raw_sources:
            if not isinstance(raw_source, dict):
                continue
            source = dict(raw_source)
            source_id = str(source.get("id") or "").strip()
            source_url = str(source.get("url") or "").strip()
            key = source_id or source_url
            if key and key not in sources_by_key:
                sources_by_key[key] = source

    text = final_transcript or "".join(visible_fragments).strip()
    return text, list(sources_by_key.values())


def _generation_options(runtime: dict[str, Any]) -> dict[str, Any]:
    options: dict[str, Any] = {"stream": True}
    capabilities = runtime.get("capabilities") if isinstance(runtime.get("capabilities"), dict) else {}
    if capabilities.get("thinking") is True:
        options.update({"think": True, "think_level": "high"})
    return options


def _coerce_max_rounds(value: Any) -> int:
    try:
        return min(24, max(4, int(value or 12)))
    except (TypeError, ValueError):
        return 12


def _compression_trigger_chars(runtime: dict[str, Any]) -> int:
    limits = runtime.get("limits") if isinstance(runtime.get("limits"), dict) else {}
    raw_tokens = limits.get("context_window") or limits.get("model_context_limit") or 0
    try:
        context_tokens = max(0, int(raw_tokens))
    except (TypeError, ValueError):
        context_tokens = 0
    if not context_tokens:
        return 60_000
    return min(120_000, max(24_000, int(context_tokens * 4 * 0.45)))


def _fallback_research_memory(raw_history: str) -> str:
    handles = list(dict.fromkeys(re.findall(r"\bc[a-z0-9]{3,}-\d+\b", raw_history, flags=re.I)))
    urls = list(dict.fromkeys(re.findall(r"https?://[^\s\"'<>]+", raw_history)))
    tail = raw_history[-16_000:]
    return (
        "## Research Goal\nPreserved in the active request.\n\n"
        "## Plan State\nCompression fallback retained the newest research observations.\n\n"
        "## Verified Claims\nReview the preserved observations below.\n\n"
        "## Contradictions\nNot semantically classified by the fallback.\n\n"
        "## Open Evidence Gaps\nReassess against the active plan.\n\n"
        "## Source Index\n"
        + "\n".join([*(f"- [{handle}]" for handle in handles), *(f"- {url}" for url in urls)])
        + "\n\n## Sandbox Findings\nSee preserved observations.\n\n"
        "## Next Queries\nRe-evaluate the next unresolved evidence gap.\n\n"
        "## Preserved Observations\n"
        + tail
    )


def _research_compactor(
    runtime: dict[str, Any],
    event_logger: ResearchEventLogger | None = None,
):
    engine = str(runtime["engine"])
    model = str(runtime["model"])

    def compact(entries: list[dict[str, Any]], *, provider_format: str = "standard") -> str:
        if event_logger is not None:
            event_logger.emit(
                "compression_started",
                phase="compression",
                data={"provider_format": provider_format, "entry_count": len(entries)},
            )
        raw_history = json.dumps(entries, ensure_ascii=False, default=str)
        compression_result = llm_api.generate(
            engine,
            model,
            [
                {"role": "system", "content": RESEARCH_COMPRESSION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": "Compress these completed research turns:\n\n" + raw_history,
                },
            ],
            stream=True,
        )
        summary, _sources = _collect_generation(
            compression_result,
            event_logger=event_logger,
            phase="compression",
        )
        fallback_used = not bool(summary)
        compressed = summary or _fallback_research_memory(raw_history)
        if event_logger is not None:
            event_logger.emit(
                "compression_completed",
                phase="compression",
                data={
                    "fallback_used": fallback_used,
                    "input_chars": len(raw_history),
                    "output_chars": len(compressed),
                },
            )
            event_logger.phase_iterations["compression"] = (
                event_logger.current_iteration("compression") + 1
            )
        return compressed

    return compact


def run_deep_research(
    arguments: Mapping[str, Any],
    context: Mapping[str, Any] | None = None,
    *,
    metadata_path: Path = RUNTIME_METADATA_FILE,
    logs_dir: Path = LOGS_DIR,
) -> dict[str, Any]:
    """Run the deterministic v2 state machine with the caller's selected model."""

    try:
        runtime = resolve_runtime_model(context, metadata_path=metadata_path)
    except Exception as exc:
        session_id = str(arguments.get("session_id") or "").strip()
        if session_id:
            try:
                research_control.update_state(
                    session_id,
                    status="failed",
                    phase="failed",
                    latest_action="The selected research model could not be initialized",
                    error=f"{type(exc).__name__}: {str(exc)[:300]}",
                    can_approve=False,
                    can_edit=False,
                    can_stop=False,
                )
            except (OSError, ValueError):
                pass
        raise
    return run_deep_research_v2(
        arguments,
        context,
        runtime=runtime,
        generation_options=_generation_options(runtime),
        logs_dir=logs_dir,
    )
