# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import aiohttp
import asyncio
import ast
import json
import os
import re
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import urlsplit

from .config import (
    LLM_REASONING_EFFORT,
    LLM_REASONING_MODE,
    LLM_REASONING_PROMPT,
    LLM_REASONING_TOKENS,
    LLM_STRUCTURED_OUTPUT_ENABLED,
    LLM_STRUCTURED_OUTPUT_STRICT,
    LM_STUDIO_URL,
)

try:
    import jsonschema as _jsonschema
except Exception:  # pragma: no cover - optional dependency
    _jsonschema = None

_session: Optional[aiohttp.ClientSession] = None
_session_lock = threading.Lock()

_ENGINE_ALIASES = {
    "anthropic": "claude",
    "claude": "claude",
    "gemini": "gemini",
    "grok": "grok",
    "lm-studio": "lms",
    "lms": "lms",
    "ollama": "ollama-service",
    "ollama-service": "ollama-service",
    "openai": "openai",
    "openai-api": "openai",
    "openrouter": "openrouter",
}

_OPENAI_COMPAT_DEFAULTS = {
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "grok": "https://api.x.ai/v1",
    "openai": "https://api.openai.com/v1",
    "openai-compatible": "http://127.0.0.1:8000/v1",
    "openrouter": "https://openrouter.ai/api/v1",
}

_OPENAI_COMPAT_HOSTS = {
    "api.openai.com": "openai",
    "api.x.ai": "grok",
    "generativelanguage.googleapis.com": "gemini",
    "openrouter.ai": "openrouter",
}

_OPENAI_COMPAT_API_KEY_ENVS = {
    "gemini": ("GEMINI_API_KEY", "OPENAI_API_KEY"),
    "grok": ("GROK_API_KEY", "XAI_API_KEY", "OPENAI_API_KEY"),
    "openai": ("OPENAI_API_KEY",),
    "openai-compatible": ("OPENAI_API_KEY",),
    "openrouter": ("OPENROUTER_API_KEY", "OR_API_KEY", "OPENAI_API_KEY"),
}

_JSON_WRAPPER_KEYS = (
    "corrected_response",
    "response",
    "data",
    "result",
    "output",
    "payload",
)

_SMART_QUOTES = str.maketrans({
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u2032": "'",
    "\u2033": '"',
})


@dataclass(frozen=True)
class RuntimeProvider:
    provider_id: str
    engine: str
    endpoint: str
    transport: str
    headers: dict[str, str]
    structured_mode: str
    # "": don't send reasoning params
    # "effort": send as-is (low / medium / high) — for thinking models
    # "on_off": map any non-empty effort to "on", absence to "off" — for Qwen3.5, etc.
    reasoning_effort_style: str = ""
    supports_reasoning_tokens: bool = False


# Session lifecycle helpers.
async def get_session() -> aiohttp.ClientSession:
    """Return the shared aiohttp session used for LLM requests."""

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
    """Close the shared aiohttp session if it is still open."""

    global _session

    session_to_close: Optional[aiohttp.ClientSession] = None
    with _session_lock:
        if _session is not None and not _session.closed:
            session_to_close = _session
        _session = None

    if session_to_close is not None:
        await session_to_close.close()


# Runtime/provider helpers.
def _normalize_engine_name(engine: str | None) -> str:
    normalized = str(engine or "").strip().lower()
    if not normalized:
        return "lms"
    return _ENGINE_ALIASES.get(normalized, normalized)


def _get_runtime_settings_module():
    try:
        from Settings import settings as aslm_settings
    except Exception:
        repo_root = Path(__file__).resolve().parents[4]
        repo_root_str = str(repo_root)
        if repo_root_str not in sys.path:
            sys.path.insert(0, repo_root_str)
        try:
            from Settings import settings as aslm_settings
        except Exception:
            return None
    return aslm_settings


def _runtime_engine() -> str:
    # Temporary override: deep-research is pinned to LM Studio until
    # runtime/provider routing is unified with the main ASLM execution path.
    return "lms"

    explicit_provider = os.getenv("ASLM_LLM_PROVIDER", "").strip()
    if explicit_provider:
        return _normalize_engine_name(explicit_provider)

    aslm_settings = _get_runtime_settings_module()
    if aslm_settings is not None:
        try:
            return _normalize_engine_name(aslm_settings.get_llm_engine())
        except Exception:
            pass

    return _normalize_engine_name(os.getenv("ASLM_LLM_ENGINE", "lms"))


def _ensure_scheme(base_url: str, default_scheme: str = "http") -> str:
    base = str(base_url or "").strip().rstrip("/")
    if not base:
        return ""
    if "://" not in base:
        base = f"{default_scheme}://{base}"
    return base


