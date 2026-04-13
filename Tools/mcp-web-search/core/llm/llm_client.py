# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""
LLM client for deep research.

Architecture
------------
RuntimeProvider — frozen dataclass describing one engine's transport and schema mode.
_resolve_runtime_provider() — returns a RuntimeProvider for the active engine (LMS).

Active engine: LMS (LM Studio, OpenAI-compat).
Other providers (Ollama, Claude, Gemini, OpenRouter) tracked in todo.md.

Public API
----------
get_session() / close_session()   — shared aiohttp session lifecycle
call_llm(prompt, model, ...)      — returns raw response text or None
call_llm_json(prompt, model, ...) — returns parsed JSON object or None
extract_json(text, schema)        — parse / repair JSON from LLM output
RuntimeProvider                   — provider descriptor (for type hints in callers)
"""

from __future__ import annotations

import aiohttp
import asyncio
import ast
import json
import os
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

try:
    import jsonschema as _jsonschema
except ImportError:
    _jsonschema = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Shared aiohttp session
# ---------------------------------------------------------------------------

_session: Optional[aiohttp.ClientSession] = None
_session_lock = threading.Lock()
_reconnect_lock: Optional[asyncio.Lock] = None


def _get_reconnect_lock() -> asyncio.Lock:
    """Lazy-init asyncio.Lock (must be accessed from within a running event loop)."""
    global _reconnect_lock
    if _reconnect_lock is None:
        _reconnect_lock = asyncio.Lock()
    return _reconnect_lock


async def get_session() -> aiohttp.ClientSession:
    """Return the shared aiohttp session, creating it if closed or absent."""
    global _session
    with _session_lock:
        if _session is None or _session.closed:
            connector = aiohttp.TCPConnector(
                limit=8,
                limit_per_host=8,
                keepalive_timeout=30,
                ttl_dns_cache=300,
            )
            _session = aiohttp.ClientSession(connector=connector)
    return _session


async def close_session() -> None:
    """Close and discard the shared aiohttp session."""
    global _session
    to_close: Optional[aiohttp.ClientSession] = None
    with _session_lock:
        if _session is not None and not _session.closed:
            to_close = _session
        _session = None
    if to_close is not None:
        await to_close.close()


# ---------------------------------------------------------------------------
# Constants (defaults; callers can override per-request)
# ---------------------------------------------------------------------------

_LMS_BASE_URL = "http://127.0.0.1:1234/v1"
_LMS_MODEL_PLACEHOLDER = "local-model"

LLM_STRUCTURED_OUTPUT_ENABLED: bool = True
LLM_STRUCTURED_OUTPUT_STRICT: bool = True
LLM_REASONING_EFFORT: str = "low"
LLM_REASONING_TOKENS: int = 2048
LLM_REASONING_MODE: str = "none"   # "effort" | "on_off" | "none"
LLM_REASONING_PROMPT: str = (
    "Be concise. Think briefly before answering."
)

# JSON wrapper keys tried when unwrapping model responses.
_JSON_WRAPPER_KEYS = ("corrected_response", "response", "data", "result", "output", "payload")

_SMART_QUOTES = str.maketrans({
    "\u2018": "'", "\u2019": "'",
    "\u201c": '"', "\u201d": '"',
    "\u2032": "'", "\u2033": '"',
})

# ---------------------------------------------------------------------------
# RuntimeProvider — per-engine transport descriptor
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RuntimeProvider:
    """Immutable descriptor for one LLM engine's transport and schema mode.

    structured_mode:
        "response_format_json_schema"  — OpenAI-compat (current: lms)

    reasoning_effort_style:
        ""        — do not send reasoning params
        "effort"  — send reasoning_effort as-is (low/medium/high)
        "on_off"  — map any non-empty effort → "on", absent → "off"
    """

    provider_id: str
    engine: str
    endpoint: str
    transport: str
    headers: dict[str, str]
    structured_mode: str
    reasoning_effort_style: str = ""
    supports_reasoning_tokens: bool = False


# ---------------------------------------------------------------------------
# Engine resolution — lms only (other branches are stubs for future use)
# ---------------------------------------------------------------------------

def _openai_chat_url(base: str) -> str:
    base = base.rstrip("/")
    if "://" not in base:
        base = f"http://{base}"
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def _runtime_lms_base_url() -> str:
    """Read LMS base URL from env or fall back to localhost:1234."""
    env_url = os.getenv("ASLM_LMS_URL", "").strip()
    if env_url:
        return env_url
    # Try to pull from ASLM Settings module if available.
    try:
        from Settings import settings as _s
        url = str(_s.get_engine_url("lms") or "").strip()
        if url:
            return url
    except Exception:
        pass
    return _LMS_BASE_URL


def _resolve_runtime_provider() -> RuntimeProvider:
    """Return a RuntimeProvider for the currently active engine (LMS only).

    Other providers (Ollama, Claude, Gemini, OpenRouter) are tracked in todo.md
    and will be wired here when activated. Ollama requires the ASLM Ollama URL
    from ASLM config (not a hardcoded port) and native /api/chat transport.
    """
    lms_url = _runtime_lms_base_url()
    lms_reasoning_style = os.getenv("ASLM_LLM_REASONING_MODE", LLM_REASONING_MODE).strip().lower()
    if lms_reasoning_style == "none":
        lms_reasoning_style = ""
    return RuntimeProvider(
        provider_id="lms",
        engine="lms",
        endpoint=_openai_chat_url(lms_url),
        transport="openai_compat",
        headers={"Content-Type": "application/json"},
        structured_mode="response_format_json_schema",
        reasoning_effort_style=lms_reasoning_style,
        supports_reasoning_tokens=(lms_reasoning_style == "effort"),
    )


# ---------------------------------------------------------------------------
# Payload builders
# ---------------------------------------------------------------------------

def _build_response_format(
    *,
    schema_name: str,
    json_schema: Optional[dict[str, Any]],
    strict: bool,
) -> Optional[dict[str, Any]]:
    """Build response_format payload for OpenAI-compat endpoints.

    Returns None when no schema is provided — callers must NOT include
    response_format in the payload in that case.  "json_object" mode is
    intentionally avoided: some LMS versions (e.g. LM Studio ≥ 0.3.x)
    reject it with HTTP 400 and only accept "json_schema" or "text".
    """
    if json_schema:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "strict": strict,
                "schema": json_schema,
            },
        }
    return None


def _build_payload(
    *,
    provider: RuntimeProvider,
    prompt: str,
    model: str,
    system: str,
    temperature: float,
    max_tokens: int,
    json_schema: Optional[dict[str, Any]],
    schema_name: str,
    structured_output: bool,
    strict: bool,
    reasoning_effort: Optional[str],
    reasoning_tokens: Optional[int],
) -> dict[str, Any]:
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "frequency_penalty": 0.5,
        "stream": False,
    }
    if structured_output:
        fmt = _build_response_format(
            schema_name=schema_name,
            json_schema=json_schema,
            strict=strict,
        )
        if fmt is not None:
            payload["response_format"] = fmt
    if provider.reasoning_effort_style and reasoning_effort:
        if provider.reasoning_effort_style == "on_off":
            payload["reasoning_effort"] = (
                "off" if reasoning_effort in ("off", "none", "") else "on"
            )
        else:
            payload["reasoning_effort"] = reasoning_effort
    if provider.supports_reasoning_tokens and reasoning_tokens and reasoning_tokens > 0:
        payload["reasoning_tokens"] = int(reasoning_tokens)
    return payload


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def _coerce_response_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content") or ""
                if text:
                    parts.append(str(text))
        return "".join(parts)
    if content is None:
        return ""
    return str(content)


def _extract_thinking(data: dict[str, Any]) -> str:
    """Extract raw reasoning/thinking content from an LLM response (for CoT logging).

    Field name differs by provider:
      - LMS / OpenAI-compat reasoning models → "reasoning_content"
      - Ollama (Qwen3, etc.)                 → "reasoning"
    """
    choices = data.get("choices") or []
    if not choices:
        return ""
    message = (choices[0] or {}).get("message") or {}
    return (
        _coerce_response_text(message.get("reasoning_content"))
        or _coerce_response_text(message.get("reasoning"))
    )


def _extract_response_text(provider: RuntimeProvider, data: dict[str, Any]) -> str:
    # OpenAI-compat (LMS)
    choices = data.get("choices") or []
    if not choices:
        return ""
    message = (choices[0] or {}).get("message") or {}
    content = _coerce_response_text(message.get("content"))

    # Some reasoning models (Gemma-4, QwQ, etc.) leak the tail of their output
    # into "reasoning_content" instead of "content".  When content looks like a
    # truncated JSON (unbalanced brackets) and reasoning_content is non-empty,
    # append it so the parser gets the full text.
    reasoning = _coerce_response_text(message.get("reasoning_content"))
    if reasoning:
        combined = content + reasoning
        # Only use the combined version when it is more balanced than content alone.
        def _balance(text: str) -> int:
            depth = 0
            in_str = False
            esc = False
            for ch in text:
                if esc:
                    esc = False
                    continue
                if ch == "\\":
                    esc = True
                    continue
                if ch == '"':
                    in_str = not in_str
                    continue
                if in_str:
                    continue
                if ch in ("{", "["):
                    depth += 1
                elif ch in ("}", "]"):
                    depth -= 1
            return depth

        if abs(_balance(combined)) < abs(_balance(content)):
            content = combined

    return content


# ---------------------------------------------------------------------------
# JSON extraction helpers
# ---------------------------------------------------------------------------

def _normalize_jsonish_text(candidate: str) -> str:
    text = str(candidate or "").strip().lstrip("\ufeff")
    if not text:
        return ""
    text = text.translate(_SMART_QUOTES)
    text = re.sub(r"^\s*json\s*[:\-]?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*response\s*[:\-]?\s*", "", text, flags=re.IGNORECASE)
    return text.strip()


def _strip_json_comments(candidate: str) -> str:
    text = str(candidate or "")
    if not text:
        return text
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    cleaned_lines: list[str] = []
    for line in text.splitlines():
        if "//" in line:
            quote_count = line.count('"') - line.count('\\"')
            if quote_count % 2 == 0:
                line = re.sub(r"//.*$", "", line)
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines)


def _repair_unquoted_object_keys(candidate: str) -> str:
    return re.sub(
        r'([{\[,]\s*)([A-Za-z_][A-Za-z0-9_.\-]*)(\s*:)',
        lambda m: f'{m.group(1)}"{m.group(2)}"{m.group(3)}',
        candidate,
    )


def _unwrap_common_json_wrappers(value: Any) -> Any:
    current = value
    for _ in range(3):
        if not isinstance(current, dict):
            break
        for key in _JSON_WRAPPER_KEYS:
            nested = current.get(key)
            if isinstance(nested, (dict, list)):
                current = nested
                break
        else:
            content = current.get("content")
            if isinstance(content, (dict, list)):
                current = content
                continue
            break
    return current


def _schema_guided_recover(data: Any, schema: Optional[dict[str, Any]]) -> Any | None:
    if data is None or schema is None:
        return None
    schema_type = str(schema.get("type") or "").strip().lower()
    if not schema_type:
        return None
    if schema_type == "array":
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in _JSON_WRAPPER_KEYS:
                nested = data.get(key)
                if isinstance(nested, list):
                    return nested
            for value in data.values():
                if isinstance(value, list):
                    return value
        return None
    if schema_type == "object":
        if isinstance(data, dict):
            return data
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    return item
        return None
    return None


def _validate_schema(data: Any, schema: Optional[dict[str, Any]]) -> bool:
    if schema is None or _jsonschema is None:
        return True
    try:
        _jsonschema.validate(data, schema)
        return True
    except Exception:
        return False


def _balanced_json_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    for opener, closer in (("{", "}"), ("[", "]")):
        for start in [i for i, c in enumerate(text) if c == opener]:
            depth = 0
            in_string = False
            escape = False
            for index in range(start, len(text)):
                char = text[index]
                if escape:
                    escape = False
                    continue
                if char == "\\":
                    escape = True
                    continue
                if char == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if char == opener:
                    depth += 1
                elif char == closer:
                    depth -= 1
                    if depth == 0:
                        candidates.append(text[start:index + 1])
                        break
    return candidates


def _try_parse_json_candidate(candidate: str) -> Any | None:
    text = _normalize_jsonish_text(candidate)
    if not text:
        return None
    attempts: list[str] = []

    def _push(value: str) -> None:
        cleaned = value.strip()
        if cleaned and cleaned not in attempts:
            attempts.append(cleaned)

    _push(text)
    _push(_strip_json_comments(text))
    _push(re.sub(r",(\s*[}\]])", r"\1", text))
    _push(re.sub(r",(\s*[}\]])", r"\1", _strip_json_comments(text)))
    _push(_repair_unquoted_object_keys(text))
    _push(_repair_unquoted_object_keys(_strip_json_comments(text)))
    _push(re.sub(r",(\s*[}\]])", r"\1", _repair_unquoted_object_keys(text)))
    _push(re.sub(r",(\s*[}\]])", r"\1",
                 _repair_unquoted_object_keys(_strip_json_comments(text))))

    for attempt in attempts:
        try:
            parsed = _unwrap_common_json_wrappers(json.loads(attempt))
            if isinstance(parsed, str) and parsed.strip() != attempt.strip():
                reparsed = _try_parse_json_candidate(parsed)
                if reparsed is not None:
                    return reparsed
            return parsed
        except json.JSONDecodeError:
            try:
                parsed = ast.literal_eval(attempt)
            except (SyntaxError, ValueError):
                continue
            if isinstance(parsed, str) and parsed.strip() != attempt.strip():
                reparsed = _try_parse_json_candidate(parsed)
                if reparsed is not None:
                    return reparsed
            if isinstance(parsed, (dict, list, str)):
                return _unwrap_common_json_wrappers(parsed)
    return None


def extract_json(text: str, schema: Optional[dict[str, Any]] = None) -> Optional[object]:
    """Extract and optionally validate JSON from a model response.

    Tries multiple repair strategies (comment stripping, trailing-comma removal,
    unquoted-key repair, balanced-bracket extraction).  Falls back to best-effort
    when strict schema validation fails but the base type matches.
    """
    raw_text = str(text or "").strip()
    if not raw_text:
        return None

    candidate_texts: list[str] = [raw_text]
    for match in re.finditer(r"```(?:json)?\s*(.*?)\s*```", raw_text, re.DOTALL | re.IGNORECASE):
        candidate_texts.append(match.group(1).strip())
    candidate_texts.extend(_balanced_json_candidates(raw_text))

    schema_type = str((schema or {}).get("type") or "").strip().lower()
    best_effort: Any = None

    for candidate in candidate_texts:
        parsed = _try_parse_json_candidate(candidate)
        if parsed is not None and _validate_schema(parsed, schema):
            return parsed
        repaired = _schema_guided_recover(parsed, schema)
        if repaired is not None and _validate_schema(repaired, schema):
            return repaired
        # Track best-effort (right base type, failed count/constraint validation)
        if best_effort is None and schema_type:
            for obj in (repaired, parsed):
                if obj is None:
                    continue
                if schema_type == "array" and isinstance(obj, list):
                    best_effort = obj
                    break
                if schema_type == "object" and isinstance(obj, dict):
                    best_effort = obj
                    break

    return best_effort


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _compact_debug_text(text: Any, limit: int = 160) -> str:
    raw = re.sub(r"\s+", " ", str(text or "")).strip()
    return raw if len(raw) <= limit else raw[:limit - 3] + "..."


# ---------------------------------------------------------------------------
# Public API: call_llm / call_llm_json
# ---------------------------------------------------------------------------

async def call_llm(
    prompt: str,
    model: str = _LMS_MODEL_PLACEHOLDER,
    system: str = "",
    temperature: float = 0.3,
    max_tokens: int = 4096,
    timeout: float = 120.0,
    json_schema: Optional[dict[str, Any]] = None,
    schema_name: str = "structured_output",
    structured_output: bool = False,
    strict: bool = LLM_STRUCTURED_OUTPUT_STRICT,
    reasoning_effort: Optional[str] = None,
    reasoning_tokens: Optional[int] = None,
    cot_sink: Optional[Callable[[str], None]] = None,
    debug_label: str = "",
    debug_log: Optional[Callable[[str], None]] = None,
) -> Optional[str]:
    """Call the active LLM provider and return raw response text, or None on failure."""
    provider = _resolve_runtime_provider()
    start_ts = time.time()
    payload = _build_payload(
        provider=provider,
        prompt=prompt,
        model=model,
        system=system,
        temperature=temperature,
        max_tokens=max_tokens,
        json_schema=json_schema,
        schema_name=schema_name,
        structured_output=structured_output,
        strict=strict,
        reasoning_effort=reasoning_effort,
        reasoning_tokens=reasoning_tokens,
    )
    if debug_log is not None:
        label = debug_label or schema_name
        debug_log(
            f"  [llm] {label}: start provider={provider.engine} "
            f"model={model} structured={structured_output} timeout={timeout:.1f}s"
        )

    async def _do_request(session: aiohttp.ClientSession) -> Optional[str]:
        async with session.post(
            provider.endpoint,
            headers=provider.headers,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as response:
            if response.status != 200:
                if debug_log is not None:
                    try:
                        body = await response.text()
                    except Exception:
                        body = ""
                    label = f"{debug_label}: " if debug_label else ""
                    debug_log(
                        f"  [llm] {label}HTTP {response.status} from {provider.engine} "
                        f"after {time.time() - start_ts:.1f}s"
                        + (f" | {_compact_debug_text(body)}" if body else "")
                    )
                return None
            data = await response.json()
            if cot_sink is not None:
                thinking = _extract_thinking(data)
                if thinking:
                    try:
                        cot_sink(thinking)
                    except Exception:
                        pass
            content = _extract_response_text(provider, data)
            if debug_log is not None:
                label = debug_label or schema_name
                debug_log(
                    f"  [llm] {label}: done in {time.time() - start_ts:.1f}s "
                    f"chars={len(content or '')}"
                )
            return content

    async def _with_reconnect_retry() -> Optional[str]:
        """One reconnect-and-retry for stale/dropped connections.

        Serialized via asyncio.Lock so that concurrent tasks don't race to
        close/recreate the session simultaneously (which would cause the second
        task to destroy the session the first task just created).
        """
        async with _get_reconnect_lock():
            # If another task already reconnected while we waited, the session
            # may be healthy now — try it first without closing.
            try:
                existing = await get_session()
                if not existing.closed:
                    return await _do_request(existing)
            except (aiohttp.ServerDisconnectedError, aiohttp.ClientConnectionError):
                pass
            except Exception:
                pass
            # Session is still bad — close and recreate.
            await close_session()
            try:
                session = await get_session()
                return await _do_request(session)
            except Exception as inner:
                if debug_log is not None:
                    debug_log(
                        f"  [llm] {debug_label or schema_name}: reconnect retry failed "
                        f"after {time.time() - start_ts:.1f}s ({type(inner).__name__}: {inner})"
                    )
                return None

    try:
        session = await get_session()
        return await _do_request(session)
    except aiohttp.ServerDisconnectedError:
        # LMS closed the idle TCP connection (e.g. during a long dedup phase).
        # Reconnect and retry once — this is always transient.
        if debug_log is not None:
            debug_log(
                f"  [llm] {debug_label or schema_name}: ServerDisconnected — reconnecting"
            )
        return await _with_reconnect_retry()
    except RuntimeError as err:
        if "Session is closed" in str(err):
            return await _with_reconnect_retry()
        if debug_log is not None:
            debug_log(
                f"  [llm] {debug_label or schema_name}: runtime error "
                f"after {time.time() - start_ts:.1f}s ({type(err).__name__}: {err})"
            )
        return None
    except (aiohttp.ClientError, asyncio.TimeoutError, KeyError, IndexError) as err:
        if debug_log is not None:
            debug_log(
                f"  [llm] {debug_label or schema_name}: request failed "
                f"after {time.time() - start_ts:.1f}s ({type(err).__name__}: {err})"
            )
        return None


async def call_llm_json(
    prompt: str,
    model: str = _LMS_MODEL_PLACEHOLDER,
    system: str = "",
    temperature: float = 0.3,
    max_tokens: int = 4096,
    timeout: float = 120.0,
    json_schema: Optional[dict[str, Any]] = None,
    schema_name: str = "structured_output",
    structured_output: bool = LLM_STRUCTURED_OUTPUT_ENABLED,
    strict: bool = LLM_STRUCTURED_OUTPUT_STRICT,
    reasoning_effort: str = LLM_REASONING_EFFORT,
    reasoning_tokens: int = LLM_REASONING_TOKENS,
    concise_reasoning_prompt: str = LLM_REASONING_PROMPT,
    cot_sink: Optional[Callable[[str], None]] = None,
    debug_label: str = "",
    debug_log: Optional[Callable[[str], None]] = None,
) -> Optional[object]:
    """Call the LLM and parse a JSON object from the response.

    If structured_output=True and the first attempt yields no valid JSON,
    retries once with structured_output=False and a stricter system prompt.
    """
    start_ts = time.time()
    effective_system = system.strip()
    concise_instruction = str(concise_reasoning_prompt or "").strip()
    if concise_instruction:
        suffix = (
            f"{concise_instruction} "
            "Return only the requested JSON and no extra prose."
        ).strip()
        effective_system = (
            f"{effective_system}\n\n{suffix}".strip() if effective_system else suffix
        )

    response = await call_llm(
        prompt=prompt,
        model=model,
        system=effective_system,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
        json_schema=json_schema,
        schema_name=schema_name,
        structured_output=structured_output,
        strict=strict,
        reasoning_effort=reasoning_effort,
        reasoning_tokens=reasoning_tokens,
        cot_sink=cot_sink,
        debug_label=debug_label or schema_name,
        debug_log=debug_log,
    )
    parsed = extract_json(response or "", schema=json_schema)
    if parsed is not None:
        validated = _validate_schema(parsed, json_schema)
        if debug_log is not None:
            status = "parsed+valid" if validated else "parsed(best-effort, schema mismatch)"
            debug_log(
                f"  [llm] {debug_label or schema_name}: {status} "
                f"{type(parsed).__name__} in {time.time() - start_ts:.1f}s"
            )
        return parsed

    # Fallback: retry without provider structured-output mode
    if structured_output:
        if debug_log is not None:
            debug_log(
                f"  [llm] {debug_label or schema_name}: "
                "structured attempt produced no parseable JSON — retrying without structured_output"
            )
        fallback_system = (
            f"{effective_system}\n\n"
            "The previous attempt did not produce schema-valid JSON. "
            "Output valid JSON only. No markdown, no commentary, no surrounding text."
        ).strip()
        fallback_response = await call_llm(
            prompt=prompt,
            model=model,
            system=fallback_system,
            temperature=min(temperature, 0.2),
            max_tokens=max_tokens,
            timeout=timeout,
            json_schema=json_schema,
            schema_name=schema_name,
            structured_output=False,
            strict=strict,
            reasoning_effort=reasoning_effort,
            reasoning_tokens=reasoning_tokens,
            cot_sink=cot_sink,
            debug_label=debug_label or schema_name,
            debug_log=debug_log,
        )
        parsed = extract_json(fallback_response or "", schema=json_schema)
        if parsed is not None:
            if debug_log is not None:
                debug_log(
                    f"  [llm] {debug_label or schema_name}: parsed fallback "
                    f"{type(parsed).__name__} in {time.time() - start_ts:.1f}s"
                )
            return parsed
        if debug_log is not None:
            debug_log(
                f"  [llm] {debug_label or schema_name}: "
                f"JSON parse failed after {time.time() - start_ts:.1f}s"
            )

    return None
