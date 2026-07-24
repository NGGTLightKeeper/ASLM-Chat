"""Deterministic Deep Research v2 orchestration.

The model never sees the large web-search tool schema.  Code owns the state
machine and gives the model a series of small jobs: draft a plan, reflect on the
evidence, propose candidates, select at most two queries, and write the report.
Malformed model output is local to one phase and always has a deterministic
fallback.
"""

from __future__ import annotations

import json
import re
import threading
import time
from collections.abc import Iterable, Iterator, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit

from API import llm_api, mcp as tool_registry
from Tools import deep_research_control as control


ALLOWED_SEARCH_ALIASES = (
    "web_search__web_search",
    "web_search__read_page",
)
MAX_QUERIES_PER_ITERATION = 2
MAX_PLAN_ITEMS = 7
MAX_QUERY_CANDIDATES = 6
MAX_PUBLIC_EVENTS = 160
MODEL_EVIDENCE_CHARS = 48_000
MODEL_ENTRY_CHARS = 9_000

PLAN_PROMPT = """You plan a web research task. Do not answer it and do not search.
Think carefully about the deliverable and evidence needed. Return one small JSON object:
{"summary":"short approach","steps":[{"id":"s1","title":"verifiable evidence goal"}],"candidates":[{"text":"plain search terms","vertical":"web|academic|shopping","purpose":"gap unlocked"}]}
Use 3-6 steps and 3-6 distinct candidate queries. Keep query text under 140 characters.
The plan will be shown to the user for approval. Return JSON only."""

REFLECTION_PROMPT = """You are the deliberate reflection stage of a research system.
No tools are available and no search happens in this turn. Spend real effort auditing the
evidence against every checklist item. Find contradictions, missing source classes, and the
highest-value unresolved gap. Then design several genuinely different candidate searches.
Return one small JSON object only:
{"assessment":"public concise evidence audit","gaps":["..."],"updates":[{"id":"s1","status":"pending|active|done|blocked","note":"public reason"}],"complete":false,"candidates":[{"text":"plain search terms","vertical":"web|academic|shopping","purpose":"why this query has high marginal value"}]}
Create 4-6 candidates when research is incomplete. Do not repeat a query from history. Query
text must be plain search terms, not a question or explanation, and stay under 140 characters."""

QUERY_SELECTION_PROMPT = """You are the query-budget gate. Search slots are scarce.
Compare the proposed candidates against the evidence gap and query history. Select only the
one or two queries with the highest expected information gain, source quality, and novelty.
Prefer different source classes when two are selected. Return JSON only:
{"queries":[{"text":"plain search terms","vertical":"web|academic|shopping","purpose":"short selection rationale"}]}
Never select more than two and never repeat an earlier query."""

REPORT_PROMPT = """Write the final self-contained research report in the user's language.
Use only the supplied evidence. Put the exact opaque citation handle (for example [c0001-2])
immediately after each supported claim; never invent or alter handles. Address every requested
deliverable, distinguish evidence from inference, and state unresolved gaps or disagreements.
Return the report itself, not JSON and not a diary of the research process."""


class ResearchCancelled(Exception):
    """Cooperative cancellation requested by the user."""


class ResearchModelUnavailable(RuntimeError):
    """The selected model failed before completing a required model stage."""


class SemanticEventStream:
    """Persist and publish compact, ordered, public research events."""

    schema_version = 2

    def __init__(
        self,
        session_id: str,
        *,
        callback: Callable[[dict[str, Any]], None] | None,
        logs_dir: Path,
    ) -> None:
        self.session_id = session_id
        self.callback = callback if callable(callback) else None
        existing_state = control.read_state(session_id)
        self.sequence = max(0, int(existing_state.get("last_sequence") or 0))
        self.events: list[dict[str, Any]] = []
        self._lock = threading.RLock()
        logs_dir.mkdir(parents=True, exist_ok=True)
        key = control.session_key(session_id)
        self.path = (logs_dir / f"deep-research-{key}.jsonl").resolve()
        self._handle = self.path.open("a", encoding="utf-8", buffering=1)

    def emit(
        self,
        event_type: str,
        *,
        phase: str,
        data: Mapping[str, Any] | None = None,
        iteration: int = 0,
        plan_version: int = 0,
    ) -> dict[str, Any]:
        with self._lock:
            self.sequence += 1
            record = {
                "schema_version": self.schema_version,
                "session_id": self.session_id,
                "sequence": self.sequence,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "phase": str(phase),
                "iteration": max(0, int(iteration or 0)),
                "plan_version": max(0, int(plan_version or 0)),
                "type": str(event_type),
                "data": dict(data or {}),
            }
            self._handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
            self._handle.flush()
            self.events.append(record)
            if len(self.events) > MAX_PUBLIC_EVENTS:
                del self.events[: len(self.events) - MAX_PUBLIC_EVENTS]
        if self.callback is not None:
            try:
                self.callback(record)
            except Exception:
                pass
        return record

    def close(self) -> None:
        with self._lock:
            if not self._handle.closed:
                self._handle.close()


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
    return _as_dict(_as_dict(chunk).get(key))


def _normalize_query_text(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "").replace("\r", " ").replace("\n", " ")).strip()
    return text[:160].strip(" ,;|")


def _query_signature(value: Any) -> str:
    return re.sub(r"[^a-z0-9а-яё]+", " ", str(value or "").casefold(), flags=re.I).strip()


def _safe_vertical(value: Any) -> str:
    vertical = str(value or "web").strip().lower()
    return vertical if vertical in {"web", "academic", "shopping"} else "web"


def _strict_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value == 1
    return str(value or "").strip().casefold() in {"true", "yes", "1"}