def _openai_chat_url(base_url: str) -> str:
    base = _ensure_scheme(base_url)
    if not base:
        return ""
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    if base.endswith("/v1/"):
        return f"{base}chat/completions"
    return f"{base}/v1/chat/completions"


def _ollama_chat_url(base_url: str) -> str:
    base = _ensure_scheme(base_url)
    if not base:
        return ""
    if base.endswith("/api/chat"):
        return base
    return f"{base}/api/chat"


def _runtime_openai_base_url() -> str:
    aslm_settings = _get_runtime_settings_module()
    if aslm_settings is not None:
        try:
            return str(aslm_settings.get_engine_url("openai") or "").strip()
        except Exception:
            pass
    return str(os.getenv("ASLM_OPENAI_URL", _OPENAI_COMPAT_DEFAULTS["openai-compatible"])).strip()


def _detect_openai_compatible_provider(base_url: str) -> str:
    host = urlsplit(_ensure_scheme(base_url)).netloc.split(":", 1)[0].lower()
    return _OPENAI_COMPAT_HOSTS.get(host, "openai-compatible")


def _get_openai_compatible_api_key(provider_id: str) -> str:
    aslm_settings = _get_runtime_settings_module()
    if aslm_settings is not None:
        try:
            configured = str(aslm_settings.get_openai_api_key() or "").strip()
            if configured:
                return configured
        except Exception:
            pass

    for env_name in _OPENAI_COMPAT_API_KEY_ENVS.get(provider_id, ("OPENAI_API_KEY",)):
        value = str(os.getenv(env_name, "")).strip()
        if value:
            return value
    return ""


def _resolve_runtime_provider() -> RuntimeProvider:
    engine = _runtime_engine()

    if engine == "claude":
        api_key = (
            str(os.getenv("ASLM_ANTHROPIC_API_KEY", "")).strip()
            or str(os.getenv("ANTHROPIC_API_KEY", "")).strip()
        )
        headers = {
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        if api_key:
            headers["x-api-key"] = api_key
        endpoint = _ensure_scheme(
            os.getenv("ASLM_ANTHROPIC_URL", "https://api.anthropic.com/v1/messages"),
            default_scheme="https",
        )
        return RuntimeProvider(
            provider_id="claude",
            engine=engine,
            endpoint=endpoint,
            transport="anthropic_messages",
            headers=headers,
            structured_mode="tool_schema",
        )

    if engine == "ollama-service":
        port = str(os.getenv("ASLM_OLLAMA_SERVICE_PORT", "30002")).strip()
        endpoint = _ollama_chat_url(f"http://127.0.0.1:{port}")
        return RuntimeProvider(
            provider_id="ollama",
            engine=engine,
            endpoint=endpoint,
            transport="ollama_direct",
            headers={"Content-Type": "application/json"},
            structured_mode="format_schema",
        )

    if engine == "lms":
        # LLM_REASONING_MODE controls which style the currently-loaded model supports:
        # "effort"  — thinking models (Qwen3-235B-A22B, DeepSeek-R1, …): low/medium/high
        # "on_off"  — non-thinking reasoning models (Qwen3.5, …): on/off
        # "none"    — no reasoning params at all
        lms_reasoning_style = str(
            os.getenv("ASLM_LLM_REASONING_MODE", LLM_REASONING_MODE)
        ).strip().lower()
        if lms_reasoning_style == "none":
            lms_reasoning_style = ""
        return RuntimeProvider(
            provider_id="lms",
            engine=engine,
            endpoint=_openai_chat_url(LM_STUDIO_URL),
            transport="openai_compat",
            headers={"Content-Type": "application/json"},
            structured_mode="response_format_json_schema",
            reasoning_effort_style=lms_reasoning_style,
            supports_reasoning_tokens=lms_reasoning_style == "effort",
        )

    if engine in {"gemini", "grok", "openrouter"}:
        base_url = _OPENAI_COMPAT_DEFAULTS[engine]
        api_key = _get_openai_compatible_api_key(engine)
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return RuntimeProvider(
            provider_id=engine,
            engine=engine,
            endpoint=_openai_chat_url(base_url),
            transport="openai_compat",
            headers=headers,
            structured_mode="response_format_json_schema",
            reasoning_effort_style="effort",
        )

    openai_base_url = _runtime_openai_base_url()
    provider_id = _detect_openai_compatible_provider(openai_base_url) if engine == "openai" else "openai-compatible"
    api_key = _get_openai_compatible_api_key(provider_id)
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return RuntimeProvider(
        provider_id=provider_id,
        engine=engine,
        endpoint=_openai_chat_url(openai_base_url),
        transport="openai_compat",
        headers=headers,
        structured_mode="response_format_json_schema",
        reasoning_effort_style="effort",
    )


# Payload builders.
def _build_response_format(
    *,
    schema_name: str,
    json_schema: Optional[dict[str, Any]],
    strict: bool,
) -> dict[str, Any]:
    if json_schema:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "strict": strict,
                "schema": json_schema,
            },
        }
    return {"type": "json_object"}


