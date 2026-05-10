# Copyright NGGT.LightKeeper. All Rights Reserved.

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

COMPRESSION_TARGET_MIN_CHARS = 60000
COMPRESSION_ENTRY_MAX_CHARS = 2400
ANALYTIC_ENTRY_MAX_CHARS = 360
MEMORY_ENTRY_MAX_CHARS = 1200
COMPRESSION_FIRST_CONTEXT_ENTRIES = 3
COMPRESSION_LAST_CONTEXT_ENTRIES = 5
TOOL_OBSERVATION_MAX_CHARS = 700

NOISY_URL_HOSTS = {
    "127.0.0.1",
    "localhost",
    "www.bing.com",
    "bing.com",
}

RAW_TOOL_NOISE_MARKERS = (
    "citation rules",
    "cite search evidence",
    "use the exact citation",
    "put the citation handle",
    "search results for:",
)
FACT_NOISE_PREFIXES = (
    "content:",
    "preview:",
    "title:",
    "description:",
    "snippet:",
)
AGGRESSIVE_MARKERS = (
    "нахуя",
    "блять",
    "ебал",
    "ебуч",
    "пошевели извилинами",
    "идиот",
    "fucking",
    "wtf",
)


@dataclass
class CompressionDecision:
    enabled: bool
    context_window_tokens: int
    history_budget_chars: int
    reason: str