def _extract_json_object(text: Any) -> dict[str, Any]:
    source = str(text or "").strip()
    if not source:
        return {}
    candidates = [source]
    candidates.extend(
        match.group(1).strip()
        for match in re.finditer(r"```(?:json)?\s*(.*?)```", source, flags=re.I | re.S)
    )
    decoder = json.JSONDecoder()
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            parsed = None
        if isinstance(parsed, dict):
            return parsed
        for index, char in enumerate(candidate):
            if char != "{":
                continue
            try:
                parsed, _end = decoder.raw_decode(candidate[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
    return {}


def _plain_plan_lines(text: Any) -> list[str]:
    raw_lines = [line for line in str(text or "").splitlines() if line.strip()]
    marker = r"^\s*(?:(?:[-*+]|\d+[.)])\s+(?:\[[ xX]\]\s*)?|\[[ xX]\]\s*)"
    marked_lines = [
        line
        for line in raw_lines
        if re.match(marker, line)
    ]
    output: list[str] = []
    for line in marked_lines or raw_lines:
        clean = re.sub(marker, "", line).strip()
        if len(clean) >= 4 and not clean.startswith(("{", "}")):
            output.append(clean[:220])
        if len(output) >= MAX_PLAN_ITEMS:
            break
    return output


def _normalize_checklist(raw_steps: Any, fallback_text: str = "") -> list[dict[str, Any]]:
    steps = raw_steps if isinstance(raw_steps, list) else []
    normalized: list[dict[str, Any]] = []
    for index, raw_step in enumerate(steps[:MAX_PLAN_ITEMS], start=1):
        if isinstance(raw_step, dict):
            title = str(raw_step.get("title") or raw_step.get("step") or raw_step.get("goal") or "").strip()
            raw_id = str(raw_step.get("id") or f"s{index}").strip()
            status = str(raw_step.get("status") or "pending").strip().lower()
            note = str(raw_step.get("note") or "").strip()
        else:
            title = str(raw_step or "").strip()
            raw_id = f"s{index}"
            status = "pending"
            note = ""
        if not title:
            continue
        item = {
            "id": re.sub(r"[^a-zA-Z0-9_-]+", "-", raw_id).strip("-")[:40] or f"s{index}",
            "title": title[:220],
            "status": status if status in {"pending", "active", "done", "blocked", "skipped"} else "pending",
        }
        if note:
            item["note"] = note[:300]
        normalized.append(item)
    if normalized:
        return normalized
    return [
        {"id": f"s{index}", "title": title, "status": "pending"}
        for index, title in enumerate(_plain_plan_lines(fallback_text), start=1)
    ]


def _fallback_checklist(topic: str) -> list[dict[str, Any]]:
    return [
        {"id": "s1", "title": "Define the answer-critical claims and evidence classes", "status": "pending"},
        {"id": "s2", "title": f"Find authoritative sources for {topic[:120]}", "status": "pending"},
        {"id": "s3", "title": "Check important claims against independent evidence", "status": "pending"},
        {"id": "s4", "title": "Resolve contradictions and document remaining gaps", "status": "pending"},
        {"id": "s5", "title": "Synthesize a cited answer", "status": "pending"},
    ]


def _normalize_candidates(raw: Any, *, limit: int = MAX_QUERY_CANDIDATES) -> list[dict[str, str]]:
    items = raw if isinstance(raw, list) else []
    output: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in items:
        if isinstance(item, dict):
            text = _normalize_query_text(item.get("text") or item.get("query") or item.get("q"))
            vertical = _safe_vertical(item.get("vertical"))
            purpose = str(item.get("purpose") or item.get("rationale") or item.get("why") or "").strip()
        else:
            text = _normalize_query_text(item)
            vertical = "web"
            purpose = ""
        signature = _query_signature(text)
        if not signature or signature in seen:
            continue
        seen.add(signature)
        output.append({"text": text, "vertical": vertical, "purpose": purpose[:240]})
        if len(output) >= max(1, int(limit or 1)):
            break
    return output


def _fallback_candidates(topic: str, checklist: list[dict[str, Any]], iteration: int) -> list[dict[str, str]]:
    pending = next(
        (item for item in checklist if item.get("status") not in {"done", "skipped"}),
        checklist[-1] if checklist else {"title": topic},
    )
    goal = str(pending.get("title") or topic).strip()
    base = _normalize_query_text(topic)
    return [
        {
            "text": _normalize_query_text(f"{base} {goal}"),
            "vertical": "web",
            "purpose": f"Fallback query for unresolved plan item in iteration {iteration}",
        },
        {
            "text": _normalize_query_text(f"{base} official documentation evidence"),
            "vertical": "web",
            "purpose": "Find an authoritative source class",
        },
    ]


def _plan_text(summary: str, checklist: list[dict[str, Any]]) -> str:
    header = str(summary or "Research the request through verifiable evidence.").strip()
    lines = [header, "", *[f"- [ ] {item['title']}" for item in checklist]]
    return "\n".join(lines).strip()


class CommandInbox:
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.processed: set[str] = set()

    def poll(self) -> list[dict[str, Any]]:
        commands: list[dict[str, Any]] = []
        for filename, command in control.read_commands(self.session_id, processed=self.processed):
            self.processed.add(filename)
            commands.append(command)
        return commands


def _cancel_requested(session_id: str) -> bool:
    return control.latest_cancel_requested(session_id)


def _collect_model_text(result: Any, *, engine: str, session_id: str) -> str:
    visible: list[str] = []
    final_transcript = ""
    last_cancel_check = 0.0
    for raw_chunk in _iter_generation(result):
        now = time.monotonic()
        if now - last_cancel_check >= 0.2:
            last_cancel_check = now
            if _cancel_requested(session_id):
                try:
                    llm_api.abort_generation(engine)
                finally:
                    raise ResearchCancelled()
        message = _message_from_chunk(raw_chunk, "message")
        content = message.get("content")
        if isinstance(content, str) and content:
            visible.append(content)
        transcript = _message_from_chunk(raw_chunk, "transcript_message")
        transcript_content = transcript.get("content")
        if isinstance(transcript_content, str) and transcript_content.strip() and not transcript.get("tool_calls"):
            final_transcript = transcript_content.strip()
    return final_transcript or "".join(visible).strip()


def _run_model_stage(
    *,
    engine: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    generation_options: Mapping[str, Any],
    session_id: str,
    events: SemanticEventStream,
    phase: str,
    iteration: int,
    plan_version: int,
) -> str:
    events.emit(
        "model_stage_started",
        phase=phase,
        iteration=iteration,
        plan_version=plan_version,
        data={"stage": phase},
    )
    try:
        result = llm_api.generate(
            engine,
            model,
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            **dict(generation_options),
        )
        text = _collect_model_text(result, engine=engine, session_id=session_id)
    except ResearchCancelled:
        raise
    except Exception as exc:
        events.emit(
            "model_stage_failed",
            phase=phase,
            iteration=iteration,
            plan_version=plan_version,
            data={"stage": phase, "error_type": type(exc).__name__, "message": str(exc)[:400]},
        )
        # Provider adapters use different exception classes for connection,
        # timeout, authentication, missing-model and lazy stream failures. Any
        # exception here means the selected model did not return a response;
        # never manufacture a plan or query and continue into web search.
        raise ResearchModelUnavailable(
            f"The selected model '{model}' failed during {phase}: "
            f"{type(exc).__name__}: {str(exc)[:300]}"
        ) from exc
    events.emit(
        "model_stage_completed",
        phase=phase,
        iteration=iteration,
        plan_version=plan_version,
        data={"stage": phase, "output_chars": len(text)},
    )
    return text


def _apply_updates(checklist: list[dict[str, Any]], raw_updates: Any) -> list[dict[str, Any]]:
    updates = raw_updates if isinstance(raw_updates, list) else []
    by_id = {str(item.get("id")): dict(item) for item in checklist}
    for update in updates:
        if not isinstance(update, dict):
            continue
        item_id = str(update.get("id") or "").strip()
        if item_id not in by_id:
            continue
        status = str(update.get("status") or "").strip().lower()
        if status in {"pending", "active", "done", "blocked", "skipped"}:
            by_id[item_id]["status"] = status
        note = str(update.get("note") or "").strip()
        if note:
            by_id[item_id]["note"] = note[:300]
    return [by_id[str(item.get("id"))] for item in checklist]


def _normalize_user_plan(plan: Any, topic: str) -> tuple[str, list[dict[str, Any]]]:
    plan_text = str(plan or "").strip()
    checklist = _normalize_checklist([], plan_text)
    if not checklist:
        checklist = _fallback_checklist(topic)
        plan_text = _plan_text("User-adjusted research plan", checklist)
    return plan_text, checklist


def _handle_commands(
    inbox: CommandInbox,
    *,
    topic: str,
    plan: str,
    checklist: list[dict[str, Any]],
    plan_version: int,
    events: SemanticEventStream,
    iteration: int,
) -> tuple[str, list[dict[str, Any]], int, bool]:
    approved = False
    for command in inbox.poll():
        action = str(command.get("action") or "").strip().lower()
        payload = command.get("payload") if isinstance(command.get("payload"), dict) else {}
        if action == "cancel":
            raise ResearchCancelled()
        if action in {"revise", "approve"}:
            try:
                command_version = int(command.get("expected_plan_version"))
            except (TypeError, ValueError):
                command_version = -1
            if command_version != plan_version:
                events.emit(
                    "command_rejected",
                    phase="approval" if iteration == 0 else "research",
                    iteration=iteration,
                    plan_version=plan_version,
                    data={
                        "action": action,
                        "reason": "stale_plan_version",
                        "expected_plan_version": command_version,
                    },
                )
                continue
        if action in {"revise", "approve"} and str(payload.get("plan") or "").strip():
            plan, checklist = _normalize_user_plan(payload.get("plan"), topic)
            plan_version += 1
            events.emit(
                "plan_updated",
                phase="approval" if iteration == 0 else "research",
                iteration=iteration,
                plan_version=plan_version,
                data={"plan": plan, "checklist": checklist},
            )
            control.update_state(
                events.session_id,
                plan=plan,
                checklist=checklist,
                plan_version=plan_version,
                latest_action="Research plan updated",
                last_sequence=events.sequence,
                event_tail=list(events.events[-80:]),
            )
        if action == "approve":
            approved = True
    return plan, checklist, plan_version, approved


def _wait_for_approval(
    *,
    session_id: str,
    topic: str,
    plan: str,
    checklist: list[dict[str, Any]],
    plan_version: int,
    inbox: CommandInbox,
    events: SemanticEventStream,
    timeout_s: float,
    auto_approve: bool,
) -> tuple[str, list[dict[str, Any]], int]:
    events.emit(
        "approval_required",
        phase="approval",
        plan_version=plan_version,
        data={"plan": plan, "checklist": checklist},
    )
    control.update_state(
        session_id,
        status="awaiting_approval",
        phase="approval",
        plan=plan,
        checklist=checklist,
        plan_version=plan_version,
        latest_action="Waiting for plan approval",
        can_approve=True,
        can_edit=True,
        can_stop=True,
        last_sequence=events.sequence,
        event_tail=list(events.events[-80:]),
    )
    if auto_approve:
        events.emit(
            "approval_granted",
            phase="approval",
            plan_version=plan_version,
            data={"automatic": True},
        )
        return plan, checklist, plan_version

    deadline = time.monotonic() + max(1.0, float(timeout_s or 900.0))
    while time.monotonic() < deadline:
        plan, checklist, plan_version, approved = _handle_commands(
            inbox,
            topic=topic,
            plan=plan,
            checklist=checklist,
            plan_version=plan_version,
            events=events,
            iteration=0,
        )
        if approved:
            events.emit(
                "approval_granted",
                phase="approval",
                plan_version=plan_version,
                data={"automatic": False},
            )
            return plan, checklist, plan_version
        time.sleep(0.15)
    raise TimeoutError("Deep research plan approval expired.")


def _structured_result(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        structured = result.get("_tool_result_structured")
        if isinstance(structured, dict):
            return structured
        if isinstance(result.get("model_context"), str):
            return result
    if isinstance(result, str) and result.lstrip().startswith("{"):
        try:
            decoded = json.loads(result)
        except json.JSONDecodeError:
            return {"model_context": result, "sources": []}
        return decoded if isinstance(decoded, dict) else {"model_context": result, "sources": []}
    return {"model_context": str(result or ""), "sources": []}


def _canonical_source_url(value: Any) -> str:
    raw = str(value or "").strip()
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.casefold().removeprefix("www."), path, parsed.query, "")
    )


def _source_key(source: Mapping[str, Any]) -> str:
    return _canonical_source_url(source.get("url")) or str(source.get("id") or "").strip()


def _merge_sources(target: dict[str, dict[str, Any]], raw_sources: Any) -> int:
    added = 0
    for raw_source in raw_sources if isinstance(raw_sources, list) else []:
        if not isinstance(raw_source, dict):
            continue
        source = dict(raw_source)
        key = _source_key(source)
        if not key:
            continue
        if key in target:
            existing = target[key]
            aliases = existing.get("citation_aliases")
            if not isinstance(aliases, list):
                aliases = []
            incoming_handles = [source.get("id"), *(source.get("citation_aliases") or [])]
            for raw_handle in incoming_handles:
                handle = str(raw_handle or "").strip()
                if handle and handle != str(existing.get("id") or "").strip() and handle not in aliases:
                    aliases.append(handle)
            if aliases:
                existing["citation_aliases"] = aliases
            for field, value in source.items():
                if value not in (None, "", [], {}) and existing.get(field) in (None, "", [], {}):
                    existing[field] = value
            continue
        if not str(source.get("id") or "").strip():
            source["id"] = f"cpage-{len(target) + 1}"
        target[key] = source
        added += 1
    return added


def _read_citation_map(
    urls: list[str],
    sources_by_key: Mapping[str, Mapping[str, Any]],
) -> str:
    lines: list[str] = []
    for url in urls:
        source = sources_by_key.get(_canonical_source_url(url)) or {}
        handle = str(source.get("id") or "").strip()
        if handle:
            lines.append(f"- [{handle}] {url}")
    if not lines:
        return ""
    return "Citation mapping for the full pages below:\n" + "\n".join(lines)


def _structured_search_text(value: Any) -> tuple[str, dict[str, Any]]:
    """Move common model-written operators out of advanced query text."""

    text = _normalize_query_text(value)
    operators: dict[str, Any] = {}
    list_fields = {
        "site": "site_include",
        "-site": "site_exclude",
        "filetype": "file_types",
        "intitle": "title_terms",
        "inurl": "url_terms",
    }
    operator_pattern = re.compile(
        r'(?<!\S)(-?site|filetype|intitle|inurl|after|before):(?:"([^"]+)"|(\S+))',
        flags=re.I,
    )

    def move_operator(match: re.Match[str]) -> str:
        prefix = match.group(1).casefold()
        raw_value = (match.group(2) or match.group(3) or "").strip(" \t\r\n,;()[]{}")
        if not raw_value:
            return " "
        if prefix in {"after", "before"}:
            operators[prefix] = raw_value[:10]
        else:
            field = list_fields[prefix]
            values = operators.setdefault(field, [])
            if raw_value not in values:
                limit = 253 if "site" in field else (12 if field == "file_types" else 80)
                values.append(raw_value[:limit])
        return " "

    text = operator_pattern.sub(move_operator, text)

    exact_phrases: list[str] = []

    def move_phrase(match: re.Match[str]) -> str:
        phrase = re.sub(r"\s+", " ", match.group(1)).strip()
        if phrase and phrase not in exact_phrases and len(exact_phrases) < 4:
            exact_phrases.append(phrase[:120])
        return " "

    text = re.sub(r'"([^"]+)"', move_phrase, text)
    if exact_phrases:
        operators["exact_phrases"] = exact_phrases

    excluded_terms: list[str] = []

    def move_exclusion(match: re.Match[str]) -> str:
        term = match.group(1).strip()
        if term and term not in excluded_terms and len(excluded_terms) < 6:
            excluded_terms.append(term[:80])
        return " "

    text = re.sub(r"(?<!\S)-([\w.-]+)", move_exclusion, text)
    if excluded_terms:
        operators["exclude_terms"] = excluded_terms

    text = re.sub(r"(?<!\S)OR(?!\S)", " ", text, flags=re.I)
    text = re.sub(r"[()\[\]{}]+", " ", text)
    text = _normalize_query_text(text)
    if not text:
        fallback_terms = [
            str(item)
            for key, raw in operators.items()
            for item in (raw if isinstance(raw, list) else [raw])
            if key not in {"site_include", "site_exclude", "file_types", "after", "before"}
        ]
        text = _normalize_query_text(" ".join(fallback_terms)) or "authoritative source"
    return text, operators


def _tool_query_arguments(queries: list[dict[str, str]], iteration: int) -> dict[str, Any]:
    description = next(
        (str(query.get("purpose") or "").strip() for query in queries if query.get("purpose")),
        f"Investigating evidence gap {iteration}",
    )
    description = re.sub(r"\s+", " ", description).strip()[:76] or "Investigating evidence gap"
    canonical_queries: list[dict[str, Any]] = []
    for query in queries[:MAX_QUERIES_PER_ITERATION]:
        text, operators = _structured_search_text(query.get("text"))
        item: dict[str, Any] = {
            "vertical": _safe_vertical(query.get("vertical")),
            "text": text,
        }
        if operators:
            item["operators"] = operators
        canonical_queries.append(item)
    return {
        "description": description,
        "queries": canonical_queries,
        "effort": "medium",
    }


def _safe_source_preview(source: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: source.get(key)
        for key in (
            "id",
            "citation_aliases",
            "title",
            "url",
            "domain",
            "display_domain",
            "rank",
        )
        if source.get(key) not in (None, "")
    }


def _select_read_urls(sources: list[dict[str, Any]], seen_urls: set[str], limit: int = 2) -> list[str]:
    output: list[str] = []
    seen_domains: set[str] = set()
    for source in sources:
        url = str(source.get("url") or "").strip()
        try:
            parsed = urlsplit(url)
        except ValueError:
            continue
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or url in seen_urls:
            continue
        domain = parsed.netloc.casefold().removeprefix("www.")
        if domain in seen_domains and len(output) + 1 < limit:
            continue
        seen_domains.add(domain)
        seen_urls.add(url)
        output.append(url)
        if len(output) >= limit:
            break
    return output


def _evidence_packet(entries: list[dict[str, Any]], max_chars: int = MODEL_EVIDENCE_CHARS) -> str:
    pieces: list[str] = []
    remaining = max(4_000, int(max_chars or MODEL_EVIDENCE_CHARS))
    for entry in reversed(entries):
        text = str(entry.get("model_context") or "").strip()
        if not text:
            continue
        header = f"\n## Iteration {entry.get('iteration', '?')} {entry.get('kind', 'evidence')}\n"
        allowance = min(MODEL_ENTRY_CHARS, max(0, remaining - len(header)))
        if allowance <= 0:
            break
        fragment = header + text[:allowance]
        pieces.append(fragment)
        remaining -= len(fragment)
        if remaining <= 0:
            break
    return "".join(reversed(pieces)).strip()


def _citation_links(text: str, sources: list[dict[str, Any]]) -> str:
    source_urls: dict[str, str] = {}
    for source in sources:
        source_id = str(source.get("id") or "").strip().lower()
        url = str(source.get("url") or "").strip()
        try:
            parsed = urlsplit(url)
        except ValueError:
            continue
        if source_id and parsed.scheme in {"http", "https"} and parsed.netloc:
            source_urls[source_id] = url
            for alias in source.get("citation_aliases") or []:
                normalized_alias = str(alias or "").strip().lower()
                if normalized_alias:
                    source_urls[normalized_alias] = url
    handle = r"c[a-z0-9]{3,}-\d+"
    pattern = re.compile(rf"\[\s*({handle}(?:\s*,\s*{handle})*)\s*\](?!\()", flags=re.I)

    def replace(match: re.Match[str]) -> str:
        return " ".join(
            f"[{item}]({source_urls[item.lower()]})" if item.lower() in source_urls else f"[{item}]"
            for item in (part.strip() for part in match.group(1).split(","))
        )

    return pattern.sub(replace, str(text or ""))


def _fallback_report(
    *,
    topic: str,
    assessment: str,
    gaps: list[str],
    sources: list[dict[str, Any]],
    cancelled: bool = False,
) -> str:
    title = "Research stopped by the user" if cancelled else "Partial research result"
    parts = [f"## {title}", "", f"Topic: {topic}"]
    if assessment:
        parts.extend(["", assessment])
    if gaps:
        parts.extend(["", "### Remaining evidence gaps", *[f"- {gap}" for gap in gaps[:8]]])
    if sources:
        parts.extend(["", "### Sources collected"])
        for source in sources[:24]:
            label = str(source.get("title") or source.get("display_domain") or source.get("url") or "Source")
            handle = str(source.get("id") or "").strip()
            parts.append(f"- {label} [{handle}]" if handle else f"- {label}")
    return "\n".join(parts).strip()


def _result_payload(
    *,
    session_id: str,
    status: str,
    topic: str,
    plan: str,
    plan_version: int,
    checklist: list[dict[str, Any]],
    report: str,
    sources: list[dict[str, Any]],
    engine: str,
    model: str,
    queries_used: int,
    query_budget: int,
    iteration: int,
    events: SemanticEventStream,
) -> dict[str, Any]:
    final_status = str(status or "partial")
    ui = {
        "kind": "deep_research",
        "status": final_status,
        "topic": topic,
        "session_id": session_id,
        "plan": plan,
        "plan_version": plan_version,
        "checklist": checklist,
        "result_count": len(sources),
        "source_count": len(sources),
        "sources": sources,
        "engine": engine,
        "model": model,
        "queries_used": queries_used,
        "query_budget": query_budget,
        "iteration": iteration,
        "can_approve": False,
        "can_edit": False,
        "can_stop": False,
        "events": list(events.events),
        "event_log": {
            "schema_version": events.schema_version,
            "path": str(events.path),
            "event_count": events.sequence,
        },
    }
    return {
        "model_context": _citation_links(report, sources),
        "report": report,
        "plan": plan,
        "checklist": checklist,
        "sources": sources,
        "event_log": ui["event_log"],
        "ui": ui,
    }


def run_deep_research_v2(
    arguments: Mapping[str, Any],
    context: Mapping[str, Any] | None,
    *,
    runtime: Mapping[str, Any],
    generation_options: Mapping[str, Any],
    logs_dir: Path,
) -> dict[str, Any]:
    topic = str(arguments.get("topic") or "").strip()
    if not topic:
        raise ValueError("Deep research requires a non-empty topic.")
    instructions = str(arguments.get("instructions") or "").strip()
    request_text = topic if not instructions else f"{topic}\n\nAdditional instructions:\n{instructions}"
    try:
        max_iterations = min(10, max(2, int(arguments.get("max_rounds") or 6)))
    except (TypeError, ValueError):
        max_iterations = 6
    query_budget = max_iterations * MAX_QUERIES_PER_ITERATION
    engine = str(runtime["engine"])
    model = str(runtime["model"])
    caller = context if isinstance(context, Mapping) else {}
    try:
        approval_timeout_s = float(
            arguments.get("approval_timeout_s") or caller.get("approval_timeout_s") or 900
        )
    except (TypeError, ValueError):
        approval_timeout_s = 900.0
    runtime_limits = runtime.get("limits") if isinstance(runtime.get("limits"), Mapping) else {}
    try:
        runtime_context_tokens = int(
            runtime_limits.get("context_window")
            or runtime_limits.get("model_context_limit")
            or 0
        )
    except (TypeError, ValueError):
        runtime_context_tokens = 0
    evidence_char_budget = min(
        MODEL_EVIDENCE_CHARS,
        max(12_000, int(runtime_context_tokens * 4 * 0.24))
        if runtime_context_tokens
        else MODEL_EVIDENCE_CHARS,
    )
    session_id = str(arguments.get("session_id") or "").strip() or control.new_session_id()
    control.session_key(session_id)
    control.create_session(
        session_id,
        topic=topic,
        extra={"query_budget": query_budget, "engine": engine, "model": model},
    )
    events = SemanticEventStream(
        session_id,
        callback=caller.get("event_callback"),
        logs_dir=logs_dir,
    )
    inbox = CommandInbox(session_id)
    plan = ""
    plan_version = 0
    checklist: list[dict[str, Any]] = []
    sources_by_key: dict[str, dict[str, Any]] = {}
    evidence_entries: list[dict[str, Any]] = []
    seen_queries: set[str] = set()
    seen_urls: set[str] = set()
    queries_used = 0
    iteration = 0
    latest_assessment = ""
    latest_gaps: list[str] = []
    status = "partial"
    report = ""
    no_new_evidence_rounds = 0
    late_revision_without_search = False
    tool_context = {
        "chat_id": session_id,
        "engine": engine,
        "model_name": model,
        "module_dir": str(Path(__file__).resolve().parents[2]),
        "project_dir": str(Path(__file__).resolve().parents[2]),
        "allowed_tool_aliases": list(ALLOWED_SEARCH_ALIASES),
        "deep_research": True,
    }
    registry_error = ""
    try:
        _tool_specs, tool_lookup = tool_registry.build_ollama_tools(
            ["web_search"],
            allowed_tool_aliases=list(ALLOWED_SEARCH_ALIASES),
        )
    except Exception as exc:
        # Planning and synthesis can still produce a useful partial result when
        # the search backend is temporarily unavailable.  Keep this failure local
        # instead of dropping the complete MCP call before the approval card opens.
        tool_lookup = {}
        registry_error = f"{type(exc).__name__}: {exc}"[:400]

    def checkpoint(**changes: Any) -> None:
        control.update_state(
            session_id,
            plan=plan,
            plan_version=plan_version,
            checklist=checklist,
            source_count=len(sources_by_key),
            queries_used=queries_used,
            query_budget=query_budget,
            iteration=iteration,
            last_sequence=events.sequence,
            event_tail=list(events.events[-80:]),
            **changes,
        )

    try:
        events.emit(
            "session_started",
            phase="session",
            data={
                "topic": topic,
                "engine": engine,
                "model": model,
                "max_iterations": max_iterations,
                "query_budget": query_budget,
                "queries_per_iteration": MAX_QUERIES_PER_ITERATION,
                "orchestrator": "deterministic-v2",
            },
        )
        if registry_error:
            events.emit(
                "search_backend_unavailable",
                phase="session",
                data={"message": registry_error},
            )
        checkpoint(status="planning", phase="planning", latest_action="Drafting the research plan")
        events.emit("planning_started", phase="planning")
        raw_plan = _run_model_stage(
            engine=engine,
            model=model,
            system_prompt=PLAN_PROMPT,
            user_prompt=request_text,
            generation_options=generation_options,
            session_id=session_id,
            events=events,
            phase="planning",
            iteration=0,
            plan_version=0,
        )
        parsed_plan = _extract_json_object(raw_plan)
        checklist = _normalize_checklist(parsed_plan.get("steps"), raw_plan)
        if not checklist:
            checklist = _fallback_checklist(topic)
        summary = str(parsed_plan.get("summary") or "").strip()
        plan = _plan_text(summary, checklist)
        initial_candidates = _normalize_candidates(
            parsed_plan.get("candidates") or parsed_plan.get("queries")
        )
        plan_version = 1
        events.emit(
            "plan_ready",
            phase="planning",
            plan_version=plan_version,
            data={
                "plan": plan,
                "checklist": checklist,
                "candidate_count": len(initial_candidates),
                "fallback_used": not bool(parsed_plan),
            },
        )
        checkpoint(
            status="awaiting_approval",
            phase="approval",
            latest_action="Waiting for plan approval",
        )
        plan, checklist, plan_version = _wait_for_approval(
            session_id=session_id,
            topic=topic,
            plan=plan,
            checklist=checklist,
            plan_version=plan_version,
            inbox=inbox,
            events=events,
            timeout_s=approval_timeout_s,
            auto_approve=bool(caller.get("auto_approve") or arguments.get("auto_approve")),
        )
        if plan_version != 1:
            initial_candidates = []
        checkpoint(
            status="running",
            phase="research",
            latest_action="Beginning approved research",
            can_approve=False,
            can_edit=True,
            can_stop=True,
        )
        events.emit(
            "research_started",
            phase="research",
            plan_version=plan_version,
            data={"plan": plan, "checklist": checklist},
        )

        for iteration in range(1, max_iterations + 1):
            previous_plan_version = plan_version
            plan, checklist, plan_version, _approved = _handle_commands(
                inbox,
                topic=topic,
                plan=plan,
                checklist=checklist,
                plan_version=plan_version,
                events=events,
                iteration=iteration,
            )
            if plan_version != previous_plan_version and not _approved:
                initial_candidates = []
                plan, checklist, plan_version = _wait_for_approval(
                    session_id=session_id,
                    topic=topic,
                    plan=plan,
                    checklist=checklist,
                    plan_version=plan_version,
                    inbox=inbox,
                    events=events,
                    timeout_s=approval_timeout_s,
                    auto_approve=False,
                )
                checkpoint(
                    status="running",
                    phase="research",
                    latest_action="Continuing with the approved revised plan",
                    can_approve=False,
                    can_edit=True,
                    can_stop=True,
                )
            if _cancel_requested(session_id):
                raise ResearchCancelled()

            checkpoint(
                status="running",
                phase="reflection",
                latest_action=f"Reflecting before search iteration {iteration}",
            )
            events.emit(
                "reflection_started",
                phase="reflection",
                iteration=iteration,
                plan_version=plan_version,
                data={"queries_remaining": query_budget - queries_used},
            )
            evidence_packet = _evidence_packet(evidence_entries, evidence_char_budget)
            reflection_input = (
                f"Original request:\n{request_text}\n\nApproved plan:\n{plan}\n\n"
                f"Checklist JSON:\n{json.dumps(checklist, ensure_ascii=False)}\n\n"
                f"Queries already used:\n{json.dumps(sorted(seen_queries), ensure_ascii=False)}\n\n"
                f"Evidence gathered so far:\n{evidence_packet or '(none yet)'}"
            )
            raw_reflection = _run_model_stage(
                engine=engine,
                model=model,
                system_prompt=REFLECTION_PROMPT,
                user_prompt=reflection_input,
                generation_options=generation_options,
                session_id=session_id,
                events=events,
                phase="reflection",
                iteration=iteration,
                plan_version=plan_version,
            )
            reflection = _extract_json_object(raw_reflection)
            latest_assessment = str(reflection.get("assessment") or "").strip()[:1600]
            latest_gaps = [
                str(gap).strip()[:300]
                for gap in reflection.get("gaps", []) if str(gap).strip()
            ][:8] if isinstance(reflection.get("gaps"), list) else []
            checklist = _apply_updates(checklist, reflection.get("updates"))
            candidates = _normalize_candidates(reflection.get("candidates"))
            if not candidates and iteration == 1:
                candidates = initial_candidates
            if not candidates:
                candidates = _fallback_candidates(topic, checklist, iteration)
            complete = _strict_bool(reflection.get("complete")) and bool(sources_by_key)
            events.emit(
                "reflection_completed",
                phase="reflection",
                iteration=iteration,
                plan_version=plan_version,
                data={
                    "summary": latest_assessment or "Evidence audit completed.",
                    "evidence_gaps": latest_gaps,
                    "checklist": checklist,
                    "complete": complete,
                    "candidate_count": len(candidates),
                },
            )
            checkpoint(
                status="running",
                phase="reflection",
                latest_action=latest_assessment or "Evidence audit completed",
            )
            if complete:
                break
            if queries_used >= query_budget:
                break

            selection_input = (
                f"Unresolved gaps:\n{json.dumps(latest_gaps, ensure_ascii=False)}\n\n"
                f"Assessment:\n{latest_assessment}\n\n"
                f"Candidate queries:\n{json.dumps(candidates, ensure_ascii=False)}\n\n"
                f"Query history:\n{json.dumps(sorted(seen_queries), ensure_ascii=False)}\n\n"
                f"Slots remaining this iteration: {min(MAX_QUERIES_PER_ITERATION, query_budget - queries_used)}"
            )
            raw_selection = _run_model_stage(
                engine=engine,
                model=model,
                system_prompt=QUERY_SELECTION_PROMPT,
                user_prompt=selection_input,
                generation_options=generation_options,
                session_id=session_id,
                events=events,
                phase="query_selection",
                iteration=iteration,
                plan_version=plan_version,
            )
            parsed_selection = _extract_json_object(raw_selection)
            selected = _normalize_candidates(
                parsed_selection.get("queries") or parsed_selection.get("selected"),
                limit=min(MAX_QUERIES_PER_ITERATION, query_budget - queries_used),
            )
            if not selected:
                selected = candidates[: min(MAX_QUERIES_PER_ITERATION, query_budget - queries_used)]
            unique_selected: list[dict[str, str]] = []
            for query in selected:
                signature = _query_signature(query.get("text"))
                if signature and signature not in seen_queries:
                    seen_queries.add(signature)
                    unique_selected.append(query)
            if not unique_selected:
                for fallback in _fallback_candidates(topic, checklist, iteration):
                    signature = _query_signature(fallback.get("text"))
                    if signature and signature not in seen_queries:
                        seen_queries.add(signature)
                        unique_selected.append(fallback)
                        break
            if not unique_selected:
                no_new_evidence_rounds += 1
                if no_new_evidence_rounds >= 2:
                    break
                continue

            events.emit(
                "queries_selected",
                phase="query_selection",
                iteration=iteration,
                plan_version=plan_version,
                data={"queries": unique_selected},
            )
            checkpoint(
                status="running",
                phase="search",
                latest_action=f"Searching: {unique_selected[0]['text']}",
            )
            events.emit(
                "search_started",
                phase="search",
                iteration=iteration,
                plan_version=plan_version,
                data={"queries": unique_selected},
            )
            queries_used += len(unique_selected)
            search_args = _tool_query_arguments(unique_selected, iteration)
            try:
                search_result = tool_registry.call_ollama_tool(
                    tool_lookup,
                    "web_search__web_search",
                    search_args,
                    context=tool_context,
                )
                search_structured = _structured_result(search_result)
            except Exception as exc:
                search_structured = {
                    "model_context": f"Search failed without ending the session: {type(exc).__name__}: {exc}",
                    "sources": [],
                }
            if _cancel_requested(session_id):
                raise ResearchCancelled()
            search_sources = [
                dict(source)
                for source in search_structured.get("sources", [])
                if isinstance(source, dict)
            ]
            added_sources = _merge_sources(sources_by_key, search_sources)
            search_context = str(search_structured.get("model_context") or "").strip()
            if search_context:
                evidence_entries.append(
                    {
                        "iteration": iteration,
                        "kind": "search",
                        "queries": unique_selected,
                        "model_context": search_context[:MODEL_ENTRY_CHARS],
                    }
                )
            events.emit(
                "search_completed",
                phase="search",
                iteration=iteration,
                plan_version=plan_version,
                data={
                    "new_source_count": added_sources,
                    "source_count": len(sources_by_key),
                    "sources": [_safe_source_preview(source) for source in search_sources[:6]],
                },
            )

            read_urls = _select_read_urls(search_sources, seen_urls, limit=2)
            if read_urls:
                checkpoint(
                    status="running",
                    phase="reading",
                    latest_action=f"Reading {len(read_urls)} promising source pages",
                )
                events.emit(
                    "reading_started",
                    phase="reading",
                    iteration=iteration,
                    plan_version=plan_version,
                    data={"urls": read_urls},
                )
                try:
                    read_result = tool_registry.call_ollama_tool(
                        tool_lookup,
                        "web_search__read_page",
                        {"url": read_urls},
                        context=tool_context,
                    )
                    read_structured = _structured_result(read_result)
                except Exception as exc:
                    read_structured = {
                        "model_context": f"Page reading failed without ending the session: {type(exc).__name__}: {exc}",
                        "sources": [],
                    }
                if _cancel_requested(session_id):
                    raise ResearchCancelled()
                read_sources = [
                    dict(source)
                    for source in read_structured.get("sources", [])
                    if isinstance(source, dict)
                ]
                added_sources += _merge_sources(sources_by_key, read_sources)
                read_context = str(read_structured.get("model_context") or "").strip()
                if read_context:
                    citation_map = _read_citation_map(read_urls, sources_by_key)
                    if citation_map:
                        read_context = f"{citation_map}\n\n{read_context}"
                    evidence_entries.append(
                        {
                            "iteration": iteration,
                            "kind": "page reading",
                            "urls": read_urls,
                            "model_context": read_context[:MODEL_ENTRY_CHARS],
                        }
                    )
                events.emit(
                    "reading_completed",
                    phase="reading",
                    iteration=iteration,
                    plan_version=plan_version,
                    data={"url_count": len(read_urls), "new_source_count": len(read_sources)},
                )

            if added_sources <= 0:
                no_new_evidence_rounds += 1
            else:
                no_new_evidence_rounds = 0
            events.emit(
                "checkpoint_saved",
                phase="checkpoint",
                iteration=iteration,
                plan_version=plan_version,
                data={
                    "checklist": checklist,
                    "source_count": len(sources_by_key),
                    "queries_used": queries_used,
                    "query_budget": query_budget,
                    "no_new_evidence_rounds": no_new_evidence_rounds,
                },
            )
            checkpoint(
                status="running",
                phase="checkpoint",
                latest_action=f"Checkpoint {iteration} saved",
            )
            if no_new_evidence_rounds >= 2:
                break

        previous_plan_version = plan_version
        plan, checklist, plan_version, _approved = _handle_commands(
            inbox,
            topic=topic,
            plan=plan,
            checklist=checklist,
            plan_version=plan_version,
            events=events,
            iteration=iteration,
        )
        if plan_version != previous_plan_version and not _approved:
            initial_candidates = []
            plan, checklist, plan_version = _wait_for_approval(
                session_id=session_id,
                topic=topic,
                plan=plan,
                checklist=checklist,
                plan_version=plan_version,
                inbox=inbox,
                events=events,
                timeout_s=approval_timeout_s,
                auto_approve=False,
            )
            late_revision_without_search = True
        if _cancel_requested(session_id):
            raise ResearchCancelled()
        checkpoint(
            status="running",
            phase="final_reflection",
            latest_action="Performing the final evidence audit",
            can_approve=False,
            can_edit=False,
            can_stop=True,
        )
        events.emit(
            "final_reflection_started",
            phase="final_reflection",
            iteration=iteration,
            plan_version=plan_version,
            data={"source_count": len(sources_by_key), "queries_used": queries_used},
        )
        final_reflection_input = (
            "This is the mandatory final audit after the last search. Do not design or request "
            "another search. Re-evaluate every checklist item against all collected evidence and "
            "identify any remaining unsupported claim.\n\n"
            f"Original request:\n{request_text}\n\nApproved plan:\n{plan}\n\n"
            f"Checklist JSON:\n{json.dumps(checklist, ensure_ascii=False)}\n\n"
            f"Evidence gathered:\n{_evidence_packet(evidence_entries, evidence_char_budget) or '(none)'}"
        )
        raw_final_reflection = _run_model_stage(
            engine=engine,
            model=model,
            system_prompt=REFLECTION_PROMPT,
            user_prompt=final_reflection_input,
            generation_options=generation_options,
            session_id=session_id,
            events=events,
            phase="final_reflection",
            iteration=iteration,
            plan_version=plan_version,
        )
        final_reflection = _extract_json_object(raw_final_reflection)
        final_assessment = str(final_reflection.get("assessment") or "").strip()[:1600]
        if final_assessment:
            latest_assessment = final_assessment
        if isinstance(final_reflection.get("gaps"), list):
            latest_gaps = [
                str(gap).strip()[:300]
                for gap in final_reflection.get("gaps", [])
                if str(gap).strip()
            ][:8]
        checklist = _apply_updates(checklist, final_reflection.get("updates"))
        events.emit(
            "final_reflection_completed",
            phase="final_reflection",
            iteration=iteration,
            plan_version=plan_version,
            data={
                "summary": latest_assessment or "Final evidence audit completed.",
                "evidence_gaps": latest_gaps,
                "checklist": checklist,
            },
        )
        checkpoint(status="synthesizing", phase="synthesis", latest_action="Writing the cited report")
        events.emit(
            "synthesis_started",
            phase="synthesis",
            iteration=iteration,
            plan_version=plan_version,
            data={"source_count": len(sources_by_key)},
        )
        sources = list(sources_by_key.values())
        report_input = (
            f"Original request:\n{request_text}\n\nApproved plan:\n{plan}\n\n"
            f"Final checklist:\n{json.dumps(checklist, ensure_ascii=False)}\n\n"
            f"Latest evidence audit:\n{latest_assessment}\n\n"
            f"Remaining gaps:\n{json.dumps(latest_gaps, ensure_ascii=False)}\n\n"
            f"Evidence packet:\n{_evidence_packet(evidence_entries, evidence_char_budget)}"
        )
        report = _run_model_stage(
            engine=engine,
            model=model,
            system_prompt=REPORT_PROMPT,
            user_prompt=report_input,
            generation_options=generation_options,
            session_id=session_id,
            events=events,
            phase="synthesis",
            iteration=iteration,
            plan_version=plan_version,
        )
        synthesis_succeeded = bool(str(report or "").strip())
        if not synthesis_succeeded:
            report = _fallback_report(
                topic=topic,
                assessment=latest_assessment,
                gaps=latest_gaps,
                sources=sources,
            )
        unresolved_checklist = any(
            str(item.get("status") or "pending").strip().lower()
            not in {"done", "completed", "skipped"}
            for item in checklist
        )
        status = (
            "completed"
            if (
                sources
                and synthesis_succeeded
                and not late_revision_without_search
                and not latest_gaps
                and not unresolved_checklist
            )
            else "partial"
        )
        events.emit(
            "session_completed",
            phase="session",
            iteration=iteration,
            plan_version=plan_version,
            data={
                "status": status,
                "source_count": len(sources),
                "queries_used": queries_used,
                "query_budget": query_budget,
            },
        )
        checkpoint(
            status=status,
            phase="completed",
            latest_action="Research completed" if status == "completed" else "Partial report completed",
            can_approve=False,
            can_edit=False,
            can_stop=False,
            report=report,
            model_context=report,
            sources=[_safe_source_preview(source) for source in sources[:50]],
        )
        return _result_payload(
            session_id=session_id,
            status=status,
            topic=topic,
            plan=plan,
            plan_version=plan_version,
            checklist=checklist,
            report=report,
            sources=sources,
            engine=engine,
            model=model,
            queries_used=queries_used,
            query_budget=query_budget,
            iteration=iteration,
            events=events,
        )
    except ResearchCancelled:
        sources = list(sources_by_key.values())
        report = _fallback_report(
            topic=topic,
            assessment=latest_assessment,
            gaps=latest_gaps,
            sources=sources,
            cancelled=True,
        )
        events.emit(
            "session_cancelled",
            phase="session",
            iteration=iteration,
            plan_version=plan_version,
            data={"status": "cancelled", "source_count": len(sources), "queries_used": queries_used},
        )
        checkpoint(
            status="cancelled",
            phase="cancelled",
            latest_action="Research stopped by the user",
            can_approve=False,
            can_edit=False,
            can_stop=False,
            report=report,
            model_context=report,
            sources=[_safe_source_preview(source) for source in sources[:50]],
        )
        return _result_payload(
            session_id=session_id,
            status="cancelled",
            topic=topic,
            plan=plan,
            plan_version=plan_version,
            checklist=checklist,
            report=report,
            sources=sources,
            engine=engine,
            model=model,
            queries_used=queries_used,
            query_budget=query_budget,
            iteration=iteration,
            events=events,
        )
    except ResearchModelUnavailable as exc:
        sources = list(sources_by_key.values())
        report = f"Deep Research failed: {exc}"
        events.emit(
            "session_failed",
            phase="session",
            iteration=iteration,
            plan_version=plan_version,
            data={
                "status": "failed",
                "error_type": type(exc).__name__,
                "message": str(exc)[:400],
            },
        )
        checkpoint(
            status="failed",
            phase="failed",
            latest_action="The selected research model failed",
            can_approve=False,
            can_edit=False,
            can_stop=False,
            error=str(exc)[:400],
            report=report,
            model_context=report,
            sources=[_safe_source_preview(source) for source in sources[:50]],
        )
        return _result_payload(
            session_id=session_id,
            status="failed",
            topic=topic,
            plan=plan,
            plan_version=plan_version,
            checklist=checklist,
            report=report,
            sources=sources,
            engine=engine,
            model=model,
            queries_used=queries_used,
            query_budget=query_budget,
            iteration=iteration,
            events=events,
        )
    except TimeoutError as exc:
        sources = list(sources_by_key.values())
        timeout_status = "partial" if sources or queries_used else "expired"
        events.emit(
            "session_expired",
            phase="session",
            iteration=iteration,
            plan_version=plan_version,
            data={"status": timeout_status, "message": str(exc)},
        )
        report = (
            _fallback_report(
                topic=topic,
                assessment=(
                    latest_assessment
                    or "The revised-plan approval window expired; evidence collected before that point was preserved."
                ),
                gaps=latest_gaps,
                sources=sources,
            )
            if timeout_status == "partial"
            else "Deep research did not start because the initial plan approval window expired."
        )
        checkpoint(
            status=timeout_status,
            phase="expired",
            latest_action=report,
            can_approve=False,
            can_edit=False,
            can_stop=False,
            error=str(exc)[:400],
            report=report,
            model_context=report,
            sources=[
                _safe_source_preview(source)
                for source in sources[:50]
            ],
        )
        return _result_payload(
            session_id=session_id,
            status=timeout_status,
            topic=topic,
            plan=plan,
            plan_version=plan_version,
            checklist=checklist,
            report=report,
            sources=sources,
            engine=engine,
            model=model,
            queries_used=queries_used,
            query_budget=query_budget,
            iteration=iteration,
            events=events,
        )
    except Exception as exc:
        sources = list(sources_by_key.values())
        failure_status = "partial" if sources else "failed"
        failure_summary = (
            latest_assessment
            or f"The run stopped safely after an internal {type(exc).__name__}; collected evidence was preserved."
        )
        report = _fallback_report(
            topic=topic,
            assessment=failure_summary,
            gaps=latest_gaps,
            sources=sources,
        )
        try:
            events.emit(
                "session_failed",
                phase="session",
                iteration=iteration,
                plan_version=plan_version,
                data={
                    "status": failure_status,
                    "error_type": type(exc).__name__,
                    "message": str(exc)[:400],
                    "source_count": len(sources),
                },
            )
        except Exception:
            pass
        try:
            checkpoint(
                status=failure_status,
                phase="failed",
                latest_action=(
                    "Partial evidence preserved after an internal failure"
                    if sources
                    else "Research stopped after an internal failure"
                ),
                can_approve=False,
                can_edit=False,
                can_stop=False,
                error=f"{type(exc).__name__}: {str(exc)[:300]}",
                report=report,
                model_context=report,
                sources=[_safe_source_preview(source) for source in sources[:50]],
            )
        except Exception:
            pass
        return _result_payload(
            session_id=session_id,
            status=failure_status,
            topic=topic,
            plan=plan,
            plan_version=plan_version,
            checklist=checklist,
            report=report,
            sources=sources,
            engine=engine,
            model=model,
            queries_used=queries_used,
            query_budget=query_budget,
            iteration=iteration,
            events=events,
        )
    finally:
        try:
            tool_registry.clear_tool_runtime_scope(tool_context)
        except Exception:
            pass
        events.close()