def _build_messages(prompt: str, system: str) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    return messages


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
    messages = _build_messages(prompt, system)

    if provider.transport == "anthropic_messages":
        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [msg for msg in messages if msg["role"] != "system"],
        }
        if system:
            payload["system"] = system
        if structured_output:
            payload["tools"] = [
                {
                    "name": schema_name,
                    "description": "Structured JSON output",
                    "input_schema": json_schema or {"type": "object", "additionalProperties": True},
                }
            ]
            payload["tool_choice"] = {"type": "tool", "name": schema_name}
        return payload

    if provider.transport == "ollama_direct":
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if structured_output:
            payload["format"] = json_schema or "json"
            # Ollama reasoning models can spend the whole budget in `thinking`
            # and leave `message.content` empty, which breaks schema extraction.
            payload["think"] = False
        return payload

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "frequency_penalty": 0.5,
        "stream": False,
    }
    if structured_output:
        payload["response_format"] = _build_response_format(
            schema_name=schema_name,
            json_schema=json_schema,
            strict=strict,
        )
    if provider.reasoning_effort_style and reasoning_effort:
        if provider.reasoning_effort_style == "on_off":
            payload["reasoning_effort"] = "off" if reasoning_effort in ("off", "none", "") else "on"
        else:  # "effort"
            payload["reasoning_effort"] = reasoning_effort
    if provider.supports_reasoning_tokens and reasoning_tokens and reasoning_tokens > 0:
        payload["reasoning_tokens"] = int(reasoning_tokens)
    return payload


# Response parsing helpers.
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