def resolve_context_window_tokens(
    model_info_payload: dict[str, Any] | None,
    *,
    runtime_metadata_path: Path | None = None,
    active_engine: str = "",
    active_model: str = "",
) -> int:
    """Resolve context window from model payload first, then runtime metadata file."""

    def _positive_int(value: Any) -> int:
        if isinstance(value, bool) or value is None:
            return 0
        try:
            number = int(value)
        except (TypeError, ValueError):
            return 0
        return number if number > 0 else 0

    payload_model_limit = 0
    if isinstance(model_info_payload, dict):
        defaults = model_info_payload.get("defaults", {})
        if isinstance(defaults, dict):
            for key in ("num_ctx", "context_window", "contextWindow", "input_token_limit", "inputTokenLimit"):
                number = _positive_int(defaults.get(key))
                if number:
                    return number

        limits = model_info_payload.get("limits", {})
        if isinstance(limits, dict):
            for key in ("context_window", "contextWindow", "num_ctx"):
                number = _positive_int(limits.get(key))
                if number:
                    return number

        for key in ("context_window", "contextWindow", "num_ctx", "input_token_limit", "inputTokenLimit"):
            number = _positive_int(model_info_payload.get(key))
            if number:
                return number

        payload_model_limit = _positive_int(model_info_payload.get("context_length"))

    if runtime_metadata_path is None:
        return payload_model_limit

    try:
        payload = json.loads(runtime_metadata_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return payload_model_limit

    if not isinstance(payload, dict):
        return payload_model_limit

    models = payload.get("models", {})
    if not isinstance(models, dict):
        return payload_model_limit

    model_key = f"{active_engine}:{active_model}" if active_engine and active_model else ""
    targets: list[dict[str, Any]] = []
    if model_key and isinstance(models.get(model_key), dict):
        targets.append(models[model_key])
    active = payload.get("active", {})
    if isinstance(active, dict):
        active_key = f"{active.get('engine')}:{active.get('model')}"
        if isinstance(models.get(active_key), dict):
            targets.append(models[active_key])

    for item in models.values():
        if isinstance(item, dict):
            targets.append(item)

    for target in targets:
        limits = target.get("limits", {})
        if not isinstance(limits, dict):
            continue
        context_window = _positive_int(limits.get("context_window"))
        if context_window:
            return context_window

    for target in targets:
        limits = target.get("limits", {})
        if not isinstance(limits, dict):
            continue
        model_limit = _positive_int(limits.get("model_context_limit"))
        if model_limit:
            return model_limit

    return payload_model_limit


def decide_compression(
    *,
    used_history_chars: int,
    history_budget_chars: int,
    model_info_payload: dict[str, Any] | None,
    runtime_metadata_path: Path | None,
    active_engine: str,
    active_model: str,
    debug_force_4k: bool = False,
    trigger_ratio: float = 0.80,
) -> CompressionDecision:
    context_window_tokens = resolve_context_window_tokens(
        model_info_payload,
        runtime_metadata_path=runtime_metadata_path,
        active_engine=active_engine,
        active_model=active_model,
    )
    if debug_force_4k:
        context_window_tokens = 4096

    threshold = int(max(0, history_budget_chars) * max(0.0, min(1.0, trigger_ratio)))
    enabled = history_budget_chars > 0 and used_history_chars >= threshold
    reason = f"used={used_history_chars}, threshold={threshold}, budget={history_budget_chars}, ctx={context_window_tokens}"
    return CompressionDecision(
        enabled=enabled,
        context_window_tokens=context_window_tokens,
        history_budget_chars=history_budget_chars,
        reason=reason,
    )


def _strip_control_tokens(text: str) -> str:
    cleaned = str(text or "")
    cleaned = re.sub(r"<\|start\|>.*?<\|message\|>", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"<\|[^>]+\|>", "", cleaned)
    return cleaned.strip()


def _entry_text(entry: dict[str, Any], max_chars: int = COMPRESSION_ENTRY_MAX_CHARS) -> str:
    role = str(entry.get("role") or "unknown")
    content = _strip_control_tokens(str(entry.get("content") or ""))
    thinking = _strip_control_tokens(str(entry.get("thinking") or ""))
    parts = [part for part in (content, thinking) if part]
    raw = "\n".join(parts).strip()
    if len(raw) > max_chars:
        raw = raw[:max_chars].rstrip() + "..."
    return f"{role}: {raw}" if raw else f"{role}:"


def _is_noisy_url(url: str) -> bool:
    raw = str(url or "").strip().rstrip(".,;:")
    if not raw:
        return True
    match = re.match(r"^https?://([^/?#]+)", raw, flags=re.IGNORECASE)
    host = match.group(1).lower() if match else ""
    host = host.split(":", 1)[0]
    if host in NOISY_URL_HOSTS:
        return True
    if host.endswith(".bing.com"):
        return True
    return False


def _clean_memory_text(text: str) -> str:
    """Remove repeated tool boilerplate while preserving useful facts."""

    lines: list[str] = []
    skip_citation_block = False
    for raw_line in _strip_control_tokens(text).splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            skip_citation_block = False
            continue
        lowered = line.lower()
        if lowered.startswith(RAW_TOOL_NOISE_MARKERS):
            skip_citation_block = True
            continue
        if skip_citation_block and lowered.startswith(("-", "*")):
            continue
        skip_citation_block = False
        if lowered in {"---", "done", "running"}:
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _entry_memory_text(entry: dict[str, Any], max_chars: int = MEMORY_ENTRY_MAX_CHARS) -> str:
    role = str(entry.get("role") or "unknown").lower()
    content = _clean_memory_text(str(entry.get("content") or ""))
    thinking = "" if role == "assistant" else _clean_memory_text(str(entry.get("thinking") or ""))
    raw = "\n".join(part for part in (content, thinking) if part).strip()
    if not raw:
        return f"{role}:"

    if role == "tool":
        site_match = re.search(r"\*\*Site:\*\*\s*([^\n]+)", raw)
        url_match = re.search(r"\*\*URL:\*\*\s*([^\n]+)", raw)
        title_match = re.search(r"^\s*#\s+(.+)$", raw, flags=re.MULTILINE)
        query_match = re.search(r"Search results for:\s*([^\n]+)", raw, flags=re.IGNORECASE)
        parts: list[str] = []
        if query_match:
            parts.append(f"Search query: {query_match.group(1).strip()}")
        if title_match:
            parts.append(f"Source title: {title_match.group(1).strip()}")
        if site_match:
            parts.append(f"Site: {site_match.group(1).strip()}")
        if url_match and not _is_noisy_url(url_match.group(1).strip()):
            parts.append(f"URL: {url_match.group(1).strip()}")
        for line in _line_candidates(raw):
            lowered = line.lower()
            if lowered.startswith(RAW_TOOL_NOISE_MARKERS):
                continue
            if lowered.startswith(("site:**", "url:**", "**site", "**url")):
                continue
            if lowered.count("http://") + lowered.count("https://") > 1:
                continue
            if any(_is_noisy_url(url) for url in re.findall(r"https?://[^\s)>\]\"']+", line, flags=re.IGNORECASE)):
                continue
            if len(parts) >= 8:
                break
            parts.append(line[:260])
        raw = "\n".join(parts) if parts else raw

    if len(raw) > max_chars:
        raw = raw[:max_chars].rstrip() + "..."
    return f"{role}: {raw}" if raw else f"{role}:"


def _tool_observation_text(entry: dict[str, Any], max_chars: int = TOOL_OBSERVATION_MAX_CHARS) -> str:
    """Return a compact observation from a tool result without raw tool-call logs."""

    text = _clean_memory_text(str(entry.get("content") or ""))
    if not text:
        return ""

    tool_name = str(entry.get("tool_name") or entry.get("name") or entry.get("alias") or entry.get("tool_id") or "tool").strip()
    title_match = re.search(r"^\s*#\s+(.+)$", text, flags=re.MULTILINE)
    site_match = re.search(r"\*\*Site:\*\*\s*([^\n]+)", text)
    url_match = re.search(r"\*\*URL:\*\*\s*([^\n]+)", text)
    error_match = re.search(r"(Traceback[\s\S]{0,500}|[A-Za-z_]*Error:\s*[^\n]+|exit_code['\"]?\s*:\s*[1-9]\d*)", text)

    parts: list[str] = []
    if tool_name:
        parts.append(f"Tool outcome from {tool_name}.")
    if title_match:
        parts.append(f"Source/title: {title_match.group(1).strip()}.")
    if site_match:
        parts.append(f"Site: {site_match.group(1).strip()}.")
    if url_match and not _is_noisy_url(url_match.group(1).strip()):
        parts.append(f"URL: {url_match.group(1).strip()}.")
    if error_match:
        parts.append(f"Error signal: {error_match.group(1).strip()}.")

    for line in _line_candidates(text):
        lowered = line.lower()
        if lowered.startswith(RAW_TOOL_NOISE_MARKERS):
            continue
        if lowered.startswith(("site:**", "url:**", "**site", "**url")):
            continue
        if lowered.count("http://") + lowered.count("https://") > 1:
            continue
        if any(_is_noisy_url(url) for url in re.findall(r"https?://[^\s)>\]\"']+", line, flags=re.IGNORECASE)):
            continue
        if re.match(r"^\{.*\}$", line):
            continue
        parts.append(line[:260])
        if len(parts) >= 6:
            break

    observation = " ".join(part for part in parts if part).strip()
    if len(observation) > max_chars:
        observation = observation[:max_chars].rstrip() + "..."
    return observation


def _compression_prompt_entry_text(entry: dict[str, Any]) -> str:
    role = str(entry.get("role") or "").lower()
    if role == "tool":
        observation = _tool_observation_text(entry)
        return f"tool_observation: {observation}" if observation else ""
    return _entry_memory_text(entry, max_chars=1000)


def _scoped_context_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep a small stable raw-context window around the compressed span."""

    if len(entries) <= COMPRESSION_FIRST_CONTEXT_ENTRIES + COMPRESSION_LAST_CONTEXT_ENTRIES:
        return list(entries)
    first = entries[:COMPRESSION_FIRST_CONTEXT_ENTRIES]
    last = entries[-COMPRESSION_LAST_CONTEXT_ENTRIES:]
    return [*first, *last]


def _looks_like_raw_tool_dump(text: str) -> bool:
    lowered = str(text or "").lower()
    if any(marker in lowered for marker in RAW_TOOL_NOISE_MARKERS):
        return True
    if lowered.startswith(("**site:**", "**url:**", "site:**", "url:**")):
        return True
    if lowered.count("http://") + lowered.count("https://") >= 2:
        return True
    if any(_is_noisy_url(url) for url in re.findall(r"https?://[^\s)>\]\"']+", lowered, flags=re.IGNORECASE)):
        return True
    if len(lowered) > 600 and ("**site:**" in lowered or "**url:**" in lowered):
        return True
    return False


def _sanitize_semantic_items(
    values: list[Any],
    *,
    limit: int,
    max_chars: int,
    allow_tool_memory: bool = False,
) -> list[str]:
    cleaned: list[str] = []
    for value in values:
        text = _clean_memory_text(str(value or ""))
        if not text:
            continue
        if text.strip().lower() in {"assistant:", "assistant: []"}:
            continue
        if not allow_tool_memory and _looks_like_raw_tool_dump(text):
            continue
        if len(text) > max_chars:
            text = text[:max_chars].rstrip() + "..."
        cleaned.append(text)
    return _dedupe_strings(cleaned, limit=limit)


def _looks_like_reasoning_fragment(text: str) -> bool:
    lowered = re.sub(r"\s+", " ", str(text or "").strip().lower())
    if not lowered:
        return False
    reasoning_starts = (
        "we need",
        "now ",
        "wait ",
        "check ",
        "let's ",
        "i need",
        "need to ",
        "maybe ",
        "probably ",
    )
    return lowered.startswith(reasoning_starts) or lowered.endswith("...")


def _sanitize_open_tasks(values: list[Any], *, limit: int = 12) -> list[str]:
    tasks: list[str] = []
    for value in values:
        text = _clean_memory_text(str(value or ""))
        if not text:
            continue
        if _looks_like_reasoning_fragment(text):
            continue
        lowered = text.lower()
        if any(marker in lowered for marker in ("wait we", "now combine", "check balancing", "we need to")):
            continue
        if len(text) > ANALYTIC_ENTRY_MAX_CHARS:
            text = text[:ANALYTIC_ENTRY_MAX_CHARS].rstrip() + "..."
        tasks.append(text)
    return _dedupe_strings(tasks, limit=limit)


def _fallback_open_task_from_goal(goal: str) -> str:
    clean_goal = _clean_memory_text(str(goal or "")).strip()
    if not clean_goal:
        return ""
    if len(clean_goal) > 180:
        clean_goal = clean_goal[:180].rstrip() + "..."
    return f"Check the current result and complete the remaining user goal requirements: {clean_goal}"


def _dedupe_strings(values: list[str], *, limit: int = 64) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
        if len(result) >= limit:
            break
    return result


def _line_candidates(text: str) -> list[str]:
    raw = _strip_control_tokens(text)
    candidates: list[str] = []
    for line in raw.splitlines():
        cleaned = re.sub(r"^[\s>*#\-\d.)•]+", "", line).strip()
        if len(cleaned) < 18:
            continue
        if cleaned.lower().startswith(RAW_TOOL_NOISE_MARKERS):
            continue
        candidates.append(cleaned)
    return candidates


def _normalize_key_fact(line: str) -> str:
    text = _clean_memory_text(str(line or ""))
    normalized = text.strip().strip("\"'`[]{}(),")
    lowered = normalized.lower()
    if lowered.startswith(FACT_NOISE_PREFIXES):
        return ""
    if any(lowered.startswith(f"{prefix}") for prefix in FACT_NOISE_PREFIXES):
        return ""
    if any(f'"{prefix}' in lowered for prefix in FACT_NOISE_PREFIXES):
        return ""
    if _looks_like_raw_tool_dump(text):
        return ""
    if len(normalized) > 280:
        return ""
    return normalized


def _assistant_action_memory_text(text: str, max_chars: int = 240) -> str:
    """Compress assistant output into one short action summary."""

    cleaned = _clean_memory_text(text)
    lowered = cleaned.lower()
    actions: list[str] = []

    if any(token in lowered for token in ("python", "script", ".py", "code", "bash", "terminal", "run")):
        actions.append("Generated or executed code")
    if any(token in lowered for token in ("pdf", ".pdf", "report")):
        actions.append("Prepared PDF/report output")
    if any(token in lowered for token in ("edit", "patched", "fixed", "исправ")):
        actions.append("Applied code fixes")
    if any(token in lowered for token in ("error", "traceback", "exception", "importerror", "module not found")):
        actions.append("Investigated runtime errors")
    if any(token in lowered for token in ("search", "source", "read page", "web")):
        actions.append("Collected source evidence")

    if not actions:
        for line in _line_candidates(cleaned):
            if len(line) < 24:
                continue
            summary = line[: max_chars - 4].rstrip()
            return f"[{summary}]"
        return "[Completed assistant step]"

    deduped = _dedupe_strings(actions, limit=4)
    summary = "; ".join(deduped)
    if len(summary) > max_chars - 2:
        summary = summary[: max_chars - 5].rstrip() + "..."
    return f"[{summary}]"


def _heuristic_key_facts(
    overflow_entries: list[dict[str, Any]],
    recent_user_messages: list[str],
    direct_user_directives: list[str],
) -> list[str]:
    """Extract durable task facts without copying raw snippets."""

    facts: list[str] = []
    user_blob = " ".join([*recent_user_messages, *direct_user_directives]).strip()
    user_blob_lower = user_blob.lower()
    if user_blob:
        if "фонар" in user_blob_lower or "flashlight" in user_blob_lower or "edc" in user_blob_lower:
            facts.append("Task domain: miniature/EDC flashlights selection.")
        if "pdf" in user_blob_lower or "отчет" in user_blob_lower or "report" in user_blob_lower:
            facts.append("Required deliverable: generated PDF report.")
        budget_match = re.search(r"(\d{3,5})\s*[-–]\s*(\d{3,5})", user_blob)
        if budget_match:
            facts.append(f"Budget constraint: {budget_match.group(1)}-{budget_match.group(2)}.")

    all_text_parts: list[str] = []
    for entry in overflow_entries:
        role = str(entry.get("role") or "").strip().lower()
        if role not in {"user", "assistant", "tool"}:
            continue
        content = _clean_memory_text(str(entry.get("content") or ""))
        if content:
            all_text_parts.append(content)
    all_text = "\n".join(all_text_parts)

    file_hits = _dedupe_strings(
        re.findall(r"\b[\w./\\-]+\.(?:py|pdf|md|json)\b", all_text, flags=re.IGNORECASE),
        limit=6,
    )
    for file_name in file_hits:
        if file_name.lower().endswith(".py"):
            facts.append(f"Code artifact mentioned: {file_name}.")
        if file_name.lower().endswith(".pdf"):
            facts.append(f"Output artifact mentioned: {file_name}.")

    model_hits = _dedupe_strings(
        re.findall(r"\b(?:Fenix|Olight|Nitecore|Acebeam|Wuben|Sofirn|Skilhunt|Thrunite)\s+[A-Za-z0-9\-]{1,24}", all_text),
        limit=8,
    )
    if model_hits:
        facts.append(f"Candidate models mentioned: {', '.join(model_hits[:6])}.")

    return _dedupe_strings(facts, limit=24)


def _deterministic_work_summary(
    overflow_entries: list[dict[str, Any]],
    recent_user_messages: list[str],
    direct_user_directives: list[str],
) -> str:
    """Build a readable chronological summary when model output is unavailable."""

    lines: list[str] = []
    latest_user = next((msg for msg in recent_user_messages if str(msg or "").strip()), "")
    if latest_user:
        lines.append(f"Primary user goal: {latest_user[:260]}")

    if direct_user_directives:
        top_directives = _dedupe_strings([str(x) for x in direct_user_directives], limit=5)
        if top_directives:
            lines.append("Key user directives: " + "; ".join(top_directives))

    tool_events: list[str] = []
    assistant_actions: list[str] = []
    errors: list[str] = []

    def humanize_issue(tool_name: str, raw_text: str) -> str:
        lowered_local = raw_text.lower()
        if "bad_query" in lowered_local:
            if "seo filler" in lowered_local:
                return f"Tool issue ({tool_name}): query rejected due to SEO/filler wording."
            if "more than 6 content words" in lowered_local:
                return f"Tool issue ({tool_name}): query rejected for being too long/over-specified."
            return f"Tool issue ({tool_name}): query rejected by quality guard (BAD_QUERY)."
        if "timeout" in lowered_local:
            return f"Tool issue ({tool_name}): request timed out."
        if "duplicate" in lowered_local and "blocked" in lowered_local:
            return f"Tool issue ({tool_name}): duplicate tool call was blocked."
        if "mode='lines'" in lowered_local and "content" in lowered_local:
            return f"Tool issue ({tool_name}): edit failed because required argument 'content' was missing for mode='lines'."
        if "traceback" in lowered_local or "exception" in lowered_local or "error" in lowered_local:
            return f"Tool issue ({tool_name}): runtime/tool error occurred and required retry or fix."
        return f"Tool issue ({tool_name}): non-ideal tool response required follow-up handling."
    for entry in overflow_entries:
        role = str(entry.get("role") or "").strip().lower()
        text = _clean_memory_text(str(entry.get("content") or ""))
        if not text:
            continue
        lowered = text.lower()

        if role == "tool":
            tool_name = str(entry.get("tool_name") or entry.get("name") or entry.get("alias") or entry.get("tool_id") or "tool").strip()
            lowered = text.lower()
            status = ""
            if "bad_query" in lowered:
                status = "rejected low-quality query (BAD_QUERY)"
            elif "duplicate" in lowered and "blocked" in lowered:
                status = "blocked duplicate tool call"
            elif "timeout" in lowered:
                status = "timed out"
            elif "citation handle" in lowered or "search results" in lowered:
                status = "returned search results/previews"
            elif "**site:**" in lowered or "**url:**" in lowered:
                status = "read source page"
            else:
                status = "returned tool output"
            tool_events.append(f"{tool_name}: {status}")
            if any(token in lowered for token in ("error", "traceback", "exception", "timeout", "failed", "bad_query")):
                errors.append(humanize_issue(tool_name, text))
            continue

        if role == "assistant":
            assistant_actions.append(_assistant_action_memory_text(text, max_chars=220))
            if any(token in lowered for token in ("error", "traceback", "exception", "failed", "importerror")):
                errors.append(f"Assistant-reported issue: {text[:220]}")
            continue

        if role == "user" and any(token in lowered for token in AGGRESSIVE_MARKERS):
            errors.append("User signaled high frustration; response speed and execution quality became critical.")

    tool_events = _dedupe_strings(tool_events, limit=8)
    assistant_actions = _dedupe_strings(assistant_actions, limit=8)
    errors = _dedupe_strings(errors, limit=8)

    if tool_events:
        lines.append("Tool activity: " + " | ".join(tool_events))
    if assistant_actions:
        lines.append("Assistant actions: " + " -> ".join(assistant_actions))
    if errors:
        lines.append("Errors/risks observed: " + " | ".join(errors))

    if not lines:
        return "No reliable historical signal was available; summary fallback is minimal."
    return "\n".join(lines)


def _deterministic_reflection_summary(
    *,
    key_facts: list[str],
    risk_flags: list[str],
    open_tasks: list[str],
    work_summary: str,
) -> str:
    """Build a compact reflective context block for next-step reasoning."""

    reflections: list[str] = []
    if key_facts:
        reflections.append("What is stable: core task constraints and artifacts are identified.")
    if "bad_query" in work_summary.lower():
        reflections.append("Search quality risk: prior queries triggered BAD_QUERY gates; keep future queries shorter and more specific.")
    if any("frustrated" in str(flag).lower() or "aggressive" in str(flag).lower() for flag in risk_flags):
        reflections.append("User state risk: high frustration means execution-first responses are required.")
    if any("import" in str(flag).lower() or "runtime" in str(flag).lower() for flag in risk_flags):
        reflections.append("Technical risk: runtime/import failures were observed and must be re-validated after edits.")
    if open_tasks:
        reflections.append("Outstanding work exists; next turn should prioritize unresolved tasks before expanding scope.")
    else:
        reflections.append("No explicit open tasks were extracted; verify completion criteria against user goal before concluding.")
    return " ".join(reflections)


def _deterministic_memory_payload(
    overflow_entries: list[dict[str, Any]],
    recent_user_messages: list[str],
    direct_user_directives: list[str],
) -> dict[str, Any]:
    urls: list[str] = []
    files: list[str] = []
    tools_used: list[str] = []
    key_facts: list[str] = []
    decisions: list[str] = []
    open_tasks: list[str] = []
    risk_flags: list[str] = []
    source_memory: list[str] = []

    url_pattern = re.compile(r"https?://[^\s)>\]\"']+", flags=re.IGNORECASE)
    file_pattern = re.compile(r"(?:[A-Za-z]:\\[^\n\r\t*?\"<>|]+|[\w./\\-]+\.(?:py|js|ts|json|md|txt|pdf|docx|xlsx|pptx|html|css))")

    for entry in overflow_entries:
        role = str(entry.get("role") or "").strip().lower()
        content = _strip_control_tokens(str(entry.get("content") or ""))
        thinking = "" if role == "assistant" else _strip_control_tokens(str(entry.get("thinking") or ""))
        text = "\n".join(part for part in (content, thinking) if part).strip()
        if not text:
            continue

        urls.extend(url for url in url_pattern.findall(text) if not _is_noisy_url(url))
        files.extend(match.group(0).strip(".,;:") for match in file_pattern.finditer(text))

        if role == "tool":
            tool_name = str(entry.get("tool_name") or entry.get("name") or entry.get("alias") or entry.get("tool_id") or "").strip()
            if tool_name:
                tools_used.append(tool_name)
            site_match = re.search(r"\*\*Site:\*\*\s*([^\n]+)", text)
            title_match = re.search(r"^\s*#\s+(.+)$", text, flags=re.MULTILINE)
            if site_match and title_match:
                tools_used.append(f"read_source:{site_match.group(1).strip()}")

        for line in _line_candidates(text):
            lowered = line.lower()
            if role == "tool":
                if len(key_facts) < 48 and any(marker in lowered for marker in ("vless", "reality", "utls", "ech", "webtunnel", "tls", "xray", "sing-box", "vpn", "protocol")):
                    fact = _normalize_key_fact(line)
                    if fact:
                        key_facts.append(fact)
                continue
            if any(marker in lowered for marker in ("i chose", "chosen", "selected", "decided", "because", "best", "recommended", "recommendation", "top-", "therefore")):
                decisions.append(line[:420])
            if role == "user" and (
                lowered.startswith(("todo", "next:", "next step", "open task"))
                or any(marker in lowered for marker in ("need you to", "still need", "remaining task"))
            ):
                open_tasks.append(line[:360])
            if "risk_flags" not in lowered and any(marker in lowered for marker in ("risk", "danger", "problem", "bug", "blocked")):
                risk_flags.append(line[:360])
            if role == "user" and any(marker in lowered for marker in AGGRESSIVE_MARKERS):
                risk_flags.append("User is highly frustrated/aggressive; prioritize concise execution-focused responses.")
            if any(marker in lowered for marker in ("importerror", "reportlab", "cannot import name a4", "name 'a4'", "module not found")):
                risk_flags.append("Import/runtime error detected in report generation pipeline; verify code fix before final output.")
            if role in {"assistant", "tool"} and len(key_facts) < 48:
                if any(marker in lowered for marker in ("vless", "reality", "utls", "ech", "webtunnel", "tls", "xray", "sing-box", "vpn", "protocol", "протокол")):
                    fact = _normalize_key_fact(line)
                    if fact:
                        key_facts.append(fact)

        if role != "tool":
            if role == "assistant":
                source_line = f"assistant: {_assistant_action_memory_text(text)}"
            elif role == "user":
                user_line = _clean_memory_text(text)
                if len(user_line) > 220:
                    user_line = user_line[:220].rstrip() + "..."
                source_line = f"user: {user_line}"
            else:
                source_line = _entry_memory_text(entry, max_chars=420)
            normalized_source_line = str(source_line or "").strip()
            if normalized_source_line and normalized_source_line.lower() != "assistant:":
                source_memory.append(source_line)

    latest_user = next((msg for msg in recent_user_messages if str(msg or "").strip()), "")
    if not key_facts:
        key_facts = _heuristic_key_facts(overflow_entries, recent_user_messages, direct_user_directives)
    work_summary = _deterministic_work_summary(overflow_entries, recent_user_messages, direct_user_directives)
    sanitized_open_tasks = _sanitize_open_tasks(open_tasks, limit=12)
    if not sanitized_open_tasks and latest_user:
        fallback_task = _fallback_open_task_from_goal(latest_user)
        if fallback_task:
            sanitized_open_tasks = [fallback_task]
    reflection_summary = _deterministic_reflection_summary(
        key_facts=key_facts,
        risk_flags=risk_flags,
        open_tasks=sanitized_open_tasks,
        work_summary=work_summary,
    )
    return {
        "summary_version": 1,
        "session_goal": latest_user[:220],
        "current_focus": latest_user[:220],
        "work_summary": work_summary,
        "reflection_summary": reflection_summary,
        "recent_user_messages": _dedupe_strings(recent_user_messages[:12], limit=12),
        "key_facts": _dedupe_strings(key_facts, limit=48),
        "artifacts": {
            "files": _dedupe_strings(files, limit=32),
            "urls": _dedupe_strings(urls, limit=24),
            "tools_used": _dedupe_strings(tools_used, limit=32),
        },
        "open_tasks": sanitized_open_tasks,
        "risk_flags": _sanitize_semantic_items(risk_flags, limit=12, max_chars=ANALYTIC_ENTRY_MAX_CHARS),
        "source_memory": _sanitize_semantic_items(source_memory, limit=96, max_chars=MEMORY_ENTRY_MAX_CHARS, allow_tool_memory=True),
    }


def _merge_summary_payload(model_payload: dict[str, Any], deterministic: dict[str, Any]) -> dict[str, Any]:
    merged = dict(model_payload) if isinstance(model_payload, dict) else {}
    merged["summary_version"] = 1
    merged.pop("history_highlights", None)
    model_work_summary = _clean_memory_text(str(merged.get("work_summary") or ""))
    deterministic_work_summary = _clean_memory_text(str(deterministic.get("work_summary") or ""))
    if not model_work_summary:
        merged["work_summary"] = deterministic_work_summary
    else:
        if len(model_work_summary) > 6000:
            model_work_summary = model_work_summary[:6000].rstrip() + "..."
        merged["work_summary"] = model_work_summary
    model_reflection_summary = _clean_memory_text(str(merged.get("reflection_summary") or ""))
    deterministic_reflection_summary = _clean_memory_text(str(deterministic.get("reflection_summary") or ""))
    if not model_reflection_summary:
        merged["reflection_summary"] = deterministic_reflection_summary
    else:
        if len(model_reflection_summary) > 2000:
            model_reflection_summary = model_reflection_summary[:2000].rstrip() + "..."
        merged["reflection_summary"] = model_reflection_summary
    for key in ("session_goal", "current_focus"):
        if not str(merged.get(key) or "").strip():
            merged[key] = deterministic.get(key, "")
    semantic_limits = {
        "recent_user_messages": (12, 900, False),
        "key_facts": (48, 420, False),
        "open_tasks": (12, ANALYTIC_ENTRY_MAX_CHARS, False),
        "risk_flags": (12, ANALYTIC_ENTRY_MAX_CHARS, False),
        "source_memory": (96, MEMORY_ENTRY_MAX_CHARS, True),
    }
    for key, (limit, max_chars, allow_tool_memory) in semantic_limits.items():
        values = merged.get(key) if isinstance(merged.get(key), list) else []
        fallback = deterministic.get(key) if isinstance(deterministic.get(key), list) else []
        if key == "open_tasks":
            merged[key] = _sanitize_open_tasks([*values, *fallback], limit=limit)
            if not merged[key]:
                fallback_task = _fallback_open_task_from_goal(str(merged.get("current_focus") or merged.get("session_goal") or ""))
                if fallback_task:
                    merged[key] = [fallback_task]
            continue
        merged[key] = _sanitize_semantic_items(
            [*values, *fallback],
            limit=limit,
            max_chars=max_chars,
            allow_tool_memory=allow_tool_memory,
        )

    artifacts = merged.get("artifacts") if isinstance(merged.get("artifacts"), dict) else {}
    deterministic_artifacts = deterministic.get("artifacts") if isinstance(deterministic.get("artifacts"), dict) else {}
    merged["artifacts"] = {
        "files": _dedupe_strings([*(artifacts.get("files") if isinstance(artifacts.get("files"), list) else []), *(deterministic_artifacts.get("files") or [])], limit=32),
        "urls": _dedupe_strings([url for url in [*(artifacts.get("urls") if isinstance(artifacts.get("urls"), list) else []), *(deterministic_artifacts.get("urls") or [])] if not _is_noisy_url(url)], limit=24),
        "tools_used": _dedupe_strings([*(artifacts.get("tools_used") if isinstance(artifacts.get("tools_used"), list) else []), *(deterministic_artifacts.get("tools_used") or [])], limit=32),
    }
    return merged


def _summary_text_from_payload(payload: dict[str, Any]) -> str:
    return "[Conversation History Summary Base]\n" + json.dumps(payload, ensure_ascii=False, indent=2)


def _expand_payload_to_target(
    payload: dict[str, Any],
    overflow_entries: list[dict[str, Any]],
    *,
    target_min_chars: int = COMPRESSION_TARGET_MIN_CHARS,
) -> dict[str, Any]:
    """Add detailed memory excerpts until the summary is useful, not tiny."""

    expanded = dict(payload)
    existing_source = expanded.get("source_memory") if isinstance(expanded.get("source_memory"), list) else []
    source_memory = [str(item) for item in existing_source if str(item or "").strip()]
    seen = {item.lower() for item in source_memory}

    for entry in overflow_entries:
        if len(_summary_text_from_payload({**expanded, "source_memory": source_memory})) >= target_min_chars:
            break
        role = str(entry.get("role") or "").strip().lower()
        if role == "tool":
            continue
        raw_text = _clean_memory_text(str(entry.get("content") or ""))
        if role == "assistant":
            text = f"assistant: {_assistant_action_memory_text(raw_text)}"
        elif role == "user":
            user_line = raw_text[:220].rstrip() + "..." if len(raw_text) > 220 else raw_text
            text = f"user: {user_line}" if user_line else ""
        else:
            text = _entry_memory_text(entry, max_chars=420)
        if not text.strip():
            continue
        if _looks_like_raw_tool_dump(text):
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        source_memory.append(text)

    expanded["source_memory"] = source_memory
    return expanded


def fit_summary_text(summary_payload: dict[str, Any], max_chars: int) -> tuple[str, dict[str, Any]]:
    """Fit a summary into a character budget while preserving valid JSON."""

    try:
        budget = int(max_chars)
    except (TypeError, ValueError):
        budget = 0
    if budget <= 0:
        return _summary_text_from_payload(summary_payload), summary_payload

    fitted = json.loads(json.dumps(summary_payload, ensure_ascii=False))
    if not isinstance(fitted, dict):
        fitted = {}

    if len(_summary_text_from_payload(fitted)) <= budget:
        return _summary_text_from_payload(fitted), fitted

    risk_flags = fitted.get("risk_flags") if isinstance(fitted.get("risk_flags"), list) else []
    risk_flags.append("Compression summary was size-fitted; low-priority excerpts may be omitted.")
    fitted["risk_flags"] = risk_flags

    shrink_order = [
        "reflection_summary",
        "work_summary",
        "source_memory",
        "key_facts",
        "open_tasks",
        "recent_user_messages",
    ]
    for key in shrink_order:
        if key == "work_summary":
            text = str(fitted.get("work_summary") or "")
            if len(text) > 2400 and len(_summary_text_from_payload(fitted)) > budget:
                fitted["work_summary"] = text[:2400].rstrip() + "..."
            continue
        if key == "reflection_summary":
            text = str(fitted.get("reflection_summary") or "")
            if len(text) > 1200 and len(_summary_text_from_payload(fitted)) > budget:
                fitted["reflection_summary"] = text[:1200].rstrip() + "..."
            continue
        values = fitted.get(key)
        if not isinstance(values, list):
            continue
        while len(values) > 8 and len(_summary_text_from_payload(fitted)) > budget:
            values.pop()

    artifacts = fitted.get("artifacts") if isinstance(fitted.get("artifacts"), dict) else {}
    for key in ("urls", "files", "tools_used"):
        values = artifacts.get(key)
        if not isinstance(values, list):
            continue
        while len(values) > 8 and len(_summary_text_from_payload(fitted)) > budget:
            values.pop()

    for key in ("source_memory", "key_facts"):
        values = fitted.get(key)
        if not isinstance(values, list):
            continue
        for index, value in enumerate(list(values)):
            if len(_summary_text_from_payload(fitted)) <= budget:
                break
            text = str(value)
            if len(text) > 700:
                values[index] = text[:700].rstrip() + "..."

    while len(_summary_text_from_payload(fitted)) > budget:
        values = fitted.get("source_memory")
        if isinstance(values, list) and values:
            values.pop()
            continue
        break

    return _summary_text_from_payload(fitted), fitted


def _extract_json_object(text: str) -> dict[str, Any] | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, flags=re.IGNORECASE)
    if fence_match:
        raw = fence_match.group(1).strip()
    try:
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else None
    except ValueError:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end > start:
        try:
            payload = json.loads(raw[start:end + 1])
            return payload if isinstance(payload, dict) else None
        except ValueError:
            return None
    return None


def _fallback_summary_payload(
    overflow_entries: list[dict[str, Any]],
    recent_user_messages: list[str],
    direct_user_directives: list[str],
) -> dict[str, Any]:
    return _deterministic_memory_payload(overflow_entries, recent_user_messages, direct_user_directives)


def build_structured_history_summary(
    *,
    overflow_entries: list[dict[str, Any]],
    recent_user_messages: list[str],
    direct_user_directives: list[str],
    summarize_with_model: Callable[[list[dict[str, str]]], str] | None,
    max_overflow_entries: int = 40,
) -> tuple[str, dict[str, Any]]:
    """Return a structured compression block and parsed payload metadata."""

    scoped_full = overflow_entries[-max(1, max_overflow_entries):]
    scoped = _scoped_context_entries(scoped_full)
    transcript_lines = []
    for idx, entry in enumerate(scoped, 1):
        entry_text = _compression_prompt_entry_text(entry)
        if entry_text:
            transcript_lines.append(f"[{idx}] {entry_text}")
    transcript = "\n".join(transcript_lines)

    summary_payload: dict[str, Any] | None = None
    if summarize_with_model is not None and transcript.strip():
        prompt_messages = [
            {
                "role": "system",
                "content": (
                    "You compress chat history into a strict structured JSON knowledge base.\n"
                    "Return JSON only. No markdown. No prose.\n"
                    "Preserve concrete facts, paths, URLs, explicit user directives, tool outcomes, and open tasks.\n"
                    "Do not include apologies or filler.\n"
                    "Never copy raw tool calls, terminal logs, JSON tool payloads, diffs, tracebacks, citation boilerplate, or search-result lists into the output.\n"
                    "Instead, infer concise outcomes and durable facts from tool observations."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Build a structured history base using this schema:\n"
                    "{\n"
                    "  \"summary_version\": 1,\n"
                    "  \"session_goal\": string,\n"
                    "  \"current_focus\": string,\n"
                    "  \"work_summary\": string,\n"
                    "  \"reflection_summary\": string,\n"
                    "  \"recent_user_messages\": string[],\n"
                    "  \"key_facts\": string[],\n"
                    "  \"artifacts\": {\"files\": string[], \"urls\": string[], \"tools_used\": string[]},\n"
                    "  \"open_tasks\": string[],\n"
                    "  \"risk_flags\": string[],\n"
                    "  \"source_memory\": string[]\n"
                    "}\n\n"
                    "IMPORTANT:\n"
                    "- This is a large memory base, not a tiny summary.\n"
                    "- Be exhaustive about durable session state: user goal, constraints, completed actions, files changed, errors fixed, current answer facts, and remaining work.\n"
                    "- work_summary must be a detailed narrative block (multi-sentence, chronological) describing what happened in the dialogue, which tools were used, what failed, what was fixed, and what remains.\n"
                    "- reflection_summary must be a concise analytical reflection: what is reliable, what is uncertain, key risks, and the best next-step strategy.\n"
                    "- Fill each field by semantics, not by keyword matching.\n"
                    "- Treat assistant reasoning/thinking as unreliable scratchpad; do not copy it into open_tasks, key_facts, or risk_flags unless the final visible answer or user explicitly confirms it.\n"
                    "- key_facts must contain task parameters and extracted domain facts only; never copy user messages verbatim into key_facts.\n"
                    "- decisions_and_rationale must contain only actual decisions plus why they were made; leave it empty if no decision exists.\n"
                    "- open_tasks must contain model-generated next actions, not copied reasoning. If the latest user goal is not explicitly confirmed complete by the user, write at least one concrete verification or continuation task.\n"
                    "- Leave open_tasks empty only when the user explicitly confirmed the goal is complete or there is truly no actionable next step.\n"
                    "- Never put partial thought fragments in open_tasks (examples: \"We need...\", \"Now combine...\", \"Wait...\", \"Check balancing...\").\n"
                    "- risk_flags must contain only warnings that affect future work; leave it empty if none exist.\n"
                    "- Do not put raw search snippets, citation instructions, terminal logs, tool JSON, diffs, or page dumps into any field.\n"
                    "- source_memory must preserve curated detailed excerpts from important user/assistant turns only; never store entries beginning with tool:.\n"
                    "- For assistant entries in source_memory, summarize actions in square brackets (example: assistant: [Applied edit and fixed import]); do not quote long assistant outputs.\n"
                    "- Do not duplicate the same long text twice in different fields.\n"
                    "- Include direct user instructions verbatim when possible.\n"
                    "- Keep file paths and URLs exact.\n"
                    "- recent_user_messages must include no more than the latest 5 user turns.\n"
                    "- Raw context below contains at most the first 3 and last 5 compressed-span entries; infer the rest from directives, artifacts, and tool observations.\n\n"
                    f"Direct user directives:\n{json.dumps(direct_user_directives[:24], ensure_ascii=False)}\n\n"
                    f"Recent user messages:\n{json.dumps(recent_user_messages[:5], ensure_ascii=False)}\n\n"
                    f"Compressed-span context:\n{transcript}"
                ),
            },
        ]
        model_text = summarize_with_model(prompt_messages)
        summary_payload = _extract_json_object(model_text)

    deterministic_payload = _deterministic_memory_payload(scoped_full, recent_user_messages[:5], direct_user_directives)
    if not isinstance(summary_payload, dict):
        summary_payload = deterministic_payload
    else:
        summary_payload = _merge_summary_payload(summary_payload, deterministic_payload)

    summary_payload.setdefault("summary_version", 1)
    summary_payload = _expand_payload_to_target(summary_payload, scoped_full, target_min_chars=COMPRESSION_TARGET_MIN_CHARS)
    summary_text = _summary_text_from_payload(summary_payload)
    return summary_text, summary_payload