def _extract_response_text(provider: RuntimeProvider, data: dict[str, Any]) -> str:
    if provider.transport == "anthropic_messages":
        content = data.get("content") or []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                return json.dumps(block.get("input") or {}, ensure_ascii=False)
        return "".join(
            str(block.get("text") or "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )

    if provider.transport == "ollama_direct":
        message = data.get("message") or {}
        return _coerce_response_text(message.get("content"))

    choices = data.get("choices") or []
    if not choices:
        return ""
    message = (choices[0] or {}).get("message") or {}
    return _coerce_response_text(message.get("content"))


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


def _compact_debug_text(text: Any, limit: int = 160) -> str:
    raw = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(raw) <= limit:
        return raw
    return raw[: max(0, limit - 3)] + "..."


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
        lambda match: f'{match.group(1)}"{match.group(2)}"{match.group(3)}',
        candidate,
    )


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
        if isinstance(data, str):
            reparsed = _try_parse_json_candidate(data)
            if reparsed is not None and reparsed is not data:
                return _schema_guided_recover(reparsed, schema)
        return None

    if schema_type == "object":
        if isinstance(data, dict):
            return data
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    return item
        if isinstance(data, str):
            reparsed = _try_parse_json_candidate(data)
            if reparsed is not None and reparsed is not data:
                return _schema_guided_recover(reparsed, schema)
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


def _try_parse_json_candidate(candidate: str) -> Any | None:
    text = _normalize_jsonish_text(candidate)
    if not text:
        return None

    attempts: list[str] = []

    def _push_attempt(value: str) -> None:
        cleaned = value.strip()
        if cleaned and cleaned not in attempts:
            attempts.append(cleaned)

    _push_attempt(text)
    _push_attempt(_strip_json_comments(text))
    _push_attempt(re.sub(r",(\s*[}\]])", r"\1", text))
    _push_attempt(re.sub(r",(\s*[}\]])", r"\1", _strip_json_comments(text)))
    _push_attempt(_repair_unquoted_object_keys(text))
    _push_attempt(_repair_unquoted_object_keys(_strip_json_comments(text)))
    _push_attempt(re.sub(r",(\s*[}\]])", r"\1", _repair_unquoted_object_keys(text)))
    _push_attempt(
        re.sub(
            r",(\s*[}\]])",
            r"\1",
            _repair_unquoted_object_keys(_strip_json_comments(text)),
        )
    )

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


def _balanced_json_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    for opener, closer in (("{", "}"), ("[", "]")):
        for start in [index for index, char in enumerate(text) if char == opener]:
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
                        candidates.append(text[start : index + 1])
                        break
    return candidates


def extract_json(text: str, schema: Optional[dict[str, Any]] = None) -> Optional[object]:
    """Extract and optionally validate JSON from a model response."""

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
        # Track best-effort: right base type but failed count/constraint validation
        # (e.g. model returned 6 queries when schema requires 7 — still usable)
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


# LLM request helpers.
async def call_llm(
    prompt: str,
    model: str,
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
    debug_label: str = "",
    debug_log: Optional[Callable[[str], None]] = None,
) -> Optional[str]:
    """Call the active LLM provider and return response text."""

    provider = _resolve_runtime_provider()
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

    try:
        session = await get_session()
        async with session.post(
            provider.endpoint,
            headers=provider.headers,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as response:
            if response.status != 200:
                if debug_log is not None:
                    try:
                        response_text = await response.text()
                    except Exception:
                        response_text = ""
                    label = f"{debug_label}: " if debug_label else ""
                    preview = _compact_debug_text(response_text)
                    suffix = f" | {preview}" if preview else ""
                    debug_log(
                        f"  [llm-debug] {label}HTTP {response.status} from {provider.engine}{suffix}"
                    )
                return None

            data = await response.json()
            return _extract_response_text(provider, data)
    except RuntimeError as error:
        if "Session is closed" in str(error):
            await close_session()
            try:
                session = await get_session()
                async with session.post(
                    provider.endpoint,
                    headers=provider.headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as response:
                    if response.status != 200:
                        if debug_log is not None:
                            try:
                                response_text = await response.text()
                            except Exception:
                                response_text = ""
                            label = f"{debug_label}: " if debug_label else ""
                            preview = _compact_debug_text(response_text)
                            suffix = f" | {preview}" if preview else ""
                            debug_log(
                                f"  [llm-debug] {label}HTTP {response.status} from {provider.engine} after session reset{suffix}"
                            )
                        return None

                    data = await response.json()
                    return _extract_response_text(provider, data)
            except (aiohttp.ClientError, asyncio.TimeoutError, KeyError, IndexError, RuntimeError) as inner_error:
                if debug_log is not None:
                    label = f"{debug_label}: " if debug_label else ""
                    debug_log(
                        f"  [llm-debug] {label}request failed after session reset ({type(inner_error).__name__}: {inner_error})"
                    )
                return None
        if debug_log is not None:
            label = f"{debug_label}: " if debug_label else ""
            debug_log(f"  [llm-debug] {label}runtime error ({type(error).__name__}: {error})")
        return None
    except (aiohttp.ClientError, asyncio.TimeoutError, KeyError, IndexError) as error:
        if debug_log is not None:
            label = f"{debug_label}: " if debug_label else ""
            debug_log(f"  [llm-debug] {label}request failed ({type(error).__name__}: {error})")
        return None


async def call_llm_json(
    prompt: str,
    model: str,
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
    debug_label: str = "",
    debug_log: Optional[Callable[[str], None]] = None,
) -> Optional[object]:
    """Call the LLM and parse a JSON object from the response text."""

    effective_system = system.strip()
    concise_instruction = str(concise_reasoning_prompt or "").strip()
    if concise_instruction:
        suffix = (
            f"{concise_instruction} "
            "Return only the requested JSON and no extra prose."
        ).strip()
        effective_system = f"{effective_system}\n\n{suffix}".strip() if effective_system else suffix

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
        debug_label=debug_label or schema_name,
        debug_log=debug_log,
    )
    parsed = extract_json(response or "", schema=json_schema)
    if parsed is not None:
        return parsed
    if debug_log is not None:
        label = debug_label or schema_name
        if response:
            preview = _compact_debug_text(response)
            debug_log(
                f"  [llm-debug] {label}: structured attempt returned non-JSON text ({len(str(response))} chars)"
                + (f" | {preview}" if preview else "")
            )
        else:
            debug_log(f"  [llm-debug] {label}: structured attempt returned empty response")

    if structured_output:
        if debug_log is not None:
            label = debug_label or schema_name
            debug_log(f"  [llm-debug] {label}: retrying without provider structured-output mode")
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
            debug_label=debug_label or schema_name,
            debug_log=debug_log,
        )
        parsed = extract_json(fallback_response or "", schema=json_schema)
        if parsed is not None:
            return parsed
        if debug_log is not None:
            label = debug_label or schema_name
            if fallback_response:
                preview = _compact_debug_text(fallback_response)
                debug_log(
                    f"  [llm-debug] {label}: fallback attempt returned non-JSON text ({len(str(fallback_response))} chars)"
                    + (f" | {preview}" if preview else "")
                )
            else:
                debug_log(f"  [llm-debug] {label}: fallback attempt returned empty response")

    return None
