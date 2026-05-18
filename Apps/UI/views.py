# Copyright NGGT.LightKeeper. All Rights Reserved.

from __future__ import annotations

import base64
import binascii
import copy
import hashlib
import ipaddress
import json
import logging
import mimetypes
import os
import re
import socket
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from django.http import FileResponse, HttpResponse, JsonResponse, StreamingHttpResponse
from django.utils import timezone
from django.views.generic import TemplateView

try:
    import requests
except Exception:  # pragma: no cover - optional dependency guard.
    requests = None

try:
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover - optional dependency guard.
    BeautifulSoup = None

from API import llm_api, mcp as tool_registry
from API import ollama as ollama_api
from Apps.Data.ollama_presets import (
    activate_ollama_preset,
    create_ollama_preset,
    delete_ollama_preset,
    get_ollama_preset_payload,
    rename_ollama_preset,
    sync_active_ollama_preset,
)
from Apps.Data.lms_presets import (
    activate_lms_preset,
    create_lms_preset,
    delete_lms_preset,
    get_lms_preset_payload,
    rename_lms_preset,
    sync_active_lms_preset,
)
from Apps.Data.models import (
    Chat,
    LmsPreset,
    Message,
    MessageAttachment,
    MessageAttachmentKind,
    MessageImage,
    OllamaPreset,
)
from Apps.UI.host_theme_bridge import build_host_theme_template_context
from Apps.UI.upload_storage import load_upload_manifest, model_upload_payload, public_upload_payload, save_upload_to_sandbox
from Settings import mcp_json, settings

logger = logging.getLogger(__name__)

TOOLS_PATH = settings.BASE_DIR / "Tools"
if str(TOOLS_PATH) not in sys.path:
    sys.path.insert(0, str(TOOLS_PATH))

from context_compression.history_compressor import (  # noqa: E402
    build_structured_history_summary,
    decide_compression,
    fit_summary_text,
    resolve_context_window_tokens,
)

DEFAULT_SYSTEM_PROMPT_PATH = settings.BASE_DIR / "SYSTEM_PROMPT.md"
_default_system_prompt_lock = threading.RLock()
_default_system_prompt_mtime_ns: int | None = None
_default_system_prompt_cache = ""

THINK_PARAM_NAMES = {"think", "thinking", "reasoning"}
THINK_LEVEL_PARAM_NAMES = {"think_level", "thinking_level", "reasoning_effort"}
TOOL_CAPABILITY_NAMES = {"tools", "tool", "tool-calling", "tool_calling"}
OLLAMA_TOOL_TEMPLATE_MARKERS = (
    ".Tools",
    ".ToolCalls",
    "tool_calls",
    "tool_call_id",
    "<tool_call",
    "[TOOL_CALLS]",
    "available_tools",
    "function_call",
)
TEXT_ATTACHMENT_EXTENSIONS = {
    ".adoc", ".ahk", ".asm", ".asciidoc", ".bash", ".bat", ".bib", ".c", ".cc", ".cfg",
    ".clj", ".cljc", ".cljs", ".cmd", ".cmake", ".conf", ".config", ".cpp", ".cs",
    ".cshtml", ".csproj", ".css", ".csv", ".cts", ".cue", ".cxx", ".dart", ".diff",
    ".dockerfile", ".edn", ".ejs", ".env", ".erb", ".erl", ".ex", ".exs", ".fish",
    ".fs", ".fsi", ".fsx", ".geojson", ".go", ".gql", ".gradle", ".graphql", ".groovy",
    ".gvy", ".h", ".handlebars", ".haml", ".hbs", ".hpp", ".hrl", ".hs", ".htm", ".html",
    ".http", ".hxx", ".ini", ".java", ".jinja", ".jinja2", ".jl", ".js", ".json",
    ".json5", ".jsonc", ".jsonl", ".jsx", ".kt", ".kts", ".ksh", ".latex", ".less",
    ".liquid", ".log", ".lua", ".m", ".mako", ".markdown", ".md", ".mdown", ".mdx",
    ".mjml", ".mkd", ".mm", ".mod", ".mts", ".mustache", ".nix", ".njk", ".patch",
    ".php", ".pl", ".pm", ".pod", ".properties", ".proto", ".ps1", ".ps1xml", ".psd1",
    ".psm1", ".pug", ".py", ".pyi", ".r", ".rb", ".rego", ".rest", ".rst", ".rs",
    ".sass", ".scala", ".scss", ".service", ".sh", ".shtml", ".sol", ".sql", ".srt",
    ".styl", ".svelte", ".sum", ".svg", ".swift", ".tcl", ".templ", ".tex", ".tf",
    ".tfvars", ".toml", ".ts", ".tsv", ".tsx", ".twig", ".txt", ".vb", ".vbs", ".vue",
    ".vtt", ".xhtml", ".xml", ".xsd", ".xsl", ".yaml", ".yml", ".zsh",
}


# Read the project-level system prompt file.
def _read_default_system_prompt() -> str:
    """Return the root SYSTEM_PROMPT.md content, reloading it when changed."""

    global _default_system_prompt_cache, _default_system_prompt_mtime_ns

    try:
        mtime_ns = DEFAULT_SYSTEM_PROMPT_PATH.stat().st_mtime_ns
    except OSError:
        mtime_ns = None

    with _default_system_prompt_lock:
        if mtime_ns == _default_system_prompt_mtime_ns:
            return _default_system_prompt_cache

        prompt = ""
        if mtime_ns is not None:
            try:
                prompt = DEFAULT_SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()
            except OSError:
                logger.exception("Failed to read default system prompt from %s", DEFAULT_SYSTEM_PROMPT_PATH)
                prompt = ""

        _default_system_prompt_mtime_ns = mtime_ns
        _default_system_prompt_cache = prompt
        return prompt


# Build dynamic runtime context injected into every system prompt.
def _build_runtime_context() -> str:
    from datetime import datetime
    now = datetime.now()
    return f"Today is {now.strftime('%A, %Y-%m-%d')}."


def _normalize_favicon_domain(value: str) -> str:
    raw_value = str(value or "").strip()
    if not raw_value:
        return ""

    if not re.match(r"^https?://", raw_value, flags=re.IGNORECASE):
        raw_value = f"https://{raw_value}"

    parsed = urlparse(raw_value)
    host = (parsed.hostname or "").strip().rstrip(".")
    if not host:
        return ""

    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        return ""

    host = host.lower()
    if len(host) > 253 or not re.match(r"^[a-z0-9.-]+$", host):
        return ""
    if host in {"localhost", "localhost.localdomain"}:
        return ""

    return host


def _is_public_favicon_host(host: str) -> bool:
    try:
        addresses = socket.getaddrinfo(host, None)
    except OSError:
        return False

    for address in addresses:
        try:
            ip = ipaddress.ip_address(address[4][0])
        except ValueError:
            return False
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return False

    return bool(addresses)


def _favicon_url_is_safe(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    return _is_public_favicon_host(parsed.hostname)


def _favicon_content_type(response: Any, content: bytes) -> str:
    content_type = str(response.headers.get("content-type", "") or "").split(";")[0].strip().lower()
    if content_type in FAVICON_IMAGE_TYPES:
        return content_type

    probe = content[:256].lstrip()
    if content.startswith(b"\x00\x00\x01\x00"):
        return "image/x-icon"
    if content.startswith(b"\x89PNG"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if probe.startswith(b"<svg") or b"<svg" in probe[:80]:
        return "image/svg+xml"
    if content.startswith(b"RIFF") and b"WEBP" in content[:16]:
        return "image/webp"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"

    return ""


def _favicon_safe_get(session: Any, url: str, *, stream: bool = False) -> Any | None:
    current_url = url
    for _redirect_index in range(5):
        if not _favicon_url_is_safe(current_url):
            return None

        try:
            response = session.get(current_url, timeout=(3, 7), allow_redirects=False, stream=stream)
        except Exception:
            return None

        if response.status_code not in {301, 302, 303, 307, 308}:
            return response

        location = response.headers.get("location", "")
        response.close()
        if not location:
            return None
        current_url = urljoin(current_url, location)

    return None


def _fetch_favicon_candidate(session: Any, url: str) -> tuple[str, bytes] | None:
    response = _favicon_safe_get(session, url, stream=True)
    if response is None:
        return None

    try:
        final_url = str(response.url or url)
        if response.status_code >= 400 or not _favicon_url_is_safe(final_url):
            return None

        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_content(chunk_size=16384):
            if not chunk:
                continue
            total += len(chunk)
            if total > FAVICON_MAX_BYTES:
                return None
            chunks.append(chunk)

        content = b"".join(chunks)
        content_type = _favicon_content_type(response, content)
        if not content_type:
            return None
        return content_type, content
    finally:
        response.close()


def _score_favicon_candidate(candidate: dict[str, str]) -> int:
    rel = candidate.get("rel", "")
    sizes = candidate.get("sizes", "")
    href = candidate.get("href", "")
    score = 0

    if "apple-touch-icon" in rel:
        score += 30
    if rel == "icon" or "shortcut icon" in rel:
        score += 25
    if href.lower().endswith(".svg"):
        score += 20
    if href.lower().endswith(".png"):
        score += 15
    if href.lower().endswith(".ico"):
        score += 5

    match = re.search(r"(\d+)x(\d+)", sizes)
    if match:
        score += min(int(match.group(1)), 256)

    return score


def _collect_favicon_candidates(session: Any, base_url: str) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    final_url = base_url

    if not _favicon_url_is_safe(base_url):
        return candidates

    try:
        response = _favicon_safe_get(session, base_url)
    except Exception:
        response = None

    if response is not None:
        try:
            final_url = str(response.url or base_url)
            if response.status_code < 400 and _favicon_url_is_safe(final_url):
                html = response.text[:400000]
                if BeautifulSoup is not None:
                    soup = BeautifulSoup(html, "html.parser")
                    for tag in soup.find_all("link"):
                        rels = tag.get("rel") or []
                        rel = " ".join(rels).lower() if isinstance(rels, list) else str(rels).lower()
                        if any(icon_rel in rel for icon_rel in FAVICON_ICON_RELS):
                            href = tag.get("href")
                            if href:
                                candidates.append({
                                    "href": urljoin(final_url, href),
                                    "rel": rel,
                                    "sizes": str(tag.get("sizes", "") or ""),
                                })

                    manifest_tag = soup.find("link", rel=lambda value: value and "manifest" in str(value).lower())
                    manifest_href = manifest_tag.get("href") if manifest_tag else ""
                    if manifest_href:
                        manifest_url = urljoin(final_url, manifest_href)
                        if _favicon_url_is_safe(manifest_url):
                            manifest_response = None
                            try:
                                manifest_response = _favicon_safe_get(session, manifest_url)
                                if manifest_response is None or manifest_response.status_code >= 400:
                                    manifest = {}
                                else:
                                    manifest = manifest_response.json()
                            except Exception:
                                manifest = {}
                            finally:
                                if manifest_response is not None:
                                    manifest_response.close()
                            for icon in manifest.get("icons", []) if isinstance(manifest, dict) else []:
                                src = icon.get("src") if isinstance(icon, dict) else ""
                                if src:
                                    candidates.append({
                                        "href": urljoin(manifest_url, src),
                                        "rel": "manifest-icon",
                                        "sizes": str(icon.get("sizes", "") or ""),
                                    })
        finally:
            response.close()

    parsed = urlparse(final_url)
    if parsed.scheme and parsed.netloc:
        origin = f"{parsed.scheme}://{parsed.netloc}"
        for path in FAVICON_ROOT_FALLBACKS:
            candidates.append({"href": urljoin(origin, path), "rel": "root-fallback", "sizes": ""})

    return sorted(candidates, key=_score_favicon_candidate, reverse=True)


def _resolve_favicon_content(domain: str) -> tuple[str, bytes] | None:
    if requests is None:
        return None
    if not domain or not _is_public_favicon_host(domain):
        return None

    base_url = f"https://{domain}/"
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; ASLM-FaviconResolver/1.0)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/*;q=0.8,*/*;q=0.5",
    }

    with requests.Session() as session:
        session.headers.update(headers)
        seen: set[str] = set()
        for candidate in _collect_favicon_candidates(session, base_url):
            href = candidate.get("href", "")
            if not href or href in seen:
                continue
            seen.add(href)

            resolved = _fetch_favicon_candidate(session, href)
            if resolved:
                return resolved

        for fallback_url in (
            f"https://www.google.com/s2/favicons?domain={domain}&sz=128",
            f"https://icons.duckduckgo.com/ip3/{domain}.ico",
        ):
            resolved = _fetch_favicon_candidate(session, fallback_url)
            if resolved:
                return resolved

    return None


def _favicon_cache_paths(domain: str) -> tuple[Path, Path]:
    key = hashlib.sha256(domain.encode("utf-8")).hexdigest()
    return FAVICON_CACHE_DIR / f"{key}.bin", FAVICON_CACHE_DIR / f"{key}.json"


def _read_favicon_disk_cache(domain: str, now: float) -> tuple[str, bytes] | None:
    content_path, meta_path = _favicon_cache_paths(domain)
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if float(meta.get("expires_at", 0) or 0) <= now:
            return None
        content_type = str(meta.get("content_type", "") or "").strip()
        if content_type not in FAVICON_IMAGE_TYPES:
            return None
        content = content_path.read_bytes()
    except Exception:
        return None

    if not content or len(content) > FAVICON_MAX_BYTES:
        return None
    return content_type, content


def _write_favicon_disk_cache(domain: str, content_type: str, content: bytes, expires_at: float) -> None:
    if not content or len(content) > FAVICON_MAX_BYTES:
        return

    try:
        FAVICON_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        content_path, meta_path = _favicon_cache_paths(domain)
        content_path.write_bytes(content)
        meta_path.write_text(
            json.dumps(
                {
                    "domain": domain,
                    "content_type": content_type,
                    "expires_at": expires_at,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        logger.debug("Failed to write favicon disk cache for %s", domain, exc_info=True)


# Merge the project prompt with per-request user instructions.
def _compose_system_prompt(user_system_prompt: str) -> str:
    """Build the system prompt sent to the model for one request."""

    parts: list[str] = []

    default_prompt = _read_default_system_prompt()
    if default_prompt:
        parts.append(default_prompt)

    runtime_context = _build_runtime_context()
    if runtime_context:
        parts.append(runtime_context)

    user_prompt = str(user_system_prompt or "").strip()
    if user_prompt:
        parts.append(f"Additional instructions:\n{user_prompt}")

    return "\n\n".join(parts)
TEXT_ATTACHMENT_FILENAMES = {
    ".bash_profile",
    ".bashrc",
    ".dockerignore",
    ".editorconfig",
    ".env",
    ".env.example",
    ".eslintignore",
    ".eslintrc",
    ".gitattributes",
    ".gitconfig",
    ".gitignore",
    ".gitkeep",
    ".gitmodules",
    ".npmrc",
    ".nvmrc",
    ".prettierignore",
    ".prettierrc",
    ".python-version",
    ".stylelintrc",
    ".tool-versions",
    ".yamllint",
    ".zshenv",
    ".zshrc",
    "brewfile",
    "cmakelists.txt",
    "containerfile",
    "dockerfile",
    "gemfile",
    "jenkinsfile",
    "justfile",
    "makefile",
    "procfile",
    "rakefile",
    "tiltfile",
    "vagrantfile",
}
ATTACHMENT_TEXT_CHAR_LIMIT = 24000
LLM_HISTORY_MAX_MESSAGES = 40
LLM_HISTORY_MIN_MESSAGES = 8
LLM_HISTORY_DEFAULT_CHAR_BUDGET = 48000
LLM_HISTORY_COMPRESSION_TRIGGER_RATIO = 0.80
LLM_HISTORY_COMPRESSION_MAX_CHARS = 90000
LLM_HISTORY_COMPRESSION_MAX_LINES = 120
LLM_HISTORY_COMPRESSION_MAX_ITEMS = 120
LLM_HISTORY_COMPRESSION_RECENT_USER_MESSAGES = 5
LLM_HISTORY_COMPRESSION_DIRECTIVE_MESSAGES = 20
STREAMING_ASSISTANT_SNAPSHOT_INTERVAL_SECONDS = 1.0
STREAMING_ASSISTANT_SNAPSHOT_MIN_CHAR_DELTA = 256
MODEL_INFO_CACHE_TTL_SECONDS = 300
MODEL_LIST_CACHE_TTL_SECONDS = 45
MODEL_RUNTIME_METADATA_PATH = settings.BASE_DIR / "Tools" / "model_runtime_metadata.json"
LLM_CONTROL_TOKEN_PATTERNS = (
    re.compile(
        r"<\|start\|>\s*(?:assistant|user|system)?\s*(?:<\|channel\|>\s*(?:final|analysis|commentary))?\s*(?:<\|message\|>)?",
        flags=re.IGNORECASE,
    ),
    re.compile(r"<\|start\|>", flags=re.IGNORECASE),
    re.compile(r"<\|channel\|>\s*(?:final|analysis|commentary)", flags=re.IGNORECASE),
    re.compile(r"<\|message\|>", flags=re.IGNORECASE),
    re.compile(r"<\|return\|>", flags=re.IGNORECASE),
    re.compile(r"<\|startoftext\|>", flags=re.IGNORECASE),
    re.compile(r"<\|im_(?:start|end)\|>", flags=re.IGNORECASE),
    re.compile(r"<\|(?:assistant|user|system|endoftext)\|>", flags=re.IGNORECASE),
)

_metadata_cache_lock = threading.RLock()
_model_info_cache: dict[tuple[str, str, str, str], tuple[float, dict[str, Any]]] = {}
_model_list_cache: dict[tuple[str, str, str], tuple[float, list[str]]] = {}
_tool_server_cache: dict[tuple[str, str, str, str], tuple[float, list[dict[str, Any]]]] = {}
_active_model_lock = threading.RLock()
_active_model_by_engine: dict[str, str] = {}
_chat_usage_lock = threading.RLock()
_chat_usage_by_chat_id: dict[str, dict[str, Any]] = {}
_favicon_cache_lock = threading.RLock()
_favicon_cache: dict[str, tuple[float, str, bytes]] = {}
_generation_state_lock = threading.RLock()
_active_generation_id_by_engine: dict[str, str] = {}
_active_generation_id_by_chat_id: dict[str, str] = {}
FAVICON_CACHE_DIR = settings.BASE_DIR / "Data" / "favicon_cache"
FAVICON_CACHE_TTL_SECONDS = 7 * 24 * 60 * 60
FAVICON_NEGATIVE_CACHE_TTL_SECONDS = 60 * 60
FAVICON_MAX_BYTES = 384 * 1024
FAVICON_IMAGE_TYPES = {
    "image/x-icon",
    "image/vnd.microsoft.icon",
    "image/png",
    "image/jpeg",
    "image/svg+xml",
    "image/webp",
    "image/gif",
}
FAVICON_ICON_RELS = {
    "icon",
    "shortcut icon",
    "apple-touch-icon",
    "apple-touch-icon-precomposed",
    "mask-icon",
    "fluid-icon",
}
FAVICON_ROOT_FALLBACKS = (
    "/favicon.ico",
    "/favicon.png",
    "/apple-touch-icon.png",
    "/apple-touch-icon-precomposed.png",
)
UPLOADED_FILE_CONTEXT_ENTRY_TYPE = "uploaded_file_context"

CONTEXT_WINDOW_KEYS = (
    "num_ctx",
    "context_length",
    "contextLength",
    "context_window",
    "contextWindow",
    "max_context_length",
    "maxContextLength",
    "max_context_window",
    "maxContextWindow",
    "input_token_limit",
    "inputTokenLimit",
)
OUTPUT_TOKEN_KEYS = (
    "num_predict",
    "maxTokens",
    "max_tokens",
    "max_completion_tokens",
    "max_output_tokens",
    "output_token_limit",
    "outputTokenLimit",
)


# Return a stable runtime scope for model metadata caches.
def _engine_metadata_scope(engine: str) -> tuple[str, str]:
    """Return endpoint and API-key scope for runtime metadata caches."""

    try:
        endpoint = settings.get_engine_url(engine)
    except Exception:
        endpoint = ""

    try:
        api_key = settings.get_engine_api_key(engine)
    except Exception:
        api_key = ""

    api_key_hash = hashlib.sha256(str(api_key or "").encode("utf-8")).hexdigest()[:16]
    return endpoint, api_key_hash


# Return a defensive deep copy of a cacheable payload.
def _clone_metadata_payload(payload: Any) -> Any:
    """Return a detached copy so callers cannot mutate cached metadata."""

    return copy.deepcopy(payload)


# Clear cached model metadata.
def _clear_model_metadata_caches() -> None:
    """Invalidate runtime metadata caches after settings or presets change."""

    with _metadata_cache_lock:
        _model_info_cache.clear()
        _model_list_cache.clear()
        _tool_server_cache.clear()


def _clear_tool_server_cache() -> None:
    """Drop cached tool server lists only (e.g. after ``mcp.json`` changes)."""

    with _metadata_cache_lock:
        _tool_server_cache.clear()


# Remember the latest selected model for one engine.
def _remember_active_model(engine: str, model_name: str) -> None:
    """Store the latest selected model for this server process."""

    normalized_engine = settings.normalize_engine_name(engine)
    normalized_model = str(model_name or "").strip()
    if not normalized_model:
        return

    with _active_model_lock:
        _active_model_by_engine[normalized_engine] = normalized_model


# Read the latest selected model for one engine.
def _get_remembered_active_model(engine: str) -> str:
    """Return the latest selected model for this server process."""

    normalized_engine = settings.normalize_engine_name(engine)
    with _active_model_lock:
        return _active_model_by_engine.get(normalized_engine, "")


# Convert one value into a positive integer when possible.
def _coerce_positive_int(value: Any) -> int | None:
    """Return a positive integer or ``None`` when the value is not numeric."""

    if isinstance(value, bool) or value is None:
        return None

    try:
        number = int(value)
    except (TypeError, ValueError):
        return None

    return number if number > 0 else None


# Read the first positive integer from a mapping.
def _first_positive_int(mapping: dict[str, Any], keys: tuple[str, ...]) -> int | None:
    """Return the first positive integer found under one of the given keys."""

    if not isinstance(mapping, dict):
        return None

    for key in keys:
        number = _coerce_positive_int(mapping.get(key))
        if number is not None:
            return number

    return None


# Resolve the model name represented by an inference-info request.
def _resolve_inference_model(engine: str, requested_model: str | None = None) -> tuple[str, str]:
    """Return the model name and where that selection came from."""

    model_name = str(requested_model or "").strip()
    if model_name:
        return model_name, "request"

    model_name = _get_remembered_active_model(engine)
    if model_name:
        return model_name, "runtime_selection"

    models = _load_models_for_engine(engine)
    if models:
        return models[0], "model_list"

    return "", "none"


# Return cached model info when it is still fresh.
def _get_cached_model_info(engine: str, model_name: str) -> dict[str, Any] | None:
    """Return a cached model-info payload if available."""

    endpoint, api_key_hash = _engine_metadata_scope(engine)
    cache_key = (engine, model_name, endpoint, api_key_hash)
    now = time.monotonic()

    with _metadata_cache_lock:
        cached = _model_info_cache.get(cache_key)
        if cached is None:
            return None
        cached_at, payload = cached
        if now - cached_at > MODEL_INFO_CACHE_TTL_SECONDS:
            _model_info_cache.pop(cache_key, None)
            return None
        return _clone_metadata_payload(payload)


# Store model info in the runtime cache.
def _set_cached_model_info(engine: str, model_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Cache and return a detached model-info payload."""

    endpoint, api_key_hash = _engine_metadata_scope(engine)
    cache_key = (engine, model_name, endpoint, api_key_hash)
    cached_payload = _clone_metadata_payload(payload)

    with _metadata_cache_lock:
        _model_info_cache[cache_key] = (time.monotonic(), cached_payload)

    return _clone_metadata_payload(cached_payload)


# Return cached model names when still fresh.
def _get_cached_model_list(engine: str) -> list[str] | None:
    """Return a cached model list for one engine if available."""

    endpoint, api_key_hash = _engine_metadata_scope(engine)
    cache_key = (engine, endpoint, api_key_hash)
    now = time.monotonic()

    with _metadata_cache_lock:
        cached = _model_list_cache.get(cache_key)
        if cached is None:
            return None
        cached_at, models = cached
        if now - cached_at > MODEL_LIST_CACHE_TTL_SECONDS:
            _model_list_cache.pop(cache_key, None)
            return None
        return list(models)


# Store model names in the runtime cache.
def _set_cached_model_list(engine: str, models: list[str]) -> list[str]:
    """Cache and return a detached model list."""

    endpoint, api_key_hash = _engine_metadata_scope(engine)
    cache_key = (engine, endpoint, api_key_hash)
    cached_models = list(models)

    with _metadata_cache_lock:
        _model_list_cache[cache_key] = (time.monotonic(), cached_models)

    return list(cached_models)


# Return cached tool servers when still fresh.
def _list_tool_servers_cached(engine: str, model_name: str | None = None) -> list[dict[str, Any]]:
    """Return supported tool servers with a short runtime cache."""

    endpoint, api_key_hash = _engine_metadata_scope(engine)
    normalized_model = str(model_name or "")
    cache_key = (engine, normalized_model, endpoint, api_key_hash)
    now = time.monotonic()

    with _metadata_cache_lock:
        cached = _tool_server_cache.get(cache_key)
        if cached is not None:
            cached_at, servers = cached
            if now - cached_at <= MODEL_LIST_CACHE_TTL_SECONDS:
                return _clone_metadata_payload(servers)
            _tool_server_cache.pop(cache_key, None)

    servers = tool_registry.list_servers(engine, model_name)
    with _metadata_cache_lock:
        _tool_server_cache[cache_key] = (time.monotonic(), _clone_metadata_payload(servers))
    return _clone_metadata_payload(servers)


# Emit one concise runtime event for the ASLM console.
def _print_runtime_event(message: str) -> None:
    """Emit one concise runtime event for the ASLM console."""

    print(f"[ASLM-Chat] {message}", flush=True)


# Return whether the exception is an expected runtime/connectivity failure.
def _is_expected_runtime_error(exc: Exception) -> bool:
    """Return whether the exception is an expected runtime/connectivity failure."""

    exc_name = type(exc).__name__
    if exc_name in {"ConnectError", "ConnectionError", "ReadTimeout", "TimeoutException"}:
        return True

    message = str(exc).lower()
    expected_markers = (
        "failed to connect to ollama",
        "connection refused",
        "connection error",
        "connecterror",
        "timed out",
        "timeout",
        "winerror 10061",
    )
    return any(marker in message for marker in expected_markers)


# Return a user-facing runtime error string without noisy transport details.
def _format_runtime_error(engine: str, exc: Exception) -> str:
    """Return a user-facing runtime error string without noisy transport details."""

    message = str(exc).strip()
    normalized_message = message.lower()

    if settings.is_ollama_engine(engine) and _is_expected_runtime_error(exc):
        return (
            "Failed to connect to Ollama. Please check that Ollama is downloaded, "
            "running and accessible. https://ollama.com/download"
        )

    if engine == "openai" and _is_expected_runtime_error(exc):
        return "Failed to connect to the configured OpenAI-compatible endpoint."

    if engine == "google-genai" and _is_expected_runtime_error(exc):
        return "Failed to connect to the configured Google GenAI endpoint."

    if engine == "lms" and _is_expected_runtime_error(exc):
        return "Failed to connect to LM Studio."

    if engine == "google-genai":
        if any(marker in normalized_message for marker in ("api key", "permission denied", "unauthenticated", "unauthorized")):
            return "Google GenAI authentication failed. Check the configured API key."

    if engine == "lms":
        if "v cache quantization requires flash attention" in normalized_message:
            return (
                "The current LM Studio load settings are incompatible. "
                "Enable Flash Attention or set V Cache Quantization Type to f16."
            )
        if "model get/load error" in normalized_message or "failed to load model" in normalized_message:
            return "LM Studio could not load the selected model with the current load settings."

    return message


# Remove assistant-control tokens that should never be shown to the user.
def _strip_llm_control_tokens(content: str) -> str:
    """Remove assistant-control tokens that should never be shown to the user."""

    cleaned = str(content or "")
    for pattern in LLM_CONTROL_TOKEN_PATTERNS:
        cleaned = pattern.sub("", cleaned)
    return cleaned


# Return a short, readable summary of option keys.
def _summarize_option_keys(options: dict[str, Any] | None, max_keys: int = 6) -> str:
    """Return a short, readable summary of option keys."""

    if not isinstance(options, dict) or not options:
        return "none"

    option_keys = sorted({str(key).strip() for key in options if str(key).strip()}, key=str.casefold)
    if len(option_keys) <= max_keys:
        return ", ".join(option_keys)
    return f"{', '.join(option_keys[:max_keys])}, +{len(option_keys) - max_keys} more"


# Count image attachments present in the current outbound request.
def _count_request_images(messages: list[dict[str, Any]]) -> int:
    """Count image attachments present in the current outbound request."""

    image_count = 0
    for message in messages:
        if not isinstance(message, dict):
            continue
        raw_images = message.get("images")
        if isinstance(raw_images, list):
            image_count += len(raw_images)
    return image_count


# Return decoded bytes for one base64 payload or data URL.
def _decode_base64_payload(raw_value: Any) -> bytes:
    """Return decoded bytes for one base64 payload or data URL."""

    if raw_value is None:
        return b""

    payload = str(raw_value).strip()
    if not payload:
        return b""

    if payload.startswith("data:") and "," in payload:
        payload = payload.split(",", 1)[1]

    try:
        return base64.b64decode(payload, validate=True)
    except (ValueError, binascii.Error):
        return base64.b64decode(payload)


# Estimate decoded byte size without materializing the full payload.
def _estimate_base64_payload_size(raw_value: Any) -> int:
    """Return the decoded byte size for one base64 payload or data URL."""

    payload = str(raw_value or "").strip()
    if not payload:
        return 0

    if payload.startswith("data:") and "," in payload:
        payload = payload.split(",", 1)[1]

    payload = "".join(payload.split())
    if not payload:
        return 0

    padding = len(payload) - len(payload.rstrip("="))
    return max((len(payload) * 3) // 4 - padding, 0)


# Return whether one payload is structurally valid base64.
def _is_valid_base64_payload(raw_value: Any) -> bool:
    """Return whether one base64 payload has a valid lightweight shape."""

    payload = str(raw_value or "").strip()
    if not payload:
        return False

    if payload.startswith("data:") and "," in payload:
        payload = payload.split(",", 1)[1]

    payload = "".join(payload.split())
    if not payload or len(payload) % 4 == 1:
        return False

    return re.fullmatch(r"[A-Za-z0-9+/]*={0,2}", payload) is not None


# Split a data URL into MIME type and base64 payload.
def _parse_data_url(raw_value: Any) -> tuple[str, str]:
    """Split a data URL into MIME type and base64 payload."""

    payload = str(raw_value or "").strip()
    if not payload.startswith("data:") or "," not in payload:
        return "", payload

    header, encoded = payload.split(",", 1)
    mime_type = "application/octet-stream"
    if ";" in header:
        mime_type = header[5:].split(";", 1)[0].strip() or mime_type
    return mime_type, encoded


# Return the normalized attachment kind for the payload.
def _guess_attachment_kind(mime_type: str, name: str = "") -> str:
    """Return the normalized attachment kind for the payload."""

    normalized_mime = str(mime_type or "").strip().lower()
    if normalized_mime.startswith("image/"):
        return MessageAttachmentKind.IMAGE

    guessed_mime, _encoding = mimetypes.guess_type(name or "")
    if guessed_mime and guessed_mime.startswith("image/"):
        return MessageAttachmentKind.IMAGE

    return MessageAttachmentKind.FILE


# Normalize one incoming attachment payload into the storage shape.
def _normalize_attachment_payload(raw_attachment: Any, order: int) -> dict[str, Any] | None:
    """Normalize one incoming attachment payload into the storage shape."""

    if isinstance(raw_attachment, str):
        mime_type = _detect_image_mime(raw_attachment)
        raw_data = raw_attachment
        name = f"image-{order + 1}"
    elif isinstance(raw_attachment, dict):
        name = str(
            raw_attachment.get("name")
            or raw_attachment.get("filename")
            or raw_attachment.get("title")
            or ""
        ).strip()
        mime_type = str(raw_attachment.get("mime_type") or raw_attachment.get("mimeType") or "").strip()
        raw_data = raw_attachment.get("data")
        if raw_data is None:
            raw_data = raw_attachment.get("base64")
        data_url = raw_attachment.get("data_url") or raw_attachment.get("dataUrl")
        if data_url:
            parsed_mime, parsed_data = _parse_data_url(data_url)
            if parsed_mime and not mime_type:
                mime_type = parsed_mime
            raw_data = parsed_data
        if not mime_type and name:
            mime_type = mimetypes.guess_type(name)[0] or ""
        if not mime_type:
            mime_type = "application/octet-stream"
    else:
        return None

    encoded = str(raw_data or "").strip()
    if not encoded:
        return None

    if encoded.startswith("data:"):
        parsed_mime, parsed_data = _parse_data_url(encoded)
        if parsed_mime:
            mime_type = parsed_mime
        encoded = parsed_data

    size_bytes = _estimate_base64_payload_size(encoded)
    if size_bytes <= 0 or not _is_valid_base64_payload(encoded):
        return None

    kind = _guess_attachment_kind(mime_type, name)
    if not name:
        extension = mimetypes.guess_extension(mime_type or "") or ""
        base_name = "image" if kind == MessageAttachmentKind.IMAGE else "file"
        name = f"{base_name}-{order + 1}{extension}"

    return {
        "kind": kind,
        "name": name,
        "mime_type": mime_type,
        "data": encoded,
        "size_bytes": size_bytes,
        "order": order,
    }


# Return a normalized list of request attachments.
def _normalize_request_attachments(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Return a normalized list of request attachments."""

    normalized: list[dict[str, Any]] = []
    raw_attachments = data.get("attachments", []) or []
    raw_images = data.get("images", []) or []
    for raw_attachment in list(raw_attachments) + list(raw_images):
        attachment = _normalize_attachment_payload(raw_attachment, len(normalized))
        if attachment is not None:
            normalized.append(attachment)
    return normalized


# Build an attachment content endpoint path.
def _attachment_content_url(record_type: str, record_id: int) -> str:
    """Return the lazy content endpoint for one stored attachment."""

    return f"/api/attachment/{record_type}/{record_id}/content/"


# Convert a persisted attachment-like object into the frontend payload.
def _serialize_attachment_record(attachment: Any, *, include_data: bool = True) -> dict[str, Any]:
    """Convert a persisted attachment-like object into the frontend payload."""

    if isinstance(attachment, MessageAttachment):
        payload = {
            "id": attachment.id,
            "record_type": "attachment",
            "kind": attachment.kind,
            "name": attachment.name,
            "mime_type": attachment.mime_type,
            "size_bytes": attachment.size_bytes,
            "order": attachment.order,
            "content_url": _attachment_content_url("attachment", attachment.id),
        }
        if include_data:
            payload["data_url"] = attachment.data_url()
            payload["extracted_text"] = attachment.extracted_text
            payload["extracted_text_ready"] = attachment.extracted_text_ready
        return payload

    if isinstance(attachment, MessageImage):
        payload = {
            "id": attachment.id,
            "record_type": "image",
            "kind": MessageAttachmentKind.IMAGE,
            "name": f"image-{attachment.order + 1}",
            "mime_type": attachment.mime_type,
            "size_bytes": _estimate_base64_payload_size(attachment.data),
            "order": attachment.order,
            "content_url": _attachment_content_url("image", attachment.id),
        }
        if include_data:
            payload["data_url"] = attachment.data_url()
        return payload

    return {}


# Return all persisted attachments for a message in a shared shape.
def _get_message_attachments(message: Message, *, include_data: bool = True) -> list[dict[str, Any]]:
    """Return all persisted attachments for a message in a shared shape."""

    attachments = [_serialize_attachment_record(item, include_data=include_data) for item in message.attachments.all()]
    legacy_images = [_serialize_attachment_record(item, include_data=include_data) for item in message.images.all()]
    combined = [item for item in attachments + legacy_images if item]
    combined.sort(key=lambda item: (int(item.get("order") or 0), item.get("name", "")))
    return combined


# Decode one serialized attachment payload into bytes.
def _attachment_data_to_bytes(attachment: dict[str, Any]) -> bytes:
    """Decode one serialized attachment payload into bytes."""

    try:
        return _decode_base64_payload(attachment.get("data_url") or attachment.get("data"))
    except (ValueError, binascii.Error):
        return b""


# Return whether the attachment should be decoded as text.
def _is_text_attachment(mime_type: str, name: str) -> bool:
    """Return whether the attachment should be decoded as text."""

    normalized_mime = str(mime_type or "").strip().lower()
    normalized_name = Path(name or "").name.lower()
    attachment_path = Path(name or "")
    if normalized_mime.startswith("text/"):
        return True
    if normalized_mime in {
        "application/ecmascript",
        "application/json",
        "application/ld+json",
        "application/javascript",
        "application/sql",
        "application/toml",
        "application/vnd.api+json",
        "application/xml",
        "application/x-httpd-php",
        "application/x-javascript",
        "application/x-ndjson",
        "application/x-sh",
        "application/x-shellscript",
        "application/x-toml",
        "application/x-yaml",
        "application/yaml",
        "image/svg+xml",
    }:
        return True

    if normalized_name in TEXT_ATTACHMENT_FILENAMES:
        return True

    return any(suffix.lower() in TEXT_ATTACHMENT_EXTENSIONS for suffix in attachment_path.suffixes)


# Trim attachment text so prompts stay bounded.
def _truncate_attachment_text(text: str, limit: int = ATTACHMENT_TEXT_CHAR_LIMIT) -> str:
    """Trim attachment text so prompts stay bounded."""

    normalized = str(text or "").strip()
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit].rstrip()}\n...[truncated]"


# Persist extracted text for one stored file attachment.
def _cache_attachment_text(attachment: dict[str, Any], extracted_text: str) -> str:
    """Store extracted attachment text so future requests do not decode it again."""

    attachment["extracted_text"] = extracted_text
    attachment["extracted_text_ready"] = True

    if attachment.get("record_type") != "attachment":
        return extracted_text

    try:
        attachment_id = int(attachment.get("id") or 0)
    except (TypeError, ValueError):
        attachment_id = 0

    if attachment_id <= 0:
        return extracted_text

    MessageAttachment.objects.filter(id=attachment_id).update(
        extracted_text=extracted_text,
        extracted_text_ready=True,
    )
    return extracted_text


# Extract prompt-friendly text from a file attachment when possible.
def _extract_attachment_text(attachment: dict[str, Any]) -> str:
    """Extract prompt-friendly text from a file attachment when possible."""

    if attachment.get("extracted_text_ready"):
        return _truncate_attachment_text(str(attachment.get("extracted_text") or ""))

    attachment_name = str(attachment.get("name") or "file").strip() or "file"
    mime_type = str(attachment.get("mime_type") or "application/octet-stream").strip()
    file_bytes = _attachment_data_to_bytes(attachment)
    if not file_bytes:
        return _cache_attachment_text(attachment, "")

    suffix = Path(attachment_name).suffix.lower()
    if mime_type == "application/pdf" or suffix == ".pdf":
        try:
            import fitz

            with fitz.open(stream=file_bytes, filetype="pdf") as document:
                pages = [page.get_text("text") for page in document]
            return _cache_attachment_text(attachment, _truncate_attachment_text("\n".join(pages)))
        except Exception:
            return _cache_attachment_text(attachment, "")

    if _is_text_attachment(mime_type, attachment_name):
        for encoding in ("utf-8", "utf-8-sig", "cp1251", "latin-1"):
            try:
                return _cache_attachment_text(attachment, _truncate_attachment_text(file_bytes.decode(encoding)))
            except UnicodeDecodeError:
                continue

    return _cache_attachment_text(attachment, "")


# Serialize one non-image attachment into universal text context.
def _build_file_attachment_prompt_block(attachment: dict[str, Any]) -> str:
    """Serialize one non-image attachment into universal text context."""

    attachment_name = str(attachment.get("name") or "file").strip() or "file"
    mime_type = str(attachment.get("mime_type") or "application/octet-stream").strip()
    size_bytes = int(attachment.get("size_bytes") or 0)
    extracted_text = _extract_attachment_text(attachment)

    if extracted_text:
        return (
            f"[Attached file: {attachment_name}]\n"
            f"MIME: {mime_type}\n"
            f"Size: {size_bytes} bytes\n"
            f"Content:\n{extracted_text}\n"
            f"[/Attached file]"
        )

    return (
        f"[Attached file: {attachment_name}]\n"
        f"MIME: {mime_type}\n"
        f"Size: {size_bytes} bytes\n"
        "Content could not be extracted automatically.\n"
        "[/Attached file]"
    )


def _selected_tools_include_sandbox(selected_tool_servers: list[dict[str, Any]]) -> bool:
    """Return whether the resolved tool selection includes sandbox access."""

    return any(str(server.get("id") or "").strip() == "sandbox" for server in selected_tool_servers)


def _normalize_uploaded_file_ids(data: dict[str, Any]) -> list[str]:
    """Return uploaded file ids referenced by a chat request."""

    raw_values: list[Any] = []
    for key in ("uploaded_file_ids", "uploaded_files", "file_ids"):
        value = data.get(key)
        if isinstance(value, list):
            raw_values.extend(value)
        elif value:
            raw_values.append(value)

    for attachment in data.get("attachments", []) or []:
        if isinstance(attachment, dict):
            file_id = attachment.get("file_id")
            if file_id:
                raw_values.append(file_id)

    seen: set[str] = set()
    normalized: list[str] = []
    for raw_value in raw_values:
        if isinstance(raw_value, dict):
            raw_value = raw_value.get("file_id") or raw_value.get("id")
        file_id = str(raw_value or "").strip()
        if file_id and file_id not in seen:
            seen.add(file_id)
            normalized.append(file_id)
    return normalized


def _load_model_upload_manifests(file_ids: list[str], *, sandbox_enabled: bool) -> list[dict[str, Any]]:
    """Load model-facing upload manifests for the selected tool state."""

    manifests: list[dict[str, Any]] = []
    for file_id in file_ids:
        manifest = load_upload_manifest(file_id)
        if manifest:
            manifests.append(model_upload_payload(manifest, sandbox_enabled=sandbox_enabled))
    return manifests


def _upload_manifest_file_ids(manifests: list[dict[str, Any]]) -> list[str]:
    """Return stable file ids from loaded upload manifests."""

    seen: set[str] = set()
    file_ids: list[str] = []
    for manifest in manifests or []:
        file_id = str((manifest or {}).get("file_id") or "").strip()
        if file_id and file_id not in seen:
            seen.add(file_id)
            file_ids.append(file_id)
    return file_ids


def _build_uploaded_file_context_entry(file_ids: list[str]) -> dict[str, Any] | None:
    """Build a stored user-message entry that keeps upload context replayable."""

    normalized_ids = []
    seen: set[str] = set()
    for file_id in file_ids or []:
        clean_id = str(file_id or "").strip()
        if clean_id and clean_id not in seen:
            seen.add(clean_id)
            normalized_ids.append(clean_id)
    if not normalized_ids:
        return None
    return {
        "type": UPLOADED_FILE_CONTEXT_ENTRY_TYPE,
        "uploaded_file_ids": normalized_ids,
    }


def _extract_uploaded_file_ids_from_message(message: Message) -> list[str]:
    """Return upload ids persisted on a user message."""

    raw_entries = getattr(message, "llm_transcript", None)
    if not isinstance(raw_entries, list):
        return []

    seen: set[str] = set()
    file_ids: list[str] = []
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict):
            continue
        entry_type = str(raw_entry.get("type") or raw_entry.get("kind") or "").strip()
        if entry_type != UPLOADED_FILE_CONTEXT_ENTRY_TYPE:
            continue

        raw_values: list[Any] = []
        for key in ("uploaded_file_ids", "uploaded_files", "file_ids"):
            value = raw_entry.get(key)
            if isinstance(value, list):
                raw_values.extend(value)
            elif value:
                raw_values.append(value)

        for raw_value in raw_values:
            if isinstance(raw_value, dict):
                raw_value = raw_value.get("file_id") or raw_value.get("id")
            file_id = str(raw_value or "").strip()
            if file_id and file_id not in seen:
                seen.add(file_id)
                file_ids.append(file_id)
    return file_ids


def _load_message_upload_manifests(message: Message, *, sandbox_enabled: bool) -> list[dict[str, Any]]:
    """Load persisted upload manifests for one stored user message."""

    return _load_model_upload_manifests(
        _extract_uploaded_file_ids_from_message(message),
        sandbox_enabled=sandbox_enabled,
    )


def _build_uploaded_file_prompt_block(manifest: dict[str, Any]) -> str:
    """Serialize one uploaded file manifest into private model context."""

    name = str(manifest.get("name") or "file").strip() or "file"
    mime = str(manifest.get("mime") or "application/octet-stream").strip()
    size_bytes = int(manifest.get("size_bytes") or 0)
    lines = [
        f"[Uploaded file: {name}]",
        f"File ID: {manifest.get('file_id') or ''}",
        f"MIME: {mime}",
        f"Size: {size_bytes} bytes",
    ]

    sandbox_path = manifest.get("sandbox_path")
    if sandbox_path:
        lines.append(f"Sandbox path: {sandbox_path}")

    archive_tree = manifest.get("archive_tree")
    if isinstance(archive_tree, list) and archive_tree:
        lines.append(
            "Archive preview (file names read from the compressed archive; "
            "the archive has not been extracted):"
        )
        lines.extend(f"- {item}" for item in archive_tree[:250])

    table_preview = str(manifest.get("table_preview") or "").strip()
    if table_preview:
        lines.append(f"Table preview:\n{table_preview}")

    text_preview = str(manifest.get("text_preview") or "").strip()
    if text_preview:
        lines.append(f"Text preview:\n{text_preview}")
    elif not sandbox_path:
        lines.append("Readable content is not available for this model request.")

    lines.append("[/Uploaded file]")
    return "\n".join(lines)


def _apply_uploaded_file_manifests_to_llm_entry(
    entry: dict[str, Any],
    manifests: list[dict[str, Any]],
) -> dict[str, Any]:
    """Attach uploaded file manifests to the current user entry."""

    blocks = [_build_uploaded_file_prompt_block(manifest) for manifest in manifests if manifest]
    if not blocks:
        return entry

    content = str(entry.get("content") or "").strip()
    upload_context = "\n\n".join(blocks)
    entry["content"] = f"{content}\n\n{upload_context}".strip() if content else upload_context
    return entry


# Attach images and file context to one outbound LLM message.
def _apply_attachments_to_llm_entry(entry: dict[str, Any], attachments: list[dict[str, Any]]) -> dict[str, Any]:
    """Attach images and file context to one outbound LLM message."""

    image_payloads = []
    image_mime_types = []
    file_blocks = []

    for attachment in attachments:
        if attachment.get("kind") == MessageAttachmentKind.IMAGE:
            raw_payload = str(attachment.get("data_url") or attachment.get("data") or "")
            mime_type, encoded = _parse_data_url(raw_payload)
            image_payloads.append(encoded or raw_payload)
            image_mime_types.append(str(attachment.get("mime_type") or mime_type or "image/jpeg"))
        else:
            file_blocks.append(_build_file_attachment_prompt_block(attachment))

    if image_payloads:
        entry["images"] = image_payloads
        entry["image_mime_types"] = image_mime_types

    if file_blocks:
        content = str(entry.get("content") or "").strip()
        blocks = "\n\n".join(block for block in file_blocks if block)
        entry["content"] = f"{content}\n\n{blocks}".strip() if content else blocks

    return entry


# Read local GPU devices
def _get_local_gpu_devices() -> list[dict[str, Any]]:
    """Return local NVIDIA GPU devices with both numeric ids and labels."""

    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []

    if result.returncode != 0:
        return []

    devices: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        parts = [part.strip() for part in line.split(",", 1)]
        if len(parts) != 2 or not parts[0]:
            continue
        try:
            device_id = int(parts[0])
        except ValueError:
            continue
        devices.append({"id": device_id, "name": parts[1] or f"GPU {device_id}"})

    return devices


# Resolve active engine
def _get_active_engine(requested_engine: str | None = None) -> str:
    """Return the canonical engine identifier used for the current request."""

    return settings.normalize_engine_name(requested_engine or settings.get_llm_engine())


# Extract model name
def _extract_model_name(model_entry: Any) -> str:
    """Extract a model name from adapter-specific list responses."""

    if isinstance(model_entry, str):
        return model_entry
    if isinstance(model_entry, dict):
        for key in ("model", "id", "model_key", "identifier", "name"):
            value = model_entry.get(key)
            if value:
                return str(value)
        return ""
    for attr in ("model", "id", "model_key", "identifier", "name"):
        value = getattr(model_entry, attr, None)
        if value:
            return str(value)
    return ""


# Load engine models
def _load_models_for_engine(engine: str) -> list[str]:
    """Return sorted model names for the selected engine."""

    cached_models = _get_cached_model_list(engine)
    if cached_models is not None:
        return cached_models

    try:
        raw_models = llm_api.get_models(engine)
    except NotImplementedError:
        logger.info("Model listing is not implemented for engine %s", engine)
        _print_runtime_event(f"Models not supported for engine={engine}.")
        return []
    except Exception as exc:
        logger.warning("Failed to load models for engine %s: %s", engine, exc)
        _print_runtime_event(f"Model list failed: engine={engine}, error={exc}")
        return []

    model_names = []
    for entry in raw_models or []:
        model_name = _extract_model_name(entry)
        if model_name:
            model_names.append(model_name)

    sorted_model_names = sorted(set(model_names), key=str.casefold)
    if not sorted_model_names and settings.is_ollama_engine(engine):
        return []

    return _set_cached_model_list(engine, sorted_model_names)


# Build shared template context
def _build_base_context() -> dict[str, Any]:
    """Build shared template context used by chat pages."""

    runtime_settings = settings.get_runtime_engine_settings()
    engine = _get_active_engine(runtime_settings.get("llm-engine"))
    base = {
        "llm_engine": engine,
        "models": [],
        "engine_options": settings.get_supported_engines(),
        "runtime_settings": runtime_settings,
        "available_tool_servers": _list_tool_servers_cached(engine=engine),
        "chats": Chat.objects.all(),
    }
    base.update(build_host_theme_template_context())
    return base


# Build runtime settings payload
def _build_runtime_settings_payload() -> dict[str, Any]:
    """Return the settings payload used by the UI settings API."""

    runtime_settings = settings.get_runtime_engine_settings()
    active_engine = _get_active_engine(runtime_settings.get("llm-engine"))
    runtime_settings["llm-engine"] = active_engine
    runtime_settings["active_url"] = runtime_settings["engine_urls"].get(active_engine, "")
    engine_api_keys = runtime_settings.get("engine_api_keys", {})
    runtime_settings["active_has_api_key"] = bool(
        engine_api_keys.get(active_engine, runtime_settings.get("active_has_api_key", False))
    )
    runtime_settings["engine_options"] = settings.get_supported_engines()
    return runtime_settings


# Build chat title
def _build_chat_title(message: str, has_attachments: bool) -> str:
    """Generate a stable title for a new chat thread."""

    if message:
        return message[:30] + ("..." if len(message) > 30 else "")
    if has_attachments:
        return "Attachment chat"
    return "New Chat"


# Detect image MIME type
def _detect_image_mime(base64_data: str) -> str:
    """Guess the MIME type from the leading bytes of a base64 payload."""

    if base64_data.startswith("/9j/"):
        return "image/jpeg"
    if base64_data.startswith("iVBOR"):
        return "image/png"
    if base64_data.startswith("R0lGO"):
        return "image/gif"
    if base64_data.startswith("UklGR"):
        return "image/webp"
    return "image/jpeg"


# Strip legacy markup
def _strip_llm_markup(content: str) -> str:
    """Remove stored think/tool markers from legacy assistant content."""

    source = _strip_llm_control_tokens(str(content or ""))
    source = re.sub(r"<think>.*?</think>", "", source, flags=re.DOTALL)
    source = re.sub(r"<tool_call>.*?</tool_call>", "", source, flags=re.DOTALL)
    return source.strip()


# Normalize transcript entries
def _normalize_transcript_entries(raw_entries: Any) -> list[dict[str, Any]]:
    """Return a safe list of transcript entries stored on assistant messages."""

    if not isinstance(raw_entries, list):
        return []

    entries: list[dict[str, Any]] = []
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict):
            continue
        role = str(raw_entry.get("role", "") or "").strip().lower()
        if not role and (
            raw_entry.get("alias")
            or raw_entry.get("tool_id")
            or raw_entry.get("tool_name")
            or raw_entry.get("tool_display_name")
        ):
            role = "tool"
        if role not in {"assistant", "tool"}:
            continue

        entry: dict[str, Any] = {
            "role": role,
            "content": str(raw_entry.get("content", "") or ""),
        }
        if role == "assistant":
            thinking = str(raw_entry.get("thinking", "") or "")
            if thinking:
                entry["thinking"] = thinking
            google_parts = raw_entry.get("google_parts")
            if isinstance(google_parts, list):
                entry["google_parts"] = google_parts
            tool_calls = raw_entry.get("tool_calls")
            if isinstance(tool_calls, list):
                entry["tool_calls"] = tool_calls
        else:
            for key in ("alias", "name", "tool_name", "tool_call_id", "server_id", "server_name", "tool_id", "tool_display_name"):
                value = raw_entry.get(key)
                if value is not None:
                    entry[key] = value
            arguments = raw_entry.get("arguments")
            if isinstance(arguments, dict):
                entry["arguments"] = arguments
            tool_ui = raw_entry.get("tool_ui")
            if isinstance(tool_ui, dict):
                entry["tool_ui"] = tool_ui
            structured_content = raw_entry.get("structured_content")
            if isinstance(structured_content, dict):
                entry["structured_content"] = structured_content
        entries.append(entry)

    return entries


# Build LLM history entries
def _build_llm_history_entries(message: Message, *, sandbox_enabled: bool = False) -> list[dict[str, Any]]:
    """Convert one stored message into the message list expected by the LLM backend."""

    if message.role != "assistant":
        payload = {"role": message.role, "content": message.content}
        payload = _apply_attachments_to_llm_entry(payload, _get_message_attachments(message))
        payload = _apply_uploaded_file_manifests_to_llm_entry(
            payload,
            _load_message_upload_manifests(message, sandbox_enabled=sandbox_enabled),
        )
        return [payload]

    transcript_entries = _normalize_transcript_entries(message.llm_transcript)
    if transcript_entries:
        llm_entries: list[dict[str, Any]] = []
        for entry in transcript_entries:
            if entry["role"] == "tool" and str(entry.get("alias") or "") == "context_compression_summary":
                summary_content = str(entry.get("content") or "").strip()
                if summary_content:
                    llm_entries.append({"role": "system", "content": summary_content})
                continue
            payload = {
                "role": entry["role"],
                "content": entry.get("content", ""),
            }
            if entry["role"] == "assistant":
                if entry.get("thinking"):
                    payload["thinking"] = entry["thinking"]
                if isinstance(entry.get("google_parts"), list):
                    payload["google_parts"] = entry["google_parts"]
                if isinstance(entry.get("tool_calls"), list):
                    payload["tool_calls"] = entry["tool_calls"]
            else:
                if entry.get("tool_call_id"):
                    payload["tool_call_id"] = entry["tool_call_id"]
                if entry.get("name"):
                    payload["name"] = entry["name"]
                if entry.get("tool_name"):
                    payload["tool_name"] = entry["tool_name"]
            llm_entries.append(payload)
        return llm_entries

    stripped_content = _strip_llm_markup(message.content)
    if not stripped_content:
        return []
    return [{"role": "assistant", "content": stripped_content}]


def _message_has_context_compression_summary(message: Message) -> bool:
    """Return whether one stored assistant message represents a compression marker."""

    if getattr(message, "role", "") != "assistant":
        return False
    for entry in _normalize_transcript_entries(getattr(message, "llm_transcript", None)):
        if entry.get("role") == "tool" and str(entry.get("alias") or "") == "context_compression_summary":
            return bool(str(entry.get("content") or "").strip())
    return False


def _build_context_compression_source_entries(
    history_records: list[Message],
    *,
    sandbox_enabled: bool = False,
) -> list[dict[str, Any]]:
    """Build chronological non-compression entries represented by a new boundary."""

    boundary_records: list[Message] = []
    for historical_message in history_records:
        if _message_has_context_compression_summary(historical_message):
            break
        boundary_records.append(historical_message)

    entries: list[dict[str, Any]] = []
    for historical_message in reversed(boundary_records):
        entries.extend(_build_llm_history_entries(historical_message, sandbox_enabled=sandbox_enabled))
    return entries


# Build activity segments
def _build_activity_segments(message: Message) -> list[dict[str, Any]]:
    """Build frontend activity segments from the stored machine transcript."""

    transcript_entries = _normalize_transcript_entries(message.llm_transcript)
    if not transcript_entries:
        return []

    # Index tool results by alias while preserving order. Some runtimes can
    # emit repeated aliases (for example "sandbox__share_file__0" for several
    # different files in one answer), so a simple dict overwrite would keep
    # only the last file after reload.
    tool_results: dict[str, list[dict[str, Any]]] = {}
    for entry in transcript_entries:
        if entry.get("role") == "tool":
            # Prefer the full alias stored by _build_tool_message, fall back to tool_id/name.
            alias = str(entry.get("alias") or entry.get("tool_id") or entry.get("name") or "")
            if alias:
                tool_results.setdefault(alias, []).append({
                    "content": str(entry.get("content") or ""),
                    "toolUi": entry.get("tool_ui") if isinstance(entry.get("tool_ui"), dict) else None,
                    "structuredContent": entry.get("structured_content") if isinstance(entry.get("structured_content"), dict) else None,
                })

    segments: list[dict[str, Any]] = []
    for entry in transcript_entries:
        if entry["role"] == "assistant":
            thinking = str(entry.get("thinking", "") or "").strip()
            content = str(entry.get("content", "") or "").strip()
            if thinking:
                segments.append({"type": "thought", "content": thinking})
            if content:
                segments.append({"type": "text", "content": content})
            continue

        seg_alias = str(entry.get("alias") or entry.get("tool_id", entry.get("name", "")) or "")
        payload_queue = tool_results.get(seg_alias) or []
        if payload_queue:
            result_payload = payload_queue.pop(0)
        else:
            result_payload = {
                "content": str(entry.get("content") or ""),
                "toolUi": entry.get("tool_ui") if isinstance(entry.get("tool_ui"), dict) else None,
                "structuredContent": entry.get("structured_content") if isinstance(entry.get("structured_content"), dict) else None,
            }
        segment = {
            "type": "tool",
            "alias": seg_alias,
            "serverId": str(entry.get("server_id", "") or ""),
            "serverName": str(entry.get("server_name", "") or ""),
            "toolId": str(entry.get("tool_id", entry.get("name", "")) or ""),
            "toolName": str(entry.get("tool_display_name", entry.get("tool_name", entry.get("name", ""))) or ""),
            "arguments": entry.get("arguments") if isinstance(entry.get("arguments"), dict) else {},
            "result": result_payload.get("content") if isinstance(result_payload, dict) else None,
        }
        if isinstance(result_payload, dict):
            if isinstance(result_payload.get("toolUi"), dict):
                segment["toolUi"] = result_payload["toolUi"]
            if isinstance(result_payload.get("structuredContent"), dict):
                segment["structuredContent"] = result_payload["structuredContent"]
        segments.append(segment)

    return segments


def _message_has_reasoning_segments(message: Message) -> bool:
    """Return whether the stored transcript contains model reasoning."""

    return any(
        entry.get("role") == "assistant" and str(entry.get("thinking", "") or "").strip()
        for entry in _normalize_transcript_entries(message.llm_transcript)
    )


# Serialize message
def _serialize_message(message: Message, *, include_attachment_data: bool = True) -> dict[str, Any]:
    """Convert a database message to the JSON shape expected by the frontend."""

    payload = {
        "id": message.id,
        "role": message.role,
        "content": message.content,
        "created_at": message.created_at.isoformat(),
    }
    activity_segments = _build_activity_segments(message)
    if activity_segments:
        payload["activity_segments"] = activity_segments
        payload["reasoning_mode"] = _message_has_reasoning_segments(message)
    attachments = _get_message_attachments(message, include_data=include_attachment_data)
    if message.role == "user":
        for manifest in _load_message_upload_manifests(message, sandbox_enabled=True):
            try:
                uploaded_payload = public_upload_payload(manifest)
            except Exception:
                continue
            if uploaded_payload:
                uploaded_payload["kind"] = "file"
                attachments.append(uploaded_payload)
    if attachments:
        payload["attachments"] = attachments
        payload["images"] = [
            item.get("data_url") or item.get("content_url")
            for item in attachments
            if item.get("kind") == MessageAttachmentKind.IMAGE and (item.get("data_url") or item.get("content_url"))
        ]
    return payload


# Extract streamed message parts
def _extract_stream_message_parts(chunk: Any) -> tuple[str, str]:
    """Return streamed thinking and content text from a backend chunk."""

    raw_message = chunk.get("message", {}) if isinstance(chunk, dict) else getattr(chunk, "message", {})
    if isinstance(raw_message, dict):
        thinking_part = raw_message.get("thinking", "") or ""
        text_part = raw_message.get("content", "") or ""
    else:
        thinking_part = getattr(raw_message, "thinking", "") or ""
        text_part = getattr(raw_message, "content", "") or ""
    return _strip_llm_control_tokens(str(thinking_part)), _strip_llm_control_tokens(str(text_part))


def _copy_transcript_entries_for_storage(transcript_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return transcript entries safe to persist while a response is streaming."""

    entries: list[dict[str, Any]] = []
    for entry in transcript_entries:
        if isinstance(entry, dict):
            entries.append(copy.deepcopy(entry))
    return entries


def _build_streaming_assistant_transcript(
    transcript_entries: list[dict[str, Any]],
    *,
    visible_content: str,
    thinking_content: str,
) -> list[dict[str, Any]]:
    """Overlay streamed assistant text onto machine transcript entries."""

    entries = _copy_transcript_entries_for_storage(transcript_entries)
    has_assistant_content = False
    has_assistant_thinking = False
    for entry in entries:
        if str(entry.get("role") or "").strip().lower() != "assistant":
            continue
        if _strip_llm_control_tokens(str(entry.get("content") or "")).strip():
            has_assistant_content = True
        if _strip_llm_control_tokens(str(entry.get("thinking") or "")).strip():
            has_assistant_thinking = True

    buffered_entry: dict[str, Any] = {"role": "assistant", "content": ""}
    if visible_content and not has_assistant_content:
        buffered_entry["content"] = visible_content
    if thinking_content and not has_assistant_thinking:
        buffered_entry["thinking"] = thinking_content
    if buffered_entry.get("content") or buffered_entry.get("thinking"):
        entries.append(buffered_entry)
    return entries


# Serialize tool marker
def _serialize_tool_call_marker(tool_event: dict[str, Any]) -> str:
    """Encode a tool invocation into an inline marker understood by the frontend."""

    payload = {
        "alias": str(tool_event.get("alias", "") or "").strip(),
        "server_id": str(tool_event.get("server_id", "") or "").strip(),
        "server_name": str(tool_event.get("server_name", "") or "").strip(),
        "tool_id": str(tool_event.get("tool_id", "") or "").strip(),
        "tool_name": str(tool_event.get("tool_name", "") or "").strip(),
        "arguments": tool_event.get("arguments") or {},
    }
    return f'<tool_call>{json.dumps(payload, ensure_ascii=False)}</tool_call>'


# Serialize tool result marker
def _serialize_tool_result_marker(
    alias: str,
    content: str,
    *,
    tool_ui: dict[str, Any] | None = None,
    structured_content: dict[str, Any] | None = None,
) -> str:
    """Encode a tool result into an inline marker so the frontend can show _out_."""

    payload = {"alias": alias, "content": content}
    if isinstance(tool_ui, dict):
        payload["tool_ui"] = tool_ui
    if isinstance(structured_content, dict):
        payload["structured_content"] = structured_content
    return f'<tool_result>{json.dumps(payload, ensure_ascii=False)}</tool_result>'


def _serialize_context_compression_marker(compression_event: dict[str, Any]) -> str:
    """Encode a context-compression boundary without pretending it is a model tool."""

    payload = {
        "alias": str(compression_event.get("alias") or "context_compression_summary").strip(),
        "server_id": str(compression_event.get("server_id") or "system").strip(),
        "server_name": str(compression_event.get("server_name") or "System").strip(),
        "tool_id": str(compression_event.get("tool_id") or "context_compression_summary").strip(),
        "tool_name": str(compression_event.get("tool_display_name") or compression_event.get("tool_name") or "Context Compression").strip(),
        "arguments": compression_event.get("arguments") if isinstance(compression_event.get("arguments"), dict) else {},
        "content": str(compression_event.get("content") or ""),
    }
    tool_ui = compression_event.get("tool_ui")
    if isinstance(tool_ui, dict):
        payload["tool_ui"] = tool_ui
    structured_content = compression_event.get("structured_content")
    if isinstance(structured_content, dict):
        payload["structured_content"] = structured_content
    return f'<context_compression>{json.dumps(payload, ensure_ascii=False)}</context_compression>'


# Extract Ollama model info
def _normalize_capability_tokens(capabilities: Any) -> set[str]:
    """Return normalized capability names from loosely shaped runtime metadata."""

    if capabilities is None:
        return set()

    raw_items: list[Any]
    if isinstance(capabilities, dict):
        raw_items = [key for key, value in capabilities.items() if bool(value)]
    elif isinstance(capabilities, str):
        raw_items = re.split(r"[\s,;|]+", capabilities)
    elif isinstance(capabilities, (list, tuple, set)):
        raw_items = list(capabilities)
    else:
        raw_items = [capabilities]

    tokens: set[str] = set()
    for item in raw_items:
        value = str(item or "").strip().lower()
        if not value:
            continue
        tokens.add(value)
        if "." in value:
            tokens.add(value.rsplit(".", 1)[-1])
    return tokens


# Return whether one Ollama chat template can serialize tools.
def _ollama_template_supports_tool_calling(template: str) -> bool:
    """Return whether an Ollama template contains tool-call placeholders."""

    normalized_template = str(template or "")
    if not normalized_template:
        return False

    folded_template = normalized_template.lower()
    return any(marker.lower() in folded_template for marker in OLLAMA_TOOL_TEMPLATE_MARKERS)


# Return whether Ollama metadata is strong enough to expose local tools.
def _ollama_metadata_supports_tool_calling(
    capabilities: Any,
    template: str,
) -> bool:
    """Return whether Ollama model metadata indicates real tool-call support."""

    if capabilities is not None:
        return bool(_normalize_capability_tokens(capabilities) & TOOL_CAPABILITY_NAMES)

    # Older/custom Ollama responses may not expose `capabilities`. In that
    # case, fall back to whether the model template can serialize tool calls.
    return _ollama_template_supports_tool_calling(template)


def _extract_ollama_model_info(settings_data: Any) -> dict[str, Any]:
    """Parse Ollama-specific model metadata into a frontend-friendly payload."""

    context_length = 8192
    model_layers = 0
    defaults: dict[str, Any] = {}

    # Read raw metadata from dict-like or SDK responses.
    if isinstance(settings_data, dict):
        modelinfo = settings_data.get("modelinfo", settings_data.get("model_info", {})) or {}
        parameters_str = settings_data.get("parameters", "") or ""
        template_str = settings_data.get("template", "") or ""
        capabilities = settings_data.get("capabilities")
    else:
        modelinfo = getattr(settings_data, "modelinfo", {}) or {}
        parameters_str = getattr(settings_data, "parameters", "") or ""
        template_str = getattr(settings_data, "template", "") or ""
        capabilities = getattr(settings_data, "capabilities", None)

    # Extract numeric limits from Ollama's flat metadata keys.
    for key, value in modelinfo.items():
        if key.endswith(".context_length"):
            try:
                context_length = int(value)
            except (TypeError, ValueError):
                pass
        if key.endswith(".block_count"):
            try:
                model_layers = int(value)
            except (TypeError, ValueError):
                pass

    # Parse default runtime parameters from the Modelfile-like payload.
    if parameters_str:
        for line in parameters_str.strip().splitlines():
            parts = line.strip().split()
            if len(parts) < 2:
                continue
            if parts[0].strip().lower() == "parameter":
                if len(parts) < 3:
                    continue
                key = parts[1].strip().lower()
                value = " ".join(parts[2:]).strip()
            else:
                key = parts[0].strip().lower()
                value = " ".join(parts[1:]).strip()
            if not ollama_api.is_supported_runtime_option_key(key):
                continue
            normalized = settings.normalize_setting_value(value)
            if key == "stop":
                existing = defaults.get("stop")
                if isinstance(existing, list):
                    existing.append(normalized)
                else:
                    defaults["stop"] = [normalized]
            else:
                defaults[key] = normalized

    think_param_name = "think"
    think_level_param_name = "think_level"
    normalized_capabilities = _normalize_capability_tokens(capabilities)

    # Detect supported features from the template, defaults, and capabilities.
    supports_thinking = any(
        marker in template_str
        for marker in (".Think ", ".Think\n", ".ThinkLevel", ".Reasoning", ".Reason ")
    )
    supports_think_level = any(
        marker in template_str for marker in (".ThinkLevel", ".ReasoningEffort")
    )

    if "thinking" in normalized_capabilities:
        supports_thinking = True

    for candidate in THINK_PARAM_NAMES:
        if candidate in defaults:
            think_param_name = candidate
            supports_thinking = True
            break

    for candidate in THINK_LEVEL_PARAM_NAMES:
        if candidate in defaults:
            think_level_param_name = candidate
            supports_think_level = True
            break

    supports_vision = "vision" in normalized_capabilities
    supports_tool_calling = _ollama_metadata_supports_tool_calling(capabilities, template_str)

    # Runtime limits are used by the frontend controls.
    cpu_threads = max(int(os.cpu_count() or 1), 1)
    gpu_devices = _get_local_gpu_devices()
    gpu_count = len(gpu_devices)

    return {
        "context_length": context_length,
        "model_layers": model_layers,
        "defaults": defaults,
        "supports_thinking": supports_thinking,
        "supports_think_level": supports_think_level,
        "think_param_name": think_param_name,
        "think_level_param_name": think_level_param_name,
        "supports_vision": supports_vision,
        "supports_tool_calling": supports_tool_calling,
        "supports_files": False,
        "runtime_limits": {
            "cpu_threads": cpu_threads,
            "gpu_count": gpu_count,
            "gpu_devices": gpu_devices,
            "main_gpu_max": max(gpu_count - 1, 0),
            "model_layers": model_layers,
        },
    }


# Extract generic model info
def _extract_generic_model_info(settings_data: Any) -> dict[str, Any]:
    """Build a best-effort model metadata payload for non-Ollama engines."""

    if not isinstance(settings_data, dict):
        return {
            "context_length": 8192,
            "defaults": {},
            "supports_thinking": False,
            "supports_think_toggle": False,
            "supports_think_level": False,
            "think_param_name": "think",
            "think_level_param_name": "think_level",
            "think_level_options": [],
            "supports_vision": False,
            "supports_tool_calling": False,
            "supports_files": False,
            "runtime_limits": {},
            "custom_fields": [],
        }

    capabilities = settings_data.get("capabilities", []) or []
    normalized_capabilities = {str(item).strip().lower() for item in capabilities}
    defaults = settings_data.get("defaults", settings_data.get("parameters", {})) or {}
    if not isinstance(defaults, dict):
        defaults = {}

    context_length = (
        settings_data.get("context_length")
        or settings_data.get("max_context_window")
        or settings_data.get("max_tokens")
        or 8192
    )

    return {
        "context_length": int(context_length),
        "defaults": defaults,
        "supports_thinking": bool(settings_data.get("supports_thinking", False)),
        "supports_think_toggle": bool(settings_data.get("supports_think_toggle", settings_data.get("supports_thinking", False))),
        "supports_think_level": bool(settings_data.get("supports_think_level", False)),
        "think_param_name": settings_data.get("think_param_name", "think"),
        "think_level_param_name": settings_data.get("think_level_param_name", "think_level"),
        "think_level_options": settings_data.get("think_level_options", []) if isinstance(settings_data.get("think_level_options", []), list) else [],
        "supported_parameters": settings_data.get("supported_parameters", []) if isinstance(settings_data.get("supported_parameters", []), list) else [],
        "supports_vision": "vision" in normalized_capabilities or bool(settings_data.get("supports_vision", False)),
        "supports_tool_calling": bool(settings_data.get("supports_tool_calling", False)),
        "supports_files": bool(settings_data.get("supports_files", False)),
        "runtime_limits": settings_data.get("runtime_limits", {}) if isinstance(settings_data.get("runtime_limits", {}), dict) else {},
        "custom_fields": settings_data.get("custom_fields", []) if isinstance(settings_data.get("custom_fields", []), list) else [],
    }


# Build model info payload
def _build_fallback_model_info_payload(engine: str, model_name: str) -> dict[str, Any]:
    """Return a safe payload when runtime metadata cannot be loaded."""

    payload = _extract_generic_model_info({})
    payload["available_tool_servers"] = []
    payload["model"] = model_name
    payload["engine"] = engine
    payload["metadata_fallback"] = True
    return payload


# Load adapter metadata and normalize it for the frontend.
def _build_model_info_payload(
    engine: str,
    model_name: str,
    *,
    allow_fallback: bool = False,
) -> dict[str, Any]:
    """Load adapter metadata and normalize it for the frontend."""

    cached_payload = _get_cached_model_info(engine, model_name)
    if cached_payload is not None:
        _sync_runtime_model_metadata(
            engine,
            model_name,
            cached_payload,
            source="model_info_cache",
            route="/api/model_info/",
        )
        return cached_payload

    try:
        settings_data = llm_api.get_model_settings(engine, model_name)
    except Exception:
        if not allow_fallback:
            raise
        return _build_fallback_model_info_payload(engine, model_name)
    if settings.is_ollama_engine(engine):
        payload = _extract_ollama_model_info(settings_data)
        preset_payload = get_ollama_preset_payload(model_name)
        payload["defaults"] = {**payload.get("defaults", {}), **preset_payload["active_config"]}
        payload["ollama_presets"] = preset_payload
    elif engine == "lms":
        payload = _extract_generic_model_info(settings_data)
        preset_payload = get_lms_preset_payload(model_name)
        active_config = preset_payload.get("active_config", {}) if isinstance(preset_payload, dict) else {}
        if isinstance(active_config, dict):
            payload["defaults"] = {
                **payload.get("defaults", {}),
                **(active_config.get("operation", {}) if isinstance(active_config.get("operation", {}), dict) else {}),
            }
        payload["lms_presets"] = preset_payload
    else:
        payload = _extract_generic_model_info(settings_data)

    payload["available_tool_servers"] = (
        _list_tool_servers_cached(engine, model_name) if payload.get("supports_tool_calling") else []
    )
    payload["model"] = model_name
    payload["engine"] = engine
    cached_payload = _set_cached_model_info(engine, model_name, payload)
    _sync_runtime_model_metadata(
        engine,
        model_name,
        cached_payload,
        source="model_info",
        route="/api/model_info/",
    )
    return cached_payload


# Build a stable engine label for API payloads.
def _get_engine_label(engine: str) -> str:
    """Return a human-readable engine label."""

    return getattr(settings, "ENGINE_LABELS", {}).get(engine, engine)


# Normalize model metadata into a compact runtime-inference payload.
def _build_inference_info_payload(
    engine: str,
    model_name: str,
    model_info_payload: dict[str, Any],
    model_source: str,
) -> dict[str, Any]:
    """Return unified runtime inference metadata independent of engine."""

    defaults = model_info_payload.get("defaults", {})
    if not isinstance(defaults, dict):
        defaults = {}

    runtime_limits = model_info_payload.get("runtime_limits", {})
    if not isinstance(runtime_limits, dict):
        runtime_limits = {}

    model_context_limit = _coerce_positive_int(model_info_payload.get("context_length"))
    current_context_window = _first_positive_int(defaults, CONTEXT_WINDOW_KEYS) or model_context_limit
    current_output_tokens = _first_positive_int(defaults, OUTPUT_TOKEN_KEYS)
    output_token_limit = (
        _first_positive_int(runtime_limits, OUTPUT_TOKEN_KEYS)
        or _coerce_positive_int(model_info_payload.get("output_token_limit"))
    )

    available_tool_servers = model_info_payload.get("available_tool_servers", [])
    if not isinstance(available_tool_servers, list):
        available_tool_servers = []

    capabilities = model_info_payload.get("capabilities", [])
    if not isinstance(capabilities, list):
        capabilities = []

    supported_parameters = model_info_payload.get("supported_parameters", [])
    if not isinstance(supported_parameters, list):
        supported_parameters = []

    return {
        "ok": True,
        "engine": engine,
        "engine_label": _get_engine_label(engine),
        "model": model_name,
        "model_name": model_name,
        "context_window": current_context_window,
        "model_context_limit": model_context_limit,
        "max_output_tokens": current_output_tokens,
        "output_token_limit": output_token_limit,
        "limits": {
            "context_window": current_context_window,
            "model_context_limit": model_context_limit,
            "max_output_tokens": current_output_tokens,
            "output_token_limit": output_token_limit,
        },
        "capabilities": {
            "items": capabilities,
            "supports_thinking": bool(model_info_payload.get("supports_thinking", False)),
            "supports_think_toggle": bool(
                model_info_payload.get("supports_think_toggle", model_info_payload.get("supports_thinking", False))
            ),
            "supports_think_level": bool(model_info_payload.get("supports_think_level", False)),
            "supports_vision": bool(model_info_payload.get("supports_vision", False)),
            "supports_tool_calling": bool(model_info_payload.get("supports_tool_calling", False)),
            "supports_files": bool(model_info_payload.get("supports_files", False)),
        },
        "generation_defaults": defaults,
        "supported_parameters": supported_parameters,
        "runtime_limits": runtime_limits,
        "tool_servers": available_tool_servers,
        "source": {
            "model": model_source,
        },
    }


def _runtime_metadata_source(name: str, route: str, port_setting: str) -> dict[str, Any]:
    """Describe one local metadata source without freezing dynamic ports."""

    return {
        "name": name,
        "type": "local_http_route",
        "route": route,
        "host": "127.0.0.1",
        "port_setting": port_setting,
        "port_sources": [
            "ASLM_Module.json settings[].value/default",
            "Settings/settings.json",
            "environment override when available",
        ],
    }


def _read_runtime_metadata_file() -> dict[str, Any]:
    try:
        with MODEL_RUNTIME_METADATA_PATH.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_runtime_metadata_file(payload: dict[str, Any]) -> None:
    MODEL_RUNTIME_METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = MODEL_RUNTIME_METADATA_PATH.with_suffix(".json.tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(temp_path, MODEL_RUNTIME_METADATA_PATH)


def _sync_runtime_model_metadata(
    engine: str,
    model_name: str,
    model_info_payload: dict[str, Any],
    *,
    source: str,
    route: str,
) -> None:
    """Persist active model metadata for local tools in real time."""

    if not engine or not model_name or not isinstance(model_info_payload, dict):
        return
    if model_info_payload.get("metadata_fallback"):
        return

    defaults = model_info_payload.get("defaults", {})
    if not isinstance(defaults, dict):
        defaults = {}
    runtime_limits = model_info_payload.get("runtime_limits", {})
    if not isinstance(runtime_limits, dict):
        runtime_limits = {}

    model_context_limit = _coerce_positive_int(model_info_payload.get("context_length"))
    context_window = _first_positive_int(defaults, CONTEXT_WINDOW_KEYS) or model_context_limit
    max_output_tokens = _first_positive_int(defaults, OUTPUT_TOKEN_KEYS)
    output_token_limit = (
        _first_positive_int(runtime_limits, OUTPUT_TOKEN_KEYS)
        or _coerce_positive_int(model_info_payload.get("output_token_limit"))
    )

    payload = _read_runtime_metadata_file()
    models = payload.get("models", {})
    if not isinstance(models, dict):
        models = {}

    model_key = f"{engine}:{model_name}"
    existing = models.get(model_key, {})
    runtime = existing.get("runtime", {}) if isinstance(existing, dict) else {}
    if not isinstance(runtime, dict):
        runtime = {}

    sources = [
        {
            **_runtime_metadata_source("ASLM model info", route, "ui-port"),
            "notes": "ASLM-normalized active model metadata written during model selection or generation.",
        }
    ]
    if settings.is_ollama_engine(engine):
        sources.extend(
            [
                {
                    **_runtime_metadata_source("Ollama loaded models", "/api/ps", "ollama-service_port"),
                    "notes": "Provider runtime source for loaded model state and loaded context_length.",
                },
                {
                    **_runtime_metadata_source("Ollama model metadata", "/api/show", "ollama-service_port"),
                    "notes": "Provider model metadata source for capabilities and model limits.",
                },
            ]
        )

    models[model_key] = {
        "engine": engine,
        "model": model_name,
        "capabilities": {
            "vision": bool(model_info_payload.get("supports_vision", False)),
            "tools": bool(model_info_payload.get("supports_tool_calling", False)),
            "thinking": bool(model_info_payload.get("supports_thinking", False)),
            "files": bool(model_info_payload.get("supports_files", False)),
        },
        "limits": {
            "context_window": context_window,
            "model_context_limit": model_context_limit,
            "max_output_tokens": max_output_tokens,
            "output_token_limit": output_token_limit,
        },
        "runtime": runtime,
        "sources": sources,
    }

    payload.update(
        {
            "schema_version": 1,
            "_comment": (
                "Runtime model metadata consumed by local tools. Ports are dynamic; "
                "resolve local_http_route sources through ASLM_Module.json and Settings/settings.json."
            ),
            "updated_at": timezone.now().replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "active": {
                "engine": engine,
                "engine_label": _get_engine_label(engine),
                "model": model_name,
                "source": source,
                "primary_source": {
                    **_runtime_metadata_source("ASLM model info", route, "ui-port"),
                    "fields": [
                        "engine",
                        "model",
                        "supports_vision",
                        "context_length",
                        "defaults",
                    ],
                },
            },
            "models": models,
        }
    )

    try:
        _write_runtime_metadata_file(payload)
    except OSError as exc:
        logger.debug("Failed to write runtime model metadata: %s", exc)


# Read JSON body
def _read_json_request_body(request) -> dict[str, Any]:
    """Parse a JSON request body and return a dictionary."""

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid JSON format") from exc

    if not isinstance(data, dict):
        raise ValueError("JSON body must be an object")
    return data


# Resolve selected tool servers
def _resolve_tool_servers(engine: str, model_name: str, tool_server_ids: list[str]) -> list[dict[str, Any]]:
    """Return the selected tool servers when they are supported by the backend."""

    resolved = []
    for raw_id in tool_server_ids:
        normalized = str(raw_id or "").strip()
        if not normalized:
            continue
        server = tool_registry.get_server(normalized, engine=engine, model_name=model_name)
        if server is None:
            raise ValueError(f"Unknown or unsupported tool server: {normalized}")
        resolved.append(server)
    return resolved


# Raise when tools are requested for a model that should not call tools.
def _validate_tool_server_support(
    engine: str,
    model_name: str,
    tool_server_ids: list[str],
    payload: dict[str, Any] | None = None,
) -> None:
    """Raise when tools are requested for a model that should not call tools."""

    if not tool_server_ids:
        return

    payload = payload or _build_model_info_payload(engine, model_name, allow_fallback=True)
    if payload.get("supports_tool_calling"):
        return

    raise ValueError(f"Model does not support tool calling: {model_name}")

# Parse stored tool slugs
def _parse_active_tool_slugs(slug: str) -> list[str]:
    """Return a list of active tool server ids from the stored slug field."""

    import json as _json
    if not slug:
        return []
    try:
        parsed = _json.loads(slug)
        if isinstance(parsed, list):
            return [str(s) for s in parsed if str(s).strip()]
    except (ValueError, TypeError):
        pass
    # Legacy: single plain string
    return [slug] if slug.strip() else []

# Resolve chat instance
def _resolve_chat(chat_id: str, user_message: str, attachments: list[dict[str, Any]]) -> Chat:
    """Return an existing chat or create a new one for the request."""

    if not chat_id:
        return Chat.objects.create(title=_build_chat_title(user_message, bool(attachments)))

    try:
        return Chat.objects.get(id=chat_id)
    except Chat.DoesNotExist as exc:
        raise LookupError("Chat not found") from exc

# Save message images
def _store_message_attachments(message_record: Message, attachments: list[dict[str, Any]]) -> None:
    """Persist uploaded message attachments for the current user message."""

    for attachment in attachments:
        MessageAttachment.objects.create(
            message=message_record,
            kind=attachment["kind"],
            name=attachment["name"],
            mime_type=attachment["mime_type"],
            data=attachment["data"],
            size_bytes=int(attachment.get("size_bytes") or 0),
            order=int(attachment.get("order") or 0),
        )


# Resolve a bounded history budget from model metadata.
def _resolve_history_char_budget(
    model_info_payload: dict[str, Any] | None,
    *,
    active_engine: str = "",
    active_model: str = "",
    observed_chars_per_token: float | None = None,
) -> int:
    """Return an approximate character budget for replayed chat history."""

    context_length = _context_window_tokens_from_model_info(model_info_payload)
    return _history_char_budget_from_context_window(
        context_length,
        model_info_payload=model_info_payload,
        active_engine=active_engine,
        active_model=active_model,
        observed_chars_per_token=observed_chars_per_token,
        minimum_chars=16000,
        fallback_chars=LLM_HISTORY_DEFAULT_CHAR_BUDGET,
    )


# Estimate the prompt cost of one normalized LLM entry.
def _estimate_llm_entry_chars(entry: dict[str, Any]) -> int:
    """Return a lightweight size estimate for one outbound LLM entry."""

    if not isinstance(entry, dict):
        return 0

    cost = len(str(entry.get("content") or ""))
    cost += len(str(entry.get("thinking") or ""))
    if isinstance(entry.get("tool_calls"), list):
        cost += len(json.dumps(entry["tool_calls"], ensure_ascii=False))
    if isinstance(entry.get("google_parts"), list):
        cost += len(json.dumps(entry["google_parts"], ensure_ascii=False))

    images = entry.get("images") if isinstance(entry.get("images"), list) else []
    cost += len(images) * 4096
    return cost


def _estimate_tokens_from_chars(char_count: int) -> int:
    """Approximate token count from UTF-8 character count."""

    try:
        chars = max(0, int(char_count))
    except (TypeError, ValueError):
        chars = 0
    if chars <= 0:
        return 0
    # Backward-compatible fallback for legacy call sites.
    return max(1, int(round(chars / 2.4)))


def _model_chars_per_token_hint(
    *,
    model_info_payload: dict[str, Any] | None,
    active_engine: str,
    active_model: str,
) -> float:
    """Return one base chars/token hint from model family and engine metadata."""

    model_name = str(active_model or (model_info_payload or {}).get("model") or "").strip().lower()
    engine_name = str(active_engine or "").strip().lower()

    # Conservative defaults that are still closer to real behavior than a fixed
    # chars/1.5 estimate. Lower value => more tokens estimated.
    base_ratio = 2.4
    if "qwen" in model_name:
        base_ratio = 2.0
    elif "deepseek" in model_name:
        base_ratio = 2.2
    elif "llama" in model_name or "mistral" in model_name or "mixtral" in model_name:
        base_ratio = 2.7
    elif "gemma" in model_name:
        base_ratio = 2.5
    elif "gpt" in model_name or "o3" in model_name or "o4" in model_name:
        base_ratio = 2.8

    if engine_name in {"google-genai", "google_genai", "gemini"}:
        base_ratio = min(base_ratio + 0.2, 3.0)
    return base_ratio


def _effective_chars_per_token_hint(
    *,
    model_info_payload: dict[str, Any] | None,
    active_engine: str,
    active_model: str,
    observed_chars_per_token: float | None = None,
) -> float:
    """Return the chars/token ratio shared by usage telemetry and compression."""

    base_ratio = _model_chars_per_token_hint(
        model_info_payload=model_info_payload,
        active_engine=active_engine,
        active_model=active_model,
    )
    if isinstance(observed_chars_per_token, (int, float)) and observed_chars_per_token > 0:
        base_ratio = (base_ratio * 0.35) + (float(observed_chars_per_token) * 0.65)
    return float(max(1.4, min(4.0, base_ratio)))


def _history_char_budget_from_context_window(
    context_window_tokens: int,
    *,
    model_info_payload: dict[str, Any] | None,
    active_engine: str,
    active_model: str,
    observed_chars_per_token: float | None = None,
    minimum_chars: int = 16000,
    fallback_chars: int = LLM_HISTORY_DEFAULT_CHAR_BUDGET,
) -> int:
    """Convert a token context window into the same char budget the UI estimates."""

    try:
        tokens = max(0, int(context_window_tokens))
    except (TypeError, ValueError):
        tokens = 0
    if tokens <= 0:
        return fallback_chars

    chars_per_token = _effective_chars_per_token_hint(
        model_info_payload=model_info_payload,
        active_engine=active_engine,
        active_model=active_model,
        observed_chars_per_token=observed_chars_per_token,
    )
    return max(int(minimum_chars), int(tokens * chars_per_token))


def _estimate_tokens_adaptive(
    *,
    char_count: int,
    model_info_payload: dict[str, Any] | None,
    active_engine: str,
    active_model: str,
    observed_chars_per_token: float | None = None,
) -> int:
    """Estimate tokens using model hints + optional observed prompt telemetry."""

    try:
        chars = max(0, int(char_count))
    except (TypeError, ValueError):
        chars = 0
    if chars <= 0:
        return 0

    base_ratio = _effective_chars_per_token_hint(
        model_info_payload=model_info_payload,
        active_engine=active_engine,
        active_model=active_model,
        observed_chars_per_token=observed_chars_per_token,
    )

    # Keep estimator sane and stable across outlier payloads.
    return max(1, int(round(chars / base_ratio)))


def _context_window_tokens_from_model_info(model_info_payload: dict[str, Any] | None) -> int:
    if not isinstance(model_info_payload, dict):
        return 0

    defaults = model_info_payload.get("defaults", {})
    if isinstance(defaults, dict):
        from_defaults = _first_positive_int(defaults, CONTEXT_WINDOW_KEYS)
        if from_defaults:
            return from_defaults

    limits = model_info_payload.get("limits", {})
    if isinstance(limits, dict):
        current_limit = _first_positive_int(limits, ("context_window", "contextWindow", "num_ctx"))
        if current_limit:
            return current_limit

    direct_current = _first_positive_int(
        model_info_payload,
        ("context_window", "contextWindow", "num_ctx", "input_token_limit", "inputTokenLimit"),
    )
    if direct_current:
        return direct_current

    direct_max = _coerce_positive_int(model_info_payload.get("context_length"))
    if direct_max:
        return direct_max
    return 0


def _estimate_context_usage(
    *,
    chat: Chat | None,
    system_prompt: str,
    draft_text: str,
    model_info_payload: dict[str, Any] | None,
    active_engine: str = "",
    active_model: str = "",
) -> dict[str, Any]:
    """Estimate current context usage for UI telemetry."""

    context_window_tokens = resolve_context_window_tokens(
        model_info_payload,
        runtime_metadata_path=MODEL_RUNTIME_METADATA_PATH,
        active_engine=active_engine,
        active_model=active_model,
    )
    if context_window_tokens <= 0:
        context_window_tokens = _context_window_tokens_from_model_info(model_info_payload)
    if context_window_tokens <= 0:
        context_window_tokens = 32768

    used_chars = len(str(system_prompt or ""))
    compressed_context_active = False
    observed_chars_per_token: float | None = None
    if chat is not None:
        history_qs = (
            chat.messages
            .prefetch_related("attachments", "images")
            .order_by("-created_at", "-id")[:LLM_HISTORY_MAX_MESSAGES]
        )
        for historical_message in history_qs:
            entries = _build_llm_history_entries(historical_message)
            used_chars += sum(_estimate_llm_entry_chars(entry) for entry in entries)
            if _message_has_context_compression_summary(historical_message):
                compressed_context_active = True
                break
        with _chat_usage_lock:
            observed = dict(_chat_usage_by_chat_id.get(str(chat.id), {}))
        raw_ratio = observed.get("observed_chars_per_token")
        if isinstance(raw_ratio, (int, float)) and raw_ratio > 0:
            observed_chars_per_token = float(raw_ratio)

    if draft_text:
        used_chars += len(str(draft_text))

    base_chars_per_token = _model_chars_per_token_hint(
        model_info_payload=model_info_payload,
        active_engine=active_engine,
        active_model=active_model,
    )
    effective_chars_per_token = _effective_chars_per_token_hint(
        model_info_payload=model_info_payload,
        active_engine=active_engine,
        active_model=active_model,
        observed_chars_per_token=observed_chars_per_token,
    )
    estimated_used_tokens = _estimate_tokens_adaptive(
        char_count=used_chars,
        model_info_payload=model_info_payload,
        active_engine=active_engine,
        active_model=active_model,
        observed_chars_per_token=observed_chars_per_token,
    )
    ratio = min(1.0, (estimated_used_tokens / max(1, context_window_tokens)))

    return {
        "context_window_tokens": context_window_tokens,
        "estimated_used_tokens": estimated_used_tokens,
        "estimated_used_chars": used_chars,
        "ratio": ratio,
        "compressed_context_active": compressed_context_active,
        "base_chars_per_token": float(base_chars_per_token),
        "effective_chars_per_token": float(effective_chars_per_token),
        "observed_chars_per_token": float(observed_chars_per_token) if isinstance(observed_chars_per_token, (int, float)) and observed_chars_per_token > 0 else None,
    }


def _build_manual_compression_event(
    *,
    chat: Chat,
    system_prompt: str,
    engine: str,
    model_name: str,
    model_info_payload: dict[str, Any] | None,
    force: bool,
    draft_text: str = "",
    exclude_message_ids: set[int | str] | None = None,
    summarize_with_model_enabled: bool = True,
) -> dict[str, Any] | None:
    """Build one compression event payload for manual/auto UI-triggered compression."""

    observed_chars_per_token: float | None = None
    with _chat_usage_lock:
        observed = dict(_chat_usage_by_chat_id.get(str(chat.id), {}))
    raw_observed_chars_per_token = observed.get("observed_chars_per_token")
    if isinstance(raw_observed_chars_per_token, (int, float)) and raw_observed_chars_per_token > 0:
        observed_chars_per_token = float(raw_observed_chars_per_token)

    history_budget = _resolve_history_char_budget(
        model_info_payload,
        active_engine=engine,
        active_model=model_name,
        observed_chars_per_token=observed_chars_per_token,
    )
    runtime_context_tokens = resolve_context_window_tokens(
        model_info_payload,
        runtime_metadata_path=MODEL_RUNTIME_METADATA_PATH,
        active_engine=engine,
        active_model=model_name,
    )
    if runtime_context_tokens > 0:
        runtime_budget = _history_char_budget_from_context_window(
            runtime_context_tokens,
            model_info_payload=model_info_payload,
            active_engine=engine,
            active_model=model_name,
            observed_chars_per_token=observed_chars_per_token,
            minimum_chars=12000,
            fallback_chars=history_budget,
        )
        history_budget = min(history_budget, runtime_budget)

    used_history_chars = len(str(system_prompt or "")) + len(str(draft_text or ""))
    selected_history: list[list[dict[str, Any]]] = []
    overflow_entries: list[dict[str, Any]] = []
    history_qs = chat.messages.prefetch_related("attachments", "images")
    excluded_ids = {
        str(value)
        for value in (exclude_message_ids or set())
        if value is not None and str(value).strip()
    }
    if excluded_ids:
        history_qs = history_qs.exclude(id__in=excluded_ids)
    history_records = list(history_qs.order_by("-created_at", "-id")[:LLM_HISTORY_MAX_MESSAGES])
    for index, historical_message in enumerate(history_records):
        entries = _build_llm_history_entries(historical_message)
        if not entries:
            continue
        entry_cost = sum(_estimate_llm_entry_chars(entry) for entry in entries)
        if (
            selected_history
            and len(selected_history) >= LLM_HISTORY_MIN_MESSAGES
            and used_history_chars + entry_cost > history_budget
        ):
            overflow_entries.extend(entries)
            for older_message in history_records[index + 1:]:
                if _message_has_context_compression_summary(older_message):
                    overflow_entries.extend(_build_llm_history_entries(older_message))
                    break
                overflow_entries.extend(_build_llm_history_entries(older_message))
            break
        selected_history.append(entries)
        used_history_chars += entry_cost
        if _message_has_context_compression_summary(historical_message):
            break

    if force and not overflow_entries and len(history_records) > 1:
        keep_recent_count = min(LLM_HISTORY_MIN_MESSAGES, max(1, len(history_records) - 1))
        for older_message in history_records[keep_recent_count:]:
            entries = _build_llm_history_entries(older_message)
            if entries:
                overflow_entries.extend(entries)
            if _message_has_context_compression_summary(older_message):
                break

    compression = decide_compression(
        used_history_chars=used_history_chars,
        history_budget_chars=history_budget,
        model_info_payload=model_info_payload,
        runtime_metadata_path=MODEL_RUNTIME_METADATA_PATH,
        active_engine=engine,
        active_model=model_name,
        debug_force_4k=False,
        trigger_ratio=LLM_HISTORY_COMPRESSION_TRIGGER_RATIO,
    )
    if (force or compression.enabled) and not overflow_entries and len(history_records) > 1:
        keep_recent_count = min(LLM_HISTORY_MIN_MESSAGES, max(1, len(history_records) - 1))
        for older_message in history_records[keep_recent_count:]:
            entries = _build_llm_history_entries(older_message)
            if entries:
                overflow_entries.extend(entries)
            if _message_has_context_compression_summary(older_message):
                break

    summary_entries = _build_context_compression_source_entries(history_records)
    if compression.enabled and not overflow_entries and summary_entries:
        overflow_entries = list(summary_entries)
    if force and not overflow_entries:
        overflow_entries = list(summary_entries)
    if force and not summary_entries:
        return None
    should_compress = bool(overflow_entries) and (compression.enabled or force)
    if not should_compress:
        return None

    recent_user_messages = [
        _strip_llm_control_tokens(str(message.content or "")).strip()[:1200]
        for message in chat.messages.filter(role="user").order_by("-created_at", "-id")[:LLM_HISTORY_COMPRESSION_RECENT_USER_MESSAGES]
        if str(message.content or "").strip()
    ]
    direct_user_directives = _collect_direct_user_directives(chat, exclude_message_id=0)
    summarize_with_model_callback = None
    if summarize_with_model_enabled:
        summarize_with_model_callback = lambda prompt_messages: _generate_history_summary_with_model(
            engine=engine,
            model_name=model_name,
            prompt_messages=prompt_messages,
            model_info_payload=model_info_payload,
        )

    try:
        summary_text, summary_payload = build_structured_history_summary(
            overflow_entries=summary_entries,
            recent_user_messages=recent_user_messages,
            direct_user_directives=direct_user_directives,
            summarize_with_model=summarize_with_model_callback,
            max_overflow_entries=LLM_HISTORY_COMPRESSION_MAX_ITEMS,
        )
    except Exception as exc:
        logger.warning("History compression summary failed: %s", exc)
        summary_text, summary_payload = build_structured_history_summary(
            overflow_entries=summary_entries,
            recent_user_messages=recent_user_messages,
            direct_user_directives=direct_user_directives,
            summarize_with_model=None,
            max_overflow_entries=LLM_HISTORY_COMPRESSION_MAX_ITEMS,
        )

    summary_text, summary_payload = fit_summary_text(summary_payload, LLM_HISTORY_COMPRESSION_MAX_CHARS)
    return {
        "role": "tool",
        "alias": "context_compression_summary",
        "name": "context_compression_summary",
        "tool_name": "context_compression_summary",
        "tool_id": "context_compression_summary",
        "tool_display_name": "Context Compression",
        "server_id": "system",
        "server_name": "System",
        "arguments": {
            "reason": compression.reason,
            "history_budget_chars": history_budget,
            "used_history_chars": used_history_chars,
            "context_window_tokens": compression.context_window_tokens,
            "force": bool(force),
        },
        "content": summary_text,
        "tool_ui": {
            "status": "done",
            "label": "Context compressed",
            "kind": "context_compression",
        },
        "structured_content": {
            "kind": "context_compression",
            "summary": summary_payload,
        },
    }


def _collect_recent_user_messages(chat: Chat, exclude_message_id: int) -> list[str]:
    messages = (
        chat.messages
        .filter(role="user")
        .exclude(id=exclude_message_id)
        .order_by("-created_at", "-id")[:LLM_HISTORY_COMPRESSION_RECENT_USER_MESSAGES]
    )
    result: list[str] = []
    for message in messages:
        text = _strip_llm_control_tokens(str(message.content or "")).strip()
        if text:
            result.append(text[:1200])
    return result


def _collect_direct_user_directives(chat: Chat, exclude_message_id: int) -> list[str]:
    return []


def _generate_history_summary_with_model(
    *,
    engine: str,
    model_name: str,
    prompt_messages: list[dict[str, str]],
    model_info_payload: dict[str, Any] | None = None,
) -> str:
    """Generate one non-streamed summary payload with the active model."""

    options = {
        "temperature": 0.0,
        "max_tokens": 8192,
    }
    chunks = llm_api.generate(
        engine=engine,
        model_name=model_name,
        messages=prompt_messages,
        stream=False,
        options=options,
        think=False,
        think_param_name=str((model_info_payload or {}).get("think_param_name", "think") or "think"),
        think_level_param_name=str((model_info_payload or {}).get("think_level_param_name", "reasoning_effort") or "reasoning_effort"),
    )
    parts: list[str] = []
    for chunk in chunks:
        thinking_part, text_part = _extract_stream_message_parts(chunk)
        if text_part:
            parts.append(text_part)
        elif isinstance(chunk, str):
            parts.append(chunk)
    return _strip_llm_control_tokens("".join(parts)).strip()


# Build LLM message history
def _build_chat_history(
    chat: Chat,
    user_message_record: Message,
    user_message: str,
    system_prompt: str,
    engine: str,
    model_name: str,
    model_info_payload: dict[str, Any] | None = None,
    upload_manifests: list[dict[str, Any]] | None = None,
    sandbox_enabled: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Build the message history sent to the selected backend."""

    llm_messages: list[dict[str, Any]] = []
    if system_prompt:
        llm_messages.append({"role": "system", "content": system_prompt})

    observed_chars_per_token: float | None = None
    with _chat_usage_lock:
        observed = dict(_chat_usage_by_chat_id.get(str(chat.id), {}))
    raw_observed_chars_per_token = observed.get("observed_chars_per_token")
    if isinstance(raw_observed_chars_per_token, (int, float)) and raw_observed_chars_per_token > 0:
        observed_chars_per_token = float(raw_observed_chars_per_token)

    history_budget = _resolve_history_char_budget(
        model_info_payload,
        active_engine=engine,
        active_model=model_name,
        observed_chars_per_token=observed_chars_per_token,
    )
    debug_force_4k = str(os.getenv("ASLM_DEBUG_CONTEXT_COMPRESSION_4K", "")).strip().lower() in {"1", "true", "yes", "on"}
    runtime_context_tokens = resolve_context_window_tokens(
        model_info_payload,
        runtime_metadata_path=MODEL_RUNTIME_METADATA_PATH,
        active_engine=engine,
        active_model=model_name,
    )
    if debug_force_4k:
        runtime_context_tokens = 4096
    if runtime_context_tokens > 0:
        runtime_budget = _history_char_budget_from_context_window(
            runtime_context_tokens,
            model_info_payload=model_info_payload,
            active_engine=engine,
            active_model=model_name,
            observed_chars_per_token=observed_chars_per_token,
            minimum_chars=12000,
            fallback_chars=history_budget,
        )
        history_budget = min(history_budget, runtime_budget)
    current_entry: dict[str, Any] = {"role": "user", "content": user_message}
    current_attachments = _get_message_attachments(user_message_record)
    current_entry = _apply_attachments_to_llm_entry(current_entry, current_attachments)
    current_upload_manifests = (
        upload_manifests
        if upload_manifests is not None
        else _load_message_upload_manifests(user_message_record, sandbox_enabled=sandbox_enabled)
    )
    current_entry = _apply_uploaded_file_manifests_to_llm_entry(current_entry, current_upload_manifests or [])

    used_history_chars = len(str(system_prompt or "")) + _estimate_llm_entry_chars(current_entry)
    selected_history: list[list[dict[str, Any]]] = []
    overflow_entries: list[dict[str, Any]] = []
    history_records = list((
        chat.messages
        .exclude(id=user_message_record.id)
        .prefetch_related("attachments", "images")
        .order_by("-created_at", "-id")[:LLM_HISTORY_MAX_MESSAGES]
    ))
    for index, historical_message in enumerate(history_records):
        entries = _build_llm_history_entries(historical_message, sandbox_enabled=sandbox_enabled)
        if not entries:
            continue

        entry_cost = sum(_estimate_llm_entry_chars(entry) for entry in entries)
        if (
            selected_history
            and len(selected_history) >= LLM_HISTORY_MIN_MESSAGES
            and used_history_chars + entry_cost > history_budget
        ):
            # Collect the current and older entries for compression.
            overflow_entries.extend(entries)
            for older_message in history_records[index + 1:]:
                if _message_has_context_compression_summary(older_message):
                    overflow_entries.extend(_build_llm_history_entries(older_message, sandbox_enabled=sandbox_enabled))
                    break
                overflow_entries.extend(_build_llm_history_entries(older_message, sandbox_enabled=sandbox_enabled))
            break

        selected_history.append(entries)
        used_history_chars += entry_cost
        if _message_has_context_compression_summary(historical_message):
            break

    compression = decide_compression(
        used_history_chars=used_history_chars,
        history_budget_chars=history_budget,
        model_info_payload=model_info_payload,
        runtime_metadata_path=MODEL_RUNTIME_METADATA_PATH,
        active_engine=engine,
        active_model=model_name,
        debug_force_4k=debug_force_4k,
        trigger_ratio=LLM_HISTORY_COMPRESSION_TRIGGER_RATIO,
    )
    compression_event: dict[str, Any] | None = None
    summary_entries = _build_context_compression_source_entries(
        history_records,
        sandbox_enabled=sandbox_enabled,
    )
    if overflow_entries and compression.enabled:
        if not summary_entries:
            overflow_entries = []
        else:
            overflow_entries = summary_entries
    if compression.enabled and not overflow_entries and summary_entries:
        overflow_entries = list(summary_entries)
        selected_history = []
    if overflow_entries and compression.enabled:
        recent_user_messages = _collect_recent_user_messages(chat, user_message_record.id)
        direct_user_directives = _collect_direct_user_directives(chat, user_message_record.id)
        try:
            summary_text, _summary_payload = build_structured_history_summary(
                overflow_entries=overflow_entries,
                recent_user_messages=recent_user_messages,
                direct_user_directives=direct_user_directives,
                summarize_with_model=lambda prompt_messages: _generate_history_summary_with_model(
                    engine=engine,
                    model_name=model_name,
                    prompt_messages=prompt_messages,
                    model_info_payload=model_info_payload,
                ),
                max_overflow_entries=LLM_HISTORY_COMPRESSION_MAX_ITEMS,
            )
        except Exception as exc:
            logger.warning("History compression summary failed: %s", exc)
            summary_text, _summary_payload = build_structured_history_summary(
                overflow_entries=overflow_entries,
                recent_user_messages=recent_user_messages,
                direct_user_directives=direct_user_directives,
                summarize_with_model=None,
                max_overflow_entries=LLM_HISTORY_COMPRESSION_MAX_ITEMS,
            )

        if summary_text:
            summary_text, _summary_payload = fit_summary_text(_summary_payload, LLM_HISTORY_COMPRESSION_MAX_CHARS)
            llm_messages.append({"role": "system", "content": summary_text})
            compression_event = {
                "role": "tool",
                "alias": "context_compression_summary",
                "name": "context_compression_summary",
                "tool_name": "context_compression_summary",
                "tool_id": "context_compression_summary",
                "tool_display_name": "Context Compression",
                "server_id": "system",
                "server_name": "System",
                "arguments": {
                    "reason": compression.reason,
                    "history_budget_chars": history_budget,
                    "used_history_chars": used_history_chars,
                    "context_window_tokens": compression.context_window_tokens,
                },
                "content": summary_text,
                "tool_ui": {
                    "status": "done",
                    "label": "Context compressed",
                    "kind": "context_compression",
                },
                "structured_content": {
                    "kind": "context_compression",
                    "summary": _summary_payload,
                },
            }
            logger.info(
                "History compression applied: engine=%s model=%s %s debug_force_4k=%s",
                engine,
                model_name,
                compression.reason,
                debug_force_4k,
            )

    for entries in reversed(selected_history):
        llm_messages.extend(entries)

    llm_messages.append(current_entry)

    return llm_messages, compression_event

# Split generation options
def _split_generation_options(
    options: dict[str, Any],
    think_param_name: str = "think",
    think_level_param_name: str = "think_level",
) -> tuple[Any, Any, dict[str, Any]]:
    """Split thinking controls from generic model options."""

    think_value = None
    think_level_value = None
    clean_options: dict[str, Any] = {}
    think_param_names = set(THINK_PARAM_NAMES)
    think_level_param_names = set(THINK_LEVEL_PARAM_NAMES)
    if think_param_name:
        think_param_names.add(str(think_param_name))
    if think_level_param_name:
        think_level_param_names.add(str(think_level_param_name))

    for key, value in options.items():
        if key in think_param_names:
            think_value = value
        elif key in think_level_param_names:
            think_level_value = value
        else:
            clean_options[key] = value

    return think_value, think_level_value, clean_options

# Build generation kwargs
def _build_generate_kwargs(
    engine: str,
    model_name: str,
    llm_messages: list[dict[str, Any]],
    think_value: Any,
    think_level_value: Any,
    clean_options: dict[str, Any],
    chat: Chat,
    selected_tool_servers: list[dict[str, Any]],
    think_param_name: str = "think",
    think_level_param_name: str = "think_level",
    sync_operation_defaults: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build keyword arguments for ``llm_api.generate``."""

    generate_kwargs: dict[str, Any] = {
        "engine": engine,
        "model_name": model_name,
        "messages": llm_messages,
        "stream": True,
    }

    if think_value is not None:
        generate_kwargs["think"] = think_value
    if think_level_value is not None:
        generate_kwargs["think_level"] = think_level_value
    if engine in {"lms", "openai", "google-genai"} and think_param_name:
        generate_kwargs["think_param_name"] = think_param_name
    if engine in {"lms", "openai", "google-genai"} and think_level_param_name:
        generate_kwargs["think_level_param_name"] = think_level_param_name
    if clean_options:
        generate_kwargs["options"] = clean_options
    if engine == "lms" and isinstance(sync_operation_defaults, dict) and sync_operation_defaults:
        generate_kwargs["sync_operation_defaults"] = sync_operation_defaults

    if selected_tool_servers:
        generate_kwargs["tool_server_ids"] = [s["id"] for s in selected_tool_servers]
        generate_kwargs["tool_context"] = {
            "chat_id": str(chat.id),
            "engine": engine,
            "model_name": model_name,
            "module_dir": str(settings.BASE_DIR),
            "project_dir": str(settings.BASE_DIR),
            "selected_tool_server_ids": [s["id"] for s in selected_tool_servers],
            "sandbox_enabled": _selected_tools_include_sandbox(selected_tool_servers),
        }

    return generate_kwargs

# Stream and save assistant response
def _stream_chat_response(
    chat: Chat,
    engine: str,
    generate_kwargs: dict[str, Any],
    assistant_message_record: Message,
    generation_id: str,
    compression_event: dict[str, Any] | None = None,
    model_info_payload: dict[str, Any] | None = None,
    system_prompt: str = "",
    current_user_message_id: int | str | None = None,
):
    """Stream visible content and persist the machine transcript."""

    visible_parts: list[str] = []
    thinking_parts: list[str] = []
    transcript_entries: list[dict[str, Any]] = []
    usage_snapshot: dict[str, Any] = {}
    is_thinking = False
    failed = False
    restart_after_stream_compression = False
    started_at = time.perf_counter()
    model_name = str(generate_kwargs.get("model_name", "") or "")
    llm_messages = generate_kwargs.get("messages", [])
    prompt_chars_estimate = sum(
        _estimate_llm_entry_chars(entry)
        for entry in llm_messages
        if isinstance(entry, dict)
    ) if isinstance(llm_messages, list) else 0
    image_count = _count_request_images(llm_messages if isinstance(llm_messages, list) else [])
    selected_tool_server_ids = generate_kwargs.get("tool_server_ids", []) or []
    raw_options = generate_kwargs.get("options", {})
    raw_think_value = generate_kwargs.get("think")
    emit_thinking = raw_think_value is not False and str(raw_think_value).strip().lower() not in {"false", "0", "off", "no"}
    last_snapshot_at = 0.0
    last_snapshot_chars = 0
    stream_compression_applied = isinstance(compression_event, dict)

    def current_stream_context_text() -> str:
        """Return current in-flight assistant text for compression estimates."""

        parts = [
            _strip_llm_control_tokens("".join(thinking_parts)).strip(),
            _strip_llm_control_tokens("".join(visible_parts)).strip(),
        ]
        for entry in transcript_entries:
            if not isinstance(entry, dict):
                continue
            role = str(entry.get("role") or "").strip().lower()
            if role == "assistant":
                parts.append(_strip_llm_control_tokens(str(entry.get("thinking") or "")).strip())
                parts.append(_strip_llm_control_tokens(str(entry.get("content") or "")).strip())
            elif role == "tool" and str(entry.get("alias") or "") != "context_compression_summary":
                parts.append(_strip_llm_control_tokens(str(entry.get("content") or "")).strip())
        return "\n".join(part for part in parts if part)

    def persist_stream_snapshot(*, force: bool = False) -> None:
        """Persist the in-flight assistant buffer so reloads/compression see it."""

        nonlocal last_snapshot_at, last_snapshot_chars

        visible_content = _strip_llm_control_tokens("".join(visible_parts)).strip()
        thinking_content = _strip_llm_control_tokens("".join(thinking_parts)).strip()
        transcript_snapshot = _build_streaming_assistant_transcript(
            transcript_entries,
            visible_content=visible_content,
            thinking_content=thinking_content,
        )
        snapshot_chars = len(visible_content) + len(thinking_content) + sum(
            len(str(entry.get("content") or "")) + len(str(entry.get("thinking") or ""))
            for entry in transcript_snapshot
            if isinstance(entry, dict)
        )
        if not snapshot_chars:
            return

        now = time.perf_counter()
        if (
            not force
            and last_snapshot_chars > 0
            and now - last_snapshot_at < STREAMING_ASSISTANT_SNAPSHOT_INTERVAL_SECONDS
            and snapshot_chars - last_snapshot_chars < STREAMING_ASSISTANT_SNAPSHOT_MIN_CHAR_DELTA
        ):
            return

        try:
            assistant_message_record.content = visible_content
            assistant_message_record.llm_transcript = transcript_snapshot
            assistant_message_record.save(update_fields=["content", "llm_transcript"])
            Chat.objects.filter(pk=chat.pk).update(updated_at=timezone.now())
            last_snapshot_at = now
            last_snapshot_chars = snapshot_chars
        except Exception:
            logger.exception("Failed to persist streaming assistant snapshot")

    def maybe_apply_stream_context_compression(trigger: str, extra_context_text: str = "") -> str:
        """Build and persist one automatic compression marker at safe stream points."""

        nonlocal restart_after_stream_compression, stream_compression_applied

        if stream_compression_applied:
            return ""

        draft_text = "\n".join(
            part
            for part in (
                current_stream_context_text(),
                _strip_llm_control_tokens(str(extra_context_text or "")).strip(),
            )
            if part
        )

        excluded_message_ids: set[int | str] = {assistant_message_record.id}
        if current_user_message_id is not None:
            excluded_message_ids.add(current_user_message_id)
        event = _build_manual_compression_event(
            chat=chat,
            system_prompt=system_prompt,
            draft_text=draft_text,
            engine=engine,
            model_name=model_name,
            model_info_payload=model_info_payload,
            force=False,
            exclude_message_ids=excluded_message_ids,
            summarize_with_model_enabled=False,
        )
        if not event:
            return ""

        arguments = event.get("arguments")
        if isinstance(arguments, dict):
            arguments["auto_trigger"] = trigger
            arguments["streaming"] = True
            arguments["restart_generation"] = True
        Message.objects.create(
            chat=chat,
            role="assistant",
            content="",
            llm_transcript=[event],
        )
        stream_compression_applied = True
        try:
            llm_api.abort_generation(engine)
        except Exception:
            logger.exception("Failed to abort generation after streaming compression")
        restart_after_stream_compression = True
        return _serialize_context_compression_marker(event)

    _print_runtime_event(
        "Chat started: "
        f"engine={engine}, "
        f"model={model_name}, "
        f"messages={len(llm_messages) if isinstance(llm_messages, list) else 0}, "
        f"images={image_count}, "
        f"tools={len(selected_tool_server_ids) if isinstance(selected_tool_server_ids, list) else 0}, "
        f"options={_summarize_option_keys(raw_options)}"
    )
    if settings.is_console_trace_enabled():
        _print_runtime_event(
            "Chat trace: "
            f"tool_servers={selected_tool_server_ids if isinstance(selected_tool_server_ids, list) else []}, "
            f"options_payload={json.dumps(raw_options, ensure_ascii=False, sort_keys=True) if isinstance(raw_options, dict) else raw_options}"
        )

    try:
        with _generation_state_lock:
            _active_generation_id_by_engine[str(engine)] = str(generation_id or "")
            _active_generation_id_by_chat_id[str(chat.id)] = str(generation_id or "")
        if isinstance(compression_event, dict):
            transcript_entries.append(compression_event)
            persist_stream_snapshot(force=True)
            yield _serialize_context_compression_marker(compression_event)

        llm_api.prepare_runtime(engine)
        response_iterator = llm_api.generate(**generate_kwargs)
        for chunk in response_iterator:
            # Save assistant/tool transcript entries that are not meant
            # to be rendered directly as plain chat text.
            if isinstance(chunk, dict) and chunk.get("transcript_message"):
                transcript_message = chunk["transcript_message"]
                if isinstance(transcript_message, dict):
                    transcript_thinking = _strip_llm_control_tokens(str(transcript_message.get("thinking") or "")).strip()
                    if not emit_thinking and transcript_message.get("thinking"):
                        transcript_message = {**transcript_message}
                        transcript_message.pop("thinking", None)
                    transcript_entries.append(transcript_message)
                    persist_stream_snapshot()
                    transcript_trigger = ""
                    transcript_trigger_context = transcript_thinking
                    if transcript_thinking:
                        transcript_trigger = "reasoning"
                    elif transcript_message.get("tool_calls"):
                        transcript_trigger = "tool_call"
                        transcript_trigger_context = json.dumps(transcript_message.get("tool_calls"), ensure_ascii=False)
                    if transcript_trigger:
                        compression_marker = maybe_apply_stream_context_compression(
                            transcript_trigger,
                            extra_context_text=transcript_trigger_context,
                        )
                        if compression_marker:
                            yield compression_marker
                            break
                continue

            if isinstance(chunk, dict) and chunk.get("tool_result"):
                tool_message = chunk["tool_result"]
                if isinstance(tool_message, dict):
                    transcript_entries.append(tool_message)
                    persist_stream_snapshot()
                    alias = str(tool_message.get("alias") or tool_message.get("tool_id") or tool_message.get("name") or "")
                    content = str(tool_message.get("content") or "")
                    tool_ui = tool_message.get("tool_ui") if isinstance(tool_message.get("tool_ui"), dict) else None
                    structured_content = (
                        tool_message.get("structured_content")
                        if isinstance(tool_message.get("structured_content"), dict)
                        else None
                    )
                    yield _serialize_tool_result_marker(
                        alias,
                        content,
                        tool_ui=tool_ui,
                        structured_content=structured_content,
                    )
                    compression_marker = maybe_apply_stream_context_compression("tool_result")
                    if compression_marker:
                        yield compression_marker
                        break
                continue

            if isinstance(chunk, dict) and isinstance(chunk.get("tool_events"), list):
                if is_thinking:
                    is_thinking = False
                    yield "\n</think>\n"
                markers = [
                    _serialize_tool_call_marker(tool_event)
                    for tool_event in chunk["tool_events"]
                    if isinstance(tool_event, dict)
                ]
                if markers:
                    yield "".join(markers)
                compression_marker = maybe_apply_stream_context_compression(
                    "tool_call",
                    extra_context_text=json.dumps(chunk["tool_events"], ensure_ascii=False),
                )
                if compression_marker:
                    yield compression_marker
                    break
                continue

            # Tool events are sent as inline markers for the frontend.
            if isinstance(chunk, dict) and chunk.get("tool_event"):
                if is_thinking:
                    is_thinking = False
                    yield "\n</think>\n"
                yield _serialize_tool_call_marker(chunk["tool_event"])
                compression_marker = maybe_apply_stream_context_compression(
                    "tool_call",
                    extra_context_text=json.dumps(chunk["tool_event"], ensure_ascii=False),
                )
                if compression_marker:
                    yield compression_marker
                    break
                continue

            if isinstance(chunk, dict):
                prompt_tokens = _coerce_positive_int(
                    chunk.get("prompt_eval_count")
                    or chunk.get("prompt_tokens")
                    or chunk.get("input_tokens")
                )
                completion_tokens = _coerce_positive_int(
                    chunk.get("eval_count")
                    or chunk.get("completion_tokens")
                    or chunk.get("output_tokens")
                )
                total_tokens = _coerce_positive_int(
                    chunk.get("total_tokens")
                )
                usage = chunk.get("usage")
                if isinstance(usage, dict):
                    prompt_tokens = prompt_tokens or _coerce_positive_int(
                        usage.get("prompt_tokens") or usage.get("input_tokens")
                    )
                    completion_tokens = completion_tokens or _coerce_positive_int(
                        usage.get("completion_tokens") or usage.get("output_tokens")
                    )
                    total_tokens = total_tokens or _coerce_positive_int(usage.get("total_tokens"))
                if prompt_tokens is not None:
                    usage_snapshot["prompt_tokens"] = int(prompt_tokens)
                if completion_tokens is not None:
                    usage_snapshot["completion_tokens"] = int(completion_tokens)
                if total_tokens is not None:
                    usage_snapshot["total_tokens"] = int(total_tokens)

            thinking_part, text_part = _extract_stream_message_parts(chunk)

            # Thinking fragments are wrapped in custom tags.
            if thinking_part:
                if emit_thinking:
                    thinking_parts.append(thinking_part)
                    persist_stream_snapshot()
                    if not is_thinking:
                        is_thinking = True
                        yield "<think>\n"
                    yield thinking_part
                compression_marker = maybe_apply_stream_context_compression(
                    "reasoning",
                    extra_context_text="" if emit_thinking else thinking_part,
                )
                if compression_marker:
                    if is_thinking:
                        is_thinking = False
                        yield "\n</think>\n"
                    yield compression_marker
                    break

            if restart_after_stream_compression:
                break

            # Visible text is streamed and stored separately.
            if text_part:
                if is_thinking:
                    is_thinking = False
                    yield "\n</think>\n"
                visible_parts.append(text_part)
                persist_stream_snapshot()
                yield text_part
    except Exception as exc:
        failed = True
        formatted_error = _format_runtime_error(engine, exc)
        if _is_expected_runtime_error(exc):
            logger.warning("Error during streaming generation: %s", formatted_error)
        else:
            logger.exception("Error during streaming generation")
        if is_thinking:
            yield "\n</think>\n"
        yield f"\n[Error during generation: {formatted_error}]"
    finally:
        with _generation_state_lock:
            active_id = str(_active_generation_id_by_engine.get(str(engine)) or "")
            if active_id == str(generation_id or ""):
                _active_generation_id_by_engine.pop(str(engine), None)
            chat_active_id = str(_active_generation_id_by_chat_id.get(str(chat.id)) or "")
            if chat_active_id == str(generation_id or ""):
                _active_generation_id_by_chat_id.pop(str(chat.id), None)
        if is_thinking:
            yield "\n</think>\n"

        visible_content = _strip_llm_control_tokens("".join(visible_parts)).strip()
        thinking_content = _strip_llm_control_tokens("".join(thinking_parts)).strip()
        transcript_assistant_visible_parts: list[str] = []
        transcript_has_renderable_payload = False
        for entry in transcript_entries:
            if not isinstance(entry, dict):
                continue
            role = str(entry.get("role") or "").lower()
            content = _strip_llm_control_tokens(str(entry.get("content") or "")).strip()
            thinking = _strip_llm_control_tokens(str(entry.get("thinking") or "")).strip()
            if role == "assistant":
                if content:
                    transcript_assistant_visible_parts.append(content)
                    transcript_has_renderable_payload = True
                if thinking:
                    transcript_has_renderable_payload = True
            elif role == "tool":
                alias = str(entry.get("alias") or entry.get("tool_id") or "").strip().lower()
                # Compression markers alone should not become an "empty model reply".
                if alias and alias != "context_compression_summary":
                    transcript_has_renderable_payload = True
                elif content and not alias:
                    transcript_has_renderable_payload = True

        if not visible_content and transcript_assistant_visible_parts:
            visible_content = _strip_llm_control_tokens("".join(transcript_assistant_visible_parts)).strip()

        transcript_entries = _build_streaming_assistant_transcript(
            transcript_entries,
            visible_content=visible_content,
            thinking_content=thinking_content,
        )

        should_persist_message = bool(visible_content or thinking_content or transcript_has_renderable_payload)
        if should_persist_message:
            assistant_message_record.content = visible_content
            assistant_message_record.llm_transcript = transcript_entries
            assistant_message_record.save(update_fields=["content", "llm_transcript"])
            # Bump chat ordering so sidebar reflects the latest activity.
            Chat.objects.filter(pk=chat.pk).update(updated_at=timezone.now())
        else:
            # Nothing was generated; drop the empty placeholder we pre-created.
            assistant_message_record.delete()

        duration_seconds = time.perf_counter() - started_at
        if usage_snapshot:
            prompt_tokens_observed = _coerce_positive_int(usage_snapshot.get("prompt_tokens"))
            if prompt_tokens_observed and prompt_chars_estimate > 0:
                usage_snapshot["prompt_chars_estimate"] = int(prompt_chars_estimate)
                usage_snapshot["observed_chars_per_token"] = float(prompt_chars_estimate / max(1, prompt_tokens_observed))
            with _chat_usage_lock:
                _chat_usage_by_chat_id[str(chat.id)] = {
                    **usage_snapshot,
                    "engine": engine,
                    "model": model_name,
                    "updated_at": timezone.now().isoformat(),
                }
        _print_runtime_event(
            "Chat completed: "
            f"engine={engine}, "
            f"model={model_name}, "
            f"status={'failed' if failed else 'ok'}, "
            f"took={duration_seconds:.2f}s, "
            f"visible_chars={len(visible_content)}, "
            f"transcript_entries={len(transcript_entries)}"
        )


# Chat page views.

# Render the main chat page.
class MainView(TemplateView):
    template_name = "main/main.html"

    # Build the main page context.
    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """Return template context for the main chat page."""

        context = super().get_context_data(**kwargs)
        context.update(_build_base_context())
        return context


# Chat session APIs.

# Store uploaded files and return UI-facing file cards.
def upload_files_api(request):
    """Accept arbitrary user files and store private manifests for model use."""

    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    uploaded_files = request.FILES.getlist("files") or request.FILES.getlist("file")
    if not uploaded_files:
        return JsonResponse({"error": "No files uploaded"}, status=400)

    scope = request.POST.get("chat_id") or request.POST.get("scope") or "pending"
    model_supports_vision = str(request.POST.get("supports_vision", "")).lower() in {"1", "true", "yes"}
    public_files: list[dict[str, Any]] = []
    for uploaded_file in uploaded_files:
        try:
            _manifest, public_payload = save_upload_to_sandbox(
                uploaded_file,
                scope=scope,
                model_supports_vision=model_supports_vision,
            )
            public_files.append(public_payload)
        except Exception as exc:
            logger.exception("Failed to store uploaded file")
            public_files.append({
                "file_id": "",
                "name": str(getattr(uploaded_file, "name", "") or "uploaded-file"),
                "size_bytes": int(getattr(uploaded_file, "size", 0) or 0),
                "status": "error",
                "display_kind": "file",
                "type_label": "Upload failed",
                "error": str(exc),
            })

    return JsonResponse({"files": public_files})


# Handle a chat generation request.
def chat_api(request):
    """Handle chat generation requests and stream assistant output."""

    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        data = _read_json_request_body(request)

        # Read request payload and validate required inputs.
        user_message = data.get("message", "")
        model_name = data.get("model", "")
        system_prompt = _compose_system_prompt(data.get("system_prompt", ""))
        options = data.get("options", {}) or {}
        chat_id = data.get("chat_id", "")
        attachments = _normalize_request_attachments(data)
        uploaded_file_ids = _normalize_uploaded_file_ids(data)
        engine = _get_active_engine(data.get("engine"))
        raw_tool_ids = data.get("tool_server_ids") or data.get("tool_server_id") or data.get("tool_id") or []
        if isinstance(raw_tool_ids, str):
            raw_tool_ids = [raw_tool_ids] if raw_tool_ids.strip() else []
        tool_server_ids = [str(s).strip() for s in raw_tool_ids if str(s).strip()]

        if not model_name:
            return JsonResponse({"error": "Missing model parameter"}, status=400)
        if not user_message and not attachments and not uploaded_file_ids:
            return JsonResponse({"error": "Missing message or attachments"}, status=400)

        _remember_active_model(engine, model_name)
        selected_tool_servers = _resolve_tool_servers(engine, model_name, tool_server_ids)
        model_info_payload = _build_model_info_payload(engine, model_name, allow_fallback=True)
        _sync_runtime_model_metadata(
            engine,
            model_name,
            model_info_payload,
            source="generation",
            route="/api/chat/",
        )
        has_image_attachments = any(
            attachment.get("kind") == MessageAttachmentKind.IMAGE
            for attachment in attachments
            if isinstance(attachment, dict)
        )
        vision_supported = bool(model_info_payload.get("supports_vision", False))
        vision_source = str(model_info_payload.get("supports_vision_source") or "").strip().lower()
        if has_image_attachments and not vision_supported and vision_source == "explicit_false":
            return JsonResponse(
                {
                    "error": (
                        f"Model '{model_name}' does not support image input on '{engine}'. "
                        "Choose a vision-capable model."
                    )
                },
                status=400,
            )
        _validate_tool_server_support(
            engine,
            model_name,
            [server["id"] for server in selected_tool_servers],
            payload=model_info_payload,
        )
        sandbox_enabled = _selected_tools_include_sandbox(selected_tool_servers)
        upload_manifests = _load_model_upload_manifests(uploaded_file_ids, sandbox_enabled=sandbox_enabled)

        persisted_upload_file_ids = _upload_manifest_file_ids(upload_manifests)
        upload_context_entry = _build_uploaded_file_context_entry(persisted_upload_file_ids)

        # Reuse the existing chat when provided, otherwise create a new one.
        try:
            chat = _resolve_chat(chat_id, user_message, attachments or upload_manifests)
        except LookupError as exc:
            return JsonResponse({"error": str(exc)}, status=404)

        import json as _json
        active_slug = _json.dumps([s["id"] for s in selected_tool_servers], ensure_ascii=False)
        if chat.active_tool_slug != active_slug:
            chat.active_tool_slug = active_slug
            chat.save(update_fields=["active_tool_slug", "updated_at"])

        # Persist the incoming user message and its attachments.
        user_message_record = Message.objects.create(
            chat=chat,
            role="user",
            content=user_message,
            llm_transcript=[upload_context_entry] if upload_context_entry else [],
        )
        _store_message_attachments(user_message_record, attachments)
        Chat.objects.filter(pk=chat.pk).update(updated_at=timezone.now())

        # Pre-create the assistant row so the client knows its ID up front
        # and can target it for delete/regenerate without waiting for reload.
        assistant_message_record = Message.objects.create(
            chat=chat,
            role="assistant",
            content="",
            llm_transcript=[],
        )

        # Rebuild the message history expected by the selected backend.
        llm_messages, compression_event = _build_chat_history(
            chat,
            user_message_record,
            user_message,
            system_prompt,
            engine,
            model_name,
            model_info_payload,
            upload_manifests,
            sandbox_enabled=sandbox_enabled,
        )

        # Split generic options from thinking-specific controls.
        think_value, think_level_value, clean_options = _split_generation_options(
            options,
            think_param_name=str(model_info_payload.get("think_param_name", "think") or "think"),
            think_level_param_name=str(model_info_payload.get("think_level_param_name", "think_level") or "think_level"),
        )

        # Build the final generation payload for the adapter layer.
        generate_kwargs = _build_generate_kwargs(
            engine,
            model_name,
            llm_messages,
            think_value,
            think_level_value,
            clean_options,
            chat,
            selected_tool_servers,
            think_param_name=str(model_info_payload.get("think_param_name", "think") or "think"),
            think_level_param_name=str(model_info_payload.get("think_level_param_name", "think_level") or "think_level"),
            sync_operation_defaults=(
                {
                    **(
                        model_info_payload.get("defaults", {})
                        if isinstance(model_info_payload.get("defaults"), dict)
                        else {}
                    ),
                    **(
                        {str(model_info_payload.get("think_param_name")): think_value}
                        if engine == "lms" and think_value is not None and str(model_info_payload.get("think_param_name", "")).startswith("ext.")
                        else {}
                    ),
                    **(
                        {str(model_info_payload.get("think_level_param_name")): think_level_value}
                        if engine == "lms" and think_level_value is not None and str(model_info_payload.get("think_level_param_name", "")).startswith("ext.")
                        else {}
                    ),
                }
                if engine == "lms"
                else {}
            ),
        )

        generation_id = uuid.uuid4().hex
        response = StreamingHttpResponse(
            _stream_chat_response(
                chat,
                engine,
                generate_kwargs,
                assistant_message_record,
                generation_id,
                compression_event=compression_event,
                model_info_payload=model_info_payload,
                system_prompt=system_prompt,
                current_user_message_id=user_message_record.id,
            ),
            content_type="text/plain; charset=utf-8",
        )
        response["X-Chat-ID"] = str(chat.id)
        response["X-LLM-Engine"] = engine
        response["X-User-Message-ID"] = str(user_message_record.id)
        response["X-Assistant-Message-ID"] = str(assistant_message_record.id)
        response["X-Generation-ID"] = generation_id
        return response

    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except Exception as exc:
        logger.exception("Unhandled exception in chat_api")
        return JsonResponse({"error": str(exc)}, status=500)


# Message and chat management APIs.

def _path_is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _shared_file_allowed_roots() -> list[Path]:
    roots = [
        settings.BASE_DIR / "Tools" / "mcp-sandbox" / "_sandbox",
    ]

    sandbox_host_workspace = os.getenv("SANDBOX_HOST_WORKSPACE", "").strip()
    sandbox_default_task_dir = os.getenv("SANDBOX_DEFAULT_TASK_DIR", "_sandbox").strip() or "_sandbox"
    if sandbox_host_workspace:
        roots.append(Path(sandbox_host_workspace) / sandbox_default_task_dir)

    normalized: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        try:
            resolved = root.resolve()
        except OSError:
            continue
        key = str(resolved).lower()
        if key not in seen:
            normalized.append(resolved)
            seen.add(key)
    return normalized


def _resolve_shared_file_path(raw_path: str) -> Path:
    cleaned = str(raw_path or "").strip().strip('"')
    if not cleaned or "\x00" in cleaned:
        raise ValueError("Missing shared file path.")

    raw = Path(cleaned)
    allowed_roots = _shared_file_allowed_roots()
    sandbox_root = settings.BASE_DIR / "Tools" / "mcp-sandbox" / "_sandbox"
    normalized_cleaned = cleaned.replace("\\", "/").strip("/")
    normalized_parts = [part for part in normalized_cleaned.split("/") if part not in {"", "."}]
    mapped_parts = normalized_parts

    if normalized_parts and normalized_parts[0] in {"workspace", "mnt", "home"}:
        if len(normalized_parts) >= 2 and normalized_parts[0] == "workspace" and normalized_parts[1] == "_sandbox":
            mapped_parts = normalized_parts[2:]
        elif len(normalized_parts) >= 2 and normalized_parts[0] == "mnt" and normalized_parts[1] == "data":
            mapped_parts = normalized_parts[2:]
        elif len(normalized_parts) >= 2 and normalized_parts[0] == "home" and normalized_parts[1] == "sandbox":
            mapped_parts = normalized_parts[2:]

    if mapped_parts and mapped_parts[0] == "_sandbox":
        mapped_parts = mapped_parts[1:]

    if mapped_parts and mapped_parts[0].lower() == "user":
        mapped_relative = Path(*mapped_parts)
    else:
        mapped_relative = Path("User") / Path(*mapped_parts) if mapped_parts else Path("User")

    candidate_set: list[Path] = []
    seen: set[str] = set()

    def push_candidate(path: Path) -> None:
        key = str(path).lower()
        if key not in seen:
            seen.add(key)
            candidate_set.append(path)

    if raw.is_absolute():
        push_candidate(raw)
    push_candidate(settings.BASE_DIR / cleaned)
    push_candidate(sandbox_root / cleaned)
    push_candidate(sandbox_root / mapped_relative)

    for candidate in candidate_set:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if not resolved.is_file():
            continue
        if any(_path_is_within(resolved, root) for root in allowed_roots):
            return resolved

    raise FileNotFoundError("Shared file not found or not allowed.")


def _resolve_uploaded_file_content_path(manifest: dict[str, Any]) -> Path:
    """Return the local path for one uploaded file manifest."""

    sandbox_path = str((manifest or {}).get("sandbox_path") or "").strip()
    prefix = "/workspace/_sandbox/User/"
    if not sandbox_path.startswith(prefix):
        raise FileNotFoundError("Uploaded file content is not available")

    relative = sandbox_path[len(prefix):].lstrip("/")
    root = (settings.BASE_DIR / "Tools" / "mcp-sandbox" / "_sandbox" / "User").resolve()
    target = (root / relative).resolve()
    if root != target and root not in target.parents:
        raise ValueError("Unsafe uploaded file path")
    if not target.is_file():
        raise FileNotFoundError("Uploaded file not found")
    return target


MEDIA_RANGE_CHUNK_BYTES = 64 * 1024 * 1024
MEDIA_STREAM_READ_BYTES = 1024 * 1024


def _range_not_satisfiable_response(file_size: int) -> HttpResponse:
    resp = HttpResponse(status=416)
    resp["Content-Range"] = "bytes */" + str(max(0, int(file_size or 0)))
    resp["Accept-Ranges"] = "bytes"
    return resp


def _parse_single_byte_range(range_header: str, file_size: int) -> tuple[int, int] | None:
    """Return one satisfiable byte range, including suffix ranges."""

    if file_size <= 0:
        return None
    range_match = re.fullmatch(r"bytes=(\d*)-(\d*)", str(range_header or "").strip())
    if not range_match:
        return None

    raw_start, raw_end = range_match.group(1), range_match.group(2)
    if not raw_start and not raw_end:
        return None

    if not raw_start:
        suffix_length = int(raw_end)
        if suffix_length <= 0:
            return None
        start = max(file_size - suffix_length, 0)
        end = file_size - 1
        return start, end

    start = int(raw_start)
    if start >= file_size:
        return None

    if raw_end:
        end = min(int(raw_end), file_size - 1)
    else:
        end = min(start + MEDIA_RANGE_CHUNK_BYTES - 1, file_size - 1)
    if start > end:
        return None
    return start, end


def _stream_local_file_response(
    request,
    target: Path,
    *,
    mime_type: str,
    safe_name: str,
    disposition: str = "inline",
):
    """Stream a local file with HTTP Range support for media playback."""

    file_size = target.stat().st_size
    range_header = request.META.get("HTTP_RANGE", "").strip()
    is_head = request.method == "HEAD"

    if range_header:
        parsed_range = _parse_single_byte_range(range_header, file_size)
        if parsed_range is None:
            return _range_not_satisfiable_response(file_size)
        start, end = parsed_range
        chunk_size = end - start + 1
        if is_head:
            response = HttpResponse(status=206, content_type=mime_type)
        else:
            fh = target.open("rb")
            fh.seek(start)

            def _range_iter(fh, remaining):
                try:
                    while remaining > 0:
                        data = fh.read(min(MEDIA_STREAM_READ_BYTES, remaining))
                        if not data:
                            break
                        remaining -= len(data)
                        yield data
                finally:
                    fh.close()

            response = StreamingHttpResponse(_range_iter(fh, chunk_size), status=206, content_type=mime_type)
        response["Content-Range"] = "bytes " + str(start) + "-" + str(end) + "/" + str(file_size)
        response["Content-Length"] = str(chunk_size)
    else:
        if is_head:
            response = HttpResponse(content_type=mime_type)
        else:
            response = FileResponse(target.open("rb"), content_type=mime_type)
        response["Content-Length"] = str(file_size)

    response["Accept-Ranges"] = "bytes"
    response["Cache-Control"] = "private, max-age=300"
    response["Content-Disposition"] = f'{disposition}; filename="{safe_name}"'
    return response


# Return uploaded file bytes on demand.
def uploaded_file_content_api(request, file_id: str):
    """Stream one uploaded file by id with HTTP Range support for media playback."""

    if request.method not in {"GET", "HEAD"}:
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        manifest = load_upload_manifest(file_id)
        if not manifest:
            return JsonResponse({"error": "Uploaded file not found"}, status=404)
        target = _resolve_uploaded_file_content_path(manifest)
        safe_name = re.sub(r"[\"\\\r\n]", "_", Path(str(manifest.get("name") or target.name)).name or "download")
        mime_type = str(manifest.get("mime") or mimetypes.guess_type(str(target))[0] or "application/octet-stream")
        return _stream_local_file_response(request, target, mime_type=mime_type, safe_name=safe_name)
    except FileNotFoundError:
        return JsonResponse({"error": "Uploaded file not found"}, status=404)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except Exception as exc:
        logger.exception("Failed to stream uploaded file")
        return JsonResponse({"error": str(exc)}, status=500)


def shared_file_download_api(request):
    """Download a model-shared local file after validating its workspace path."""

    if request.method not in {"GET", "HEAD"}:
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        target = _resolve_shared_file_path(request.GET.get("path", ""))
        safe_name = re.sub(r'["\\\r\n]', "_", Path(request.GET.get("name") or target.name).name or "download")
        mime_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        disposition = "inline" if str(request.GET.get("preview") or "").lower() in {"1", "true", "yes"} else "attachment"
        return _stream_local_file_response(
            request,
            target,
            mime_type=mime_type,
            safe_name=safe_name,
            disposition=disposition,
        )
    except FileNotFoundError:
        return JsonResponse({"error": "Shared file not found"}, status=404)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except Exception as exc:
        logger.exception("Failed to download shared file")
        return JsonResponse({"error": str(exc)}, status=500)


# Abort active generation.
def abort_generation_api(request):
    """Immediately signal the active LLM generation to stop."""

    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        data = _read_json_request_body(request)
        engine = _get_active_engine(data.get("engine"))
        generation_id = str(data.get("generation_id") or "").strip()
        if generation_id:
            with _generation_state_lock:
                active_id = str(_active_generation_id_by_engine.get(str(engine)) or "")
            if not active_id or active_id != generation_id:
                return JsonResponse({"ok": True, "ignored": True, "reason": "generation_mismatch"})
        llm_api.abort_generation(engine)
        return JsonResponse({"ok": True})
    except Exception as exc:
        logger.exception("Failed to abort generation")
        return JsonResponse({"error": str(exc)}, status=500)


# Return stored attachment bytes on demand.
def attachment_content_api(request, record_type: str, attachment_id: int):
    """Stream one persisted attachment without embedding it into chat JSON."""

    if request.method != "GET":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        normalized_type = str(record_type or "").strip().lower()
        if normalized_type == "attachment":
            attachment = MessageAttachment.objects.get(id=attachment_id)
            mime_type = attachment.mime_type
            name = attachment.name or f"attachment-{attachment.id}"
            encoded = attachment.data
        elif normalized_type == "image":
            attachment = MessageImage.objects.get(id=attachment_id)
            mime_type = attachment.mime_type
            name = f"image-{attachment.order + 1}"
            encoded = attachment.data
        else:
            return JsonResponse({"error": "Unknown attachment type"}, status=404)

        safe_name = re.sub(r'["\\\r\n]', "_", Path(name).name or "attachment")
        response = HttpResponse(_decode_base64_payload(encoded), content_type=mime_type)
        response["Cache-Control"] = "private, max-age=3600"
        response["Content-Disposition"] = f'inline; filename="{safe_name}"'
        return response
    except (MessageAttachment.DoesNotExist, MessageImage.DoesNotExist):
        return JsonResponse({"error": "Attachment not found"}, status=404)
    except Exception as exc:
        logger.exception("Failed to load attachment %s/%s", record_type, attachment_id)
        return JsonResponse({"error": str(exc)}, status=500)


# Delete a specific message by ID.
def delete_message_api(request, message_id):
    """Delete a single message by its primary key."""

    if request.method != "DELETE":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        msg = Message.objects.get(id=message_id)
        msg.delete()
        return JsonResponse({"ok": True})
    except Message.DoesNotExist:
        return JsonResponse({"error": "Message not found"}, status=404)
    except Exception as exc:
        logger.exception("Failed to delete message %s", message_id)
        return JsonResponse({"error": str(exc)}, status=500)


# Delete the last assistant reply for regeneration.
def delete_last_assistant_api(request, chat_id):
    """Delete the last assistant message and return the preceding user message for regeneration."""

    if request.method != "DELETE":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        chat = Chat.objects.get(id=chat_id)
        messages = list(chat.messages.order_by("created_at"))
        if not messages:
            return JsonResponse({"error": "No messages"}, status=400)

        last = messages[-1]
        if last.role != "assistant":
            return JsonResponse({"error": "Last message is not from assistant"}, status=400)

        last.delete()

        # Find the preceding user message to replay.
        user_message = next((m for m in reversed(messages[:-1]) if m.role == "user"), None)
        if not user_message:
            return JsonResponse({"ok": True, "user_message": None})

        attachments = _get_message_attachments(user_message)
        return JsonResponse({
            "ok": True,
            "user_message": {
                "content": user_message.content,
                "attachments": attachments,
                "images": [item["data_url"] for item in attachments if item.get("kind") == MessageAttachmentKind.IMAGE],
            }
        })
    except Chat.DoesNotExist:
        return JsonResponse({"error": "Chat not found"}, status=404)
    except Exception as exc:
        logger.exception("Failed to delete last assistant message for chat %s", chat_id)
        return JsonResponse({"error": str(exc)}, status=500)


# Regenerate the assistant reply for an existing user message without duplicating it.
def regenerate_chat_api(request, chat_id):
    """Re-run generation against an existing user message in the chat."""

    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        data = _read_json_request_body(request)

        model_name = data.get("model", "")
        system_prompt = _compose_system_prompt(data.get("system_prompt", ""))
        options = data.get("options", {}) or {}
        engine = _get_active_engine(data.get("engine"))
        raw_tool_ids = data.get("tool_server_ids") or data.get("tool_server_id") or data.get("tool_id") or []
        if isinstance(raw_tool_ids, str):
            raw_tool_ids = [raw_tool_ids] if raw_tool_ids.strip() else []
        tool_server_ids = [str(s).strip() for s in raw_tool_ids if str(s).strip()]

        if not model_name:
            return JsonResponse({"error": "Missing model parameter"}, status=400)

        try:
            chat = Chat.objects.get(id=chat_id)
        except Chat.DoesNotExist:
            return JsonResponse({"error": "Chat not found"}, status=404)

        target_id = data.get("user_message_id")
        ordered = list(chat.messages.order_by("created_at", "id"))
        if target_id:
            user_message_record = next(
                (m for m in ordered if m.role == "user" and str(m.id) == str(target_id)),
                None,
            )
        else:
            user_message_record = next((m for m in reversed(ordered) if m.role == "user"), None)

        if user_message_record is None:
            return JsonResponse({"error": "No user message to regenerate"}, status=400)

        # Drop every message that came after the targeted user turn, including
        # the assistant reply we are about to replace.
        preserve_context_compression = bool(data.get("preserve_context_compression"))
        for message in ordered:
            if message.created_at > user_message_record.created_at or (
                message.created_at == user_message_record.created_at and message.id > user_message_record.id
            ):
                if preserve_context_compression and _message_has_context_compression_summary(message):
                    continue
                message.delete()

        _remember_active_model(engine, model_name)
        selected_tool_servers = _resolve_tool_servers(engine, model_name, tool_server_ids)
        model_info_payload = _build_model_info_payload(engine, model_name, allow_fallback=True)
        _sync_runtime_model_metadata(
            engine,
            model_name,
            model_info_payload,
            source="regeneration",
            route="/api/chat/regenerate/",
        )
        _validate_tool_server_support(
            engine,
            model_name,
            [server["id"] for server in selected_tool_servers],
            payload=model_info_payload,
        )
        sandbox_enabled = _selected_tools_include_sandbox(selected_tool_servers)

        import json as _json
        active_slug = _json.dumps([s["id"] for s in selected_tool_servers], ensure_ascii=False)
        if chat.active_tool_slug != active_slug:
            chat.active_tool_slug = active_slug
            chat.save(update_fields=["active_tool_slug", "updated_at"])

        llm_messages, compression_event = _build_chat_history(
            chat,
            user_message_record,
            user_message_record.content,
            system_prompt,
            engine,
            model_name,
            model_info_payload,
            sandbox_enabled=sandbox_enabled,
        )

        think_value, think_level_value, clean_options = _split_generation_options(
            options,
            think_param_name=str(model_info_payload.get("think_param_name", "think") or "think"),
            think_level_param_name=str(model_info_payload.get("think_level_param_name", "think_level") or "think_level"),
        )

        generate_kwargs = _build_generate_kwargs(
            engine,
            model_name,
            llm_messages,
            think_value,
            think_level_value,
            clean_options,
            chat,
            selected_tool_servers,
            think_param_name=str(model_info_payload.get("think_param_name", "think") or "think"),
            think_level_param_name=str(model_info_payload.get("think_level_param_name", "think_level") or "think_level"),
            sync_operation_defaults=(
                {
                    **(
                        model_info_payload.get("defaults", {})
                        if isinstance(model_info_payload.get("defaults"), dict)
                        else {}
                    ),
                    **(
                        {str(model_info_payload.get("think_param_name")): think_value}
                        if engine == "lms" and think_value is not None and str(model_info_payload.get("think_param_name", "")).startswith("ext.")
                        else {}
                    ),
                    **(
                        {str(model_info_payload.get("think_level_param_name")): think_level_value}
                        if engine == "lms" and think_level_value is not None and str(model_info_payload.get("think_level_param_name", "")).startswith("ext.")
                        else {}
                    ),
                }
                if engine == "lms"
                else {}
            ),
        )

        assistant_message_record = Message.objects.create(
            chat=chat,
            role="assistant",
            content="",
            llm_transcript=[],
        )

        generation_id = uuid.uuid4().hex
        response = StreamingHttpResponse(
            _stream_chat_response(
                chat,
                engine,
                generate_kwargs,
                assistant_message_record,
                generation_id,
                compression_event=compression_event,
                model_info_payload=model_info_payload,
                system_prompt=system_prompt,
                current_user_message_id=user_message_record.id,
            ),
            content_type="text/plain; charset=utf-8",
        )
        response["X-Chat-ID"] = str(chat.id)
        response["X-LLM-Engine"] = engine
        response["X-User-Message-ID"] = str(user_message_record.id)
        response["X-Assistant-Message-ID"] = str(assistant_message_record.id)
        response["X-Generation-ID"] = generation_id
        return response

    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except Exception as exc:
        logger.exception("Unhandled exception in regenerate_chat_api")
        return JsonResponse({"error": str(exc)}, status=500)


# Rename a chat thread.
def rename_chat_api(request, chat_id):
    """Rename a chat thread."""

    if request.method != "PATCH":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        data = _read_json_request_body(request)
        title = str(data.get("title", "")).strip()
        if not title:
            return JsonResponse({"error": "Title is required"}, status=400)

        chat = Chat.objects.get(id=chat_id)
        chat.title = title
        chat.save(update_fields=["title"])
        return JsonResponse({"ok": True, "title": chat.title})
    except Chat.DoesNotExist:
        return JsonResponse({"error": "Chat not found"}, status=404)
    except Exception as exc:
        logger.exception("Failed to rename chat %s", chat_id)
        return JsonResponse({"error": str(exc)}, status=500)


# Delete a chat thread and all its messages.
def delete_chat_api(request, chat_id):
    """Delete a chat thread and all its messages."""

    if request.method != "DELETE":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        chat = Chat.objects.get(id=chat_id)
        chat.delete()
        return JsonResponse({"ok": True})
    except Chat.DoesNotExist:
        return JsonResponse({"error": "Chat not found"}, status=404)
    except Exception as exc:
        logger.exception("Failed to delete chat %s", chat_id)
        return JsonResponse({"error": str(exc)}, status=500)


# Load persisted messages for a chat thread.
def load_chat_api(request, chat_id):
    """Load persisted messages for a chat thread."""

    if request.method != "GET":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        chat = Chat.objects.get(id=chat_id)
        messages = chat.messages.all().prefetch_related("attachments", "images")
        payload = [_serialize_message(message, include_attachment_data=False) for message in messages]
        active_tool_server_ids = _parse_active_tool_slugs(chat.active_tool_slug)
        return JsonResponse({
            "chat_id": str(chat.id),
            "title": chat.title,
            "messages": payload,
            "active_tool_server_ids": active_tool_server_ids,
            "active_tool_server_id": active_tool_server_ids[0] if active_tool_server_ids else "",
        })
    except Chat.DoesNotExist:
        return JsonResponse({"error": "Chat not found"}, status=404)
    except Exception as exc:
        logger.exception("Failed to load chat %s", chat_id)
        return JsonResponse({"error": str(exc)}, status=500)


# Model and tool discovery APIs.

# Return model metadata for the selected engine.
def get_model_info_api(request):
    """Return model capabilities and default parameters for the selected engine."""

    if request.method != "GET":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    model_name = request.GET.get("model", "")
    if not model_name:
        return JsonResponse({"error": "Model parameter is required"}, status=400)

    engine = _get_active_engine(request.GET.get("engine"))
    started_at = time.perf_counter()

    try:
        payload = _build_model_info_payload(engine, model_name)
        _remember_active_model(engine, model_name)
        _print_runtime_event(
            "Model info loaded: "
            f"engine={engine}, "
            f"model={model_name}, "
            f"tools={len(payload.get('available_tool_servers', []) or [])}, "
            f"options={_summarize_option_keys(payload.get('defaults', {}))}, "
            f"took={(time.perf_counter() - started_at):.2f}s"
        )
        return JsonResponse(payload)
    except NotImplementedError as exc:
        logger.info("Model info is not implemented for engine %s: %s", engine, exc)
        _print_runtime_event(f"Model info not supported: engine={engine}, model={model_name}")
        return JsonResponse({"error": str(exc)}, status=501)
    except Exception as exc:
        formatted_error = _format_runtime_error(engine, exc)
        if _is_expected_runtime_error(exc):
            logger.warning("Error getting model info for %s on engine %s: %s", model_name, engine, formatted_error)
        else:
            logger.exception("Error getting model info for %s on engine %s", model_name, engine)
        _print_runtime_event(f"Model info failed: engine={engine}, model={model_name}, error={formatted_error}")
        return JsonResponse({"error": formatted_error}, status=500)


# Return unified runtime inference metadata for the active engine/model.
def get_inference_info_api(request):
    """Return active inference engine, model, context and output limits."""

    if request.method != "GET":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    engine = _get_active_engine(request.GET.get("engine"))
    model_name, model_source = _resolve_inference_model(engine, request.GET.get("model"))
    if not model_name:
        return JsonResponse(
            {
                "ok": False,
                "engine": engine,
                "engine_label": _get_engine_label(engine),
                "model": "",
                "model_name": "",
                "context_window": None,
                "model_context_limit": None,
                "max_output_tokens": None,
                "output_token_limit": None,
                "limits": {
                    "context_window": None,
                    "model_context_limit": None,
                    "max_output_tokens": None,
                    "output_token_limit": None,
                },
                "capabilities": {
                    "items": [],
                    "supports_thinking": False,
                    "supports_think_toggle": False,
                    "supports_think_level": False,
                    "supports_vision": False,
                    "supports_tool_calling": False,
                    "supports_files": False,
                },
                "generation_defaults": {},
                "supported_parameters": [],
                "runtime_limits": {},
                "tool_servers": [],
                "source": {"model": model_source},
                "error": "No active model is available for the selected engine.",
            },
            status=404,
        )

    started_at = time.perf_counter()

    try:
        model_info_payload = _build_model_info_payload(engine, model_name)
        if model_source == "request":
            _remember_active_model(engine, model_name)
        payload = _build_inference_info_payload(engine, model_name, model_info_payload, model_source)
        _sync_runtime_model_metadata(
            engine,
            model_name,
            model_info_payload,
            source=model_source,
            route="/api/inference_info/",
        )
        _print_runtime_event(
            "Inference info loaded: "
            f"engine={engine}, "
            f"model={model_name}, "
            f"context={payload.get('context_window')}, "
            f"output={payload.get('max_output_tokens')}, "
            f"took={(time.perf_counter() - started_at):.2f}s"
        )
        return JsonResponse(payload)
    except NotImplementedError as exc:
        logger.info("Inference info is not implemented for engine %s: %s", engine, exc)
        _print_runtime_event(f"Inference info not supported: engine={engine}, model={model_name}")
        return JsonResponse({"ok": False, "engine": engine, "model": model_name, "error": str(exc)}, status=501)
    except Exception as exc:
        formatted_error = _format_runtime_error(engine, exc)
        if _is_expected_runtime_error(exc):
            logger.warning("Error getting inference info for %s on engine %s: %s", model_name, engine, formatted_error)
        else:
            logger.exception("Error getting inference info for %s on engine %s", model_name, engine)
        _print_runtime_event(f"Inference info failed: engine={engine}, model={model_name}, error={formatted_error}")
        return JsonResponse({"ok": False, "engine": engine, "model": model_name, "error": formatted_error}, status=500)


# Return the model list for the selected engine.
def get_models_api(request):
    """Return model names for the requested engine."""

    if request.method != "GET":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    engine = _get_active_engine(request.GET.get("engine"))
    started_at = time.perf_counter()
    models = _load_models_for_engine(engine)
    _print_runtime_event(
        f"Models loaded: engine={engine}, count={len(models)}, took={(time.perf_counter() - started_at):.2f}s"
    )
    return JsonResponse({"engine": engine, "models": models})


# Return discovered tool servers.
def mcp_config_api(request):
    """Read or replace ``MCP/mcp.json`` (LM Studio / Cursor style user MCP servers)."""

    mcp_json.ensure_default_mcp_json()

    if request.method == "GET":
        return JsonResponse({"content": mcp_json.load_raw_text()})

    if request.method not in {"PUT", "PATCH"}:
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        payload = _read_json_request_body(request)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    content = payload.get("content")
    if not isinstance(content, str):
        return JsonResponse({"error": "Expected JSON object with string field 'content'"}, status=400)

    try:
        mcp_json.save_raw_text(content)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    tool_registry.reset_cache()
    _clear_tool_server_cache()

    return JsonResponse({"ok": True, "content": mcp_json.load_raw_text()})


def get_tools_api(request):
    """Return locally discovered MCP-style tool servers for the requested engine/model."""

    if request.method != "GET":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    engine = _get_active_engine(request.GET.get("engine"))
    model_name = str(request.GET.get("model", "") or "").strip() or None
    servers = _list_tool_servers_cached(engine, model_name)
    return JsonResponse({"tool_servers": servers, "servers": servers, "tools": servers})


def favicon_api(request):
    """Resolve and proxy a stable favicon for a search result domain."""

    def image_response(content_type: str, content: bytes) -> HttpResponse:
        response = HttpResponse(content, content_type=content_type)
        response["Cache-Control"] = "public, max-age=604800"
        response["X-Content-Type-Options"] = "nosniff"
        return response

    if request.method != "GET":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    domain = _normalize_favicon_domain(request.GET.get("domain") or request.GET.get("url") or "")
    if not domain:
        return JsonResponse({"error": "Domain is required"}, status=400)

    now = time.time()
    with _favicon_cache_lock:
        cached = _favicon_cache.get(domain)
        if cached and cached[0] > now:
            content_type, content = cached[1], cached[2]
            if content:
                return image_response(content_type, content)
            return HttpResponse(status=404)

        disk_cached = _read_favicon_disk_cache(domain, now)
        if disk_cached:
            content_type, content = disk_cached
            _favicon_cache[domain] = (now + FAVICON_CACHE_TTL_SECONDS, content_type, content)
            return image_response(content_type, content)

    resolved = _resolve_favicon_content(domain)
    with _favicon_cache_lock:
        if resolved:
            content_type, content = resolved
            expires_at = now + FAVICON_CACHE_TTL_SECONDS
            _favicon_cache[domain] = (expires_at, content_type, content)
            _write_favicon_disk_cache(domain, content_type, content, expires_at)
            return image_response(content_type, content)

        _favicon_cache[domain] = (now + FAVICON_NEGATIVE_CACHE_TTL_SECONDS, "", b"")

    return HttpResponse(status=404)


# Preset APIs.

# Return Ollama preset metadata.
def get_ollama_presets_api(request):
    """Return preset metadata for the selected Ollama model."""

    if request.method != "GET":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    model_name = str(request.GET.get("model", "") or "").strip()
    if not model_name:
        return JsonResponse({"error": "Model parameter is required"}, status=400)

    try:
        return JsonResponse(get_ollama_preset_payload(model_name))
    except Exception as exc:
        logger.exception("Error getting Ollama presets for %s", model_name)
        return JsonResponse({"error": str(exc)}, status=500)


def get_context_usage_api(request):
    """Return estimated/observed context usage for the current chat and model."""

    if request.method != "GET":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        engine = _get_active_engine(request.GET.get("engine"))
        model_name = str(request.GET.get("model") or _get_remembered_active_model(engine) or "").strip()
        chat_id = str(request.GET.get("chat_id") or "").strip()
        draft_text = str(request.GET.get("draft") or "")
        system_prompt = _compose_system_prompt(str(request.GET.get("system_prompt") or ""))

        model_info_payload = _build_model_info_payload(engine, model_name, allow_fallback=True)
        chat: Chat | None = None
        if chat_id:
            try:
                chat = Chat.objects.get(id=chat_id)
            except Chat.DoesNotExist:
                chat = None

        estimate = _estimate_context_usage(
            chat=chat,
            system_prompt=system_prompt,
            draft_text=draft_text,
            model_info_payload=model_info_payload,
            active_engine=engine,
            active_model=model_name,
        )
        with _chat_usage_lock:
            observed = dict(_chat_usage_by_chat_id.get(chat_id, {})) if chat_id else {}

        response_payload = {
            "engine": engine,
            "model": model_name,
            "chat_id": chat_id,
            "context_window_tokens": estimate["context_window_tokens"],
            "estimated_used_tokens": estimate["estimated_used_tokens"],
            "estimated_used_chars": estimate["estimated_used_chars"],
            "ratio": estimate["ratio"],
            "threshold_ratio": LLM_HISTORY_COMPRESSION_TRIGGER_RATIO,
            "compressed_context_active": bool(estimate.get("compressed_context_active")),
            "observed_usage": observed,
            "token_estimator": {
                "mode": "adaptive",
                "base_chars_per_token": estimate.get("base_chars_per_token"),
                "effective_chars_per_token": estimate.get("effective_chars_per_token"),
                "chat_observed_chars_per_token": estimate.get("observed_chars_per_token"),
                "observed_chars_per_token": observed.get("observed_chars_per_token"),
                "prompt_chars_estimate": observed.get("prompt_chars_estimate"),
            },
        }
        return JsonResponse(response_payload)
    except Exception as exc:
        logger.exception("Failed to build context usage payload")
        return JsonResponse({"error": str(exc)}, status=500)


def context_compress_api(request):
    """Force or opportunistically run context compression and persist a timeline marker."""

    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        data = _read_json_request_body(request)
        engine = _get_active_engine(data.get("engine"))
        model_name = str(data.get("model") or _get_remembered_active_model(engine) or "").strip()
        chat_id = str(data.get("chat_id") or "").strip()
        if not chat_id:
            return JsonResponse({"ok": True, "applied": False, "reason": "missing_chat_id"})
        force = bool(data.get("force"))
        system_prompt = _compose_system_prompt(str(data.get("system_prompt") or ""))
        draft_text = str(data.get("draft") or data.get("draft_text") or "")

        try:
            chat = Chat.objects.get(id=chat_id)
        except Chat.DoesNotExist:
            return JsonResponse({"ok": True, "applied": False, "reason": "chat_not_found"})

        with _generation_state_lock:
            active_generation_id = str(_active_generation_id_by_chat_id.get(str(chat.id)) or "")
        if active_generation_id:
            return JsonResponse({
                "ok": True,
                "applied": False,
                "reason": "generation_active",
            }, status=409)

        model_info_payload = _build_model_info_payload(engine, model_name, allow_fallback=True)
        event = _build_manual_compression_event(
            chat=chat,
            system_prompt=system_prompt,
            draft_text=draft_text,
            engine=engine,
            model_name=model_name,
            model_info_payload=model_info_payload,
            force=force,
        )
        if not event:
            return JsonResponse({"ok": True, "applied": False, "reason": "below_threshold"})

        message = Message.objects.create(
            chat=chat,
            role="assistant",
            content="",
            llm_transcript=[event],
        )
        Chat.objects.filter(pk=chat.pk).update(updated_at=timezone.now())
        return JsonResponse({
            "ok": True,
            "applied": True,
            "message": _serialize_message(message, include_attachment_data=False),
        })
    except Exception as exc:
        logger.exception("Failed to run context compression")
        return JsonResponse({"error": str(exc)}, status=500)


# Return preset metadata for the selected LM Studio model.
def get_lms_presets_api(request):
    """Return preset metadata for the selected LM Studio model."""

    if request.method != "GET":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    model_name = str(request.GET.get("model", "") or "").strip()
    if not model_name:
        return JsonResponse({"error": "Model parameter is required"}, status=400)

    try:
        return JsonResponse(get_lms_preset_payload(model_name))
    except Exception as exc:
        logger.exception("Error getting LM Studio presets for %s", model_name)
        return JsonResponse({"error": str(exc)}, status=500)


# Return a JSON response after invalidating model metadata.
def _preset_mutation_response(payload: dict[str, Any]) -> JsonResponse:
    """Invalidate model-info caches after a preset mutation."""

    _clear_model_metadata_caches()
    return JsonResponse(payload)


# Sync the active Ollama preset.
def sync_ollama_preset_api(request):
    """Persist UI changes to the active Ollama preset."""

    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        data = _read_json_request_body(request)
        model_name = str(data.get("model", "") or "").strip()
        config = data.get("config", {})
        if not model_name:
            return JsonResponse({"error": "Model parameter is required"}, status=400)
        return _preset_mutation_response(sync_active_ollama_preset(model_name, config))
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except Exception as exc:
        logger.exception("Error syncing Ollama preset")
        return JsonResponse({"error": str(exc)}, status=500)


# Persist UI changes to the active LM Studio preset.
def sync_lms_preset_api(request):
    """Persist UI changes to the active LM Studio preset."""

    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        data = _read_json_request_body(request)
        model_name = str(data.get("model", "") or "").strip()
        config = data.get("config", {})
        if not model_name:
            return JsonResponse({"error": "Model parameter is required"}, status=400)
        return _preset_mutation_response(sync_active_lms_preset(model_name, config))
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except Exception as exc:
        logger.exception("Error syncing LM Studio preset")
        return JsonResponse({"error": str(exc)}, status=500)


# Activate an Ollama preset.
def select_ollama_preset_api(request):
    """Set the active preset for an Ollama model."""

    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        data = _read_json_request_body(request)
        model_name = str(data.get("model", "") or "").strip()
        preset_id = str(data.get("preset_id", "") or "").strip()
        if not model_name or not preset_id:
            return JsonResponse({"error": "Model and preset_id are required"}, status=400)
        return _preset_mutation_response(activate_ollama_preset(model_name, preset_id))
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except OllamaPreset.DoesNotExist as exc:
        return JsonResponse({"error": str(exc)}, status=404)
    except Exception as exc:
        logger.exception("Error selecting Ollama preset")
        return JsonResponse({"error": str(exc)}, status=500)


# Set the active preset for an LM Studio model.
def select_lms_preset_api(request):
    """Set the active preset for an LM Studio model."""

    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        data = _read_json_request_body(request)
        model_name = str(data.get("model", "") or "").strip()
        preset_id = str(data.get("preset_id", "") or "").strip()
        if not model_name or not preset_id:
            return JsonResponse({"error": "Model and preset_id are required"}, status=400)
        return _preset_mutation_response(activate_lms_preset(model_name, preset_id))
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except LmsPreset.DoesNotExist as exc:
        return JsonResponse({"error": str(exc)}, status=404)
    except Exception as exc:
        logger.exception("Error selecting LM Studio preset")
        return JsonResponse({"error": str(exc)}, status=500)


# Create an Ollama preset.
def create_ollama_preset_api(request):
    """Create a new Ollama preset for the selected model."""

    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        data = _read_json_request_body(request)
        model_name = str(data.get("model", "") or "").strip()
        preset_name = str(data.get("name", "") or "").strip()
        config = data.get("config", {})
        if not model_name:
            return JsonResponse({"error": "Model parameter is required"}, status=400)
        return _preset_mutation_response(
            create_ollama_preset(
                model_name,
                name=preset_name or None,
                config=config if isinstance(config, dict) else {},
                activate=True,
            )
        )
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except Exception as exc:
        logger.exception("Error creating Ollama preset")
        return JsonResponse({"error": str(exc)}, status=500)


# Create a new LM Studio preset for the selected model.
def create_lms_preset_api(request):
    """Create a new LM Studio preset for the selected model."""

    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        data = _read_json_request_body(request)
        model_name = str(data.get("model", "") or "").strip()
        preset_name = str(data.get("name", "") or "").strip()
        config = data.get("config", {})
        if not model_name:
            return JsonResponse({"error": "Model parameter is required"}, status=400)
        return _preset_mutation_response(
            create_lms_preset(
                model_name,
                name=preset_name or None,
                config=config if isinstance(config, dict) else {},
                activate=True,
            )
        )
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except Exception as exc:
        logger.exception("Error creating LM Studio preset")
        return JsonResponse({"error": str(exc)}, status=500)


# Rename an Ollama preset.
def rename_ollama_preset_api(request):
    """Rename an existing custom Ollama preset."""

    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        data = _read_json_request_body(request)
        model_name = str(data.get("model", "") or "").strip()
        preset_id = str(data.get("preset_id", "") or "").strip()
        preset_name = str(data.get("name", "") or "").strip()
        if not model_name or not preset_id or not preset_name:
            return JsonResponse({"error": "Model, preset_id and name are required"}, status=400)
        return _preset_mutation_response(rename_ollama_preset(model_name, preset_id, preset_name))
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except OllamaPreset.DoesNotExist as exc:
        return JsonResponse({"error": str(exc)}, status=404)
    except Exception as exc:
        logger.exception("Error renaming Ollama preset")
        return JsonResponse({"error": str(exc)}, status=500)


# Rename an existing custom LM Studio preset.
def rename_lms_preset_api(request):
    """Rename an existing custom LM Studio preset."""

    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        data = _read_json_request_body(request)
        model_name = str(data.get("model", "") or "").strip()
        preset_id = str(data.get("preset_id", "") or "").strip()
        preset_name = str(data.get("name", "") or "").strip()
        if not model_name or not preset_id or not preset_name:
            return JsonResponse({"error": "Model, preset_id and name are required"}, status=400)
        return _preset_mutation_response(rename_lms_preset(model_name, preset_id, preset_name))
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except LmsPreset.DoesNotExist as exc:
        return JsonResponse({"error": str(exc)}, status=404)
    except Exception as exc:
        logger.exception("Error renaming LM Studio preset")
        return JsonResponse({"error": str(exc)}, status=500)


# Delete an Ollama preset.
def delete_ollama_preset_api(request):
    """Delete an existing custom preset and fall back to the default one."""

    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        data = _read_json_request_body(request)
        model_name = str(data.get("model", "") or "").strip()
        preset_id = str(data.get("preset_id", "") or "").strip()
        if not model_name or not preset_id:
            return JsonResponse({"error": "Model and preset_id are required"}, status=400)
        return _preset_mutation_response(delete_ollama_preset(model_name, preset_id))
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except OllamaPreset.DoesNotExist as exc:
        return JsonResponse({"error": str(exc)}, status=404)
    except Exception as exc:
        logger.exception("Error deleting Ollama preset")
        return JsonResponse({"error": str(exc)}, status=500)


# Delete an existing custom preset and fall back to the default one.
def delete_lms_preset_api(request):
    """Delete an existing custom preset and fall back to the default one."""

    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        data = _read_json_request_body(request)
        model_name = str(data.get("model", "") or "").strip()
        preset_id = str(data.get("preset_id", "") or "").strip()
        if not model_name or not preset_id:
            return JsonResponse({"error": "Model and preset_id are required"}, status=400)
        return _preset_mutation_response(delete_lms_preset(model_name, preset_id))
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except LmsPreset.DoesNotExist as exc:
        return JsonResponse({"error": str(exc)}, status=404)
    except Exception as exc:
        logger.exception("Error deleting LM Studio preset")
        return JsonResponse({"error": str(exc)}, status=500)


# Runtime settings API.

# Read or update runtime settings.
def runtime_settings_api(request):
    """Read or update runtime engine settings used by the chat UI."""

    if request.method == "GET":
        return JsonResponse(_build_runtime_settings_payload())

    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        data = _read_json_request_body(request)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    allowed_keys = {
        "llm-engine",
        "lms_url",
        "openai_url",
        "openai_api_key",
        "google_genai_url",
        "google_genai_api_key",
    }

    previous_engine = settings.get_llm_engine()
    next_engine = previous_engine

    def _is_masked_api_key(value: str) -> bool:
        """Return whether the payload looks like a masked placeholder, not a real key."""

        raw = str(value or "")
        stripped = raw.strip()
        if not stripped:
            return False

        # Password placeholders often arrive as repeated mask glyphs.
        if all(char in {"*", "\u2022", "\u25cf", "\u2219", "\u00b7", "\u25e6"} for char in stripped):
            return True

        lowered = stripped.lower()
        if lowered in {
            "stored api key",
            "stored api key.",
            "stored key",
            "use saved key",
        }:
            return True

        return False

    # Persist only known settings and normalize engine-specific values.
    for raw_key, raw_value in data.items():
        if raw_key not in allowed_keys:
            continue

        if raw_key == "llm-engine":
            value = settings.resolve_enabled_engine(raw_value)
            next_engine = value
        else:
            value = str(raw_value or "").strip()
            if raw_key in {"openai_api_key", "google_genai_api_key"} and _is_masked_api_key(value):
                # Ignore UI mask placeholders so they never overwrite real keys.
                continue

        settings.set(raw_key, value)

    # Apply runtime transitions after the new settings are saved.
    llm_api.handle_engine_transition(previous_engine, next_engine)
    _clear_model_metadata_caches()

    return JsonResponse(_build_runtime_settings_payload())


# Browser portal control APIs.

_frame404_burst_log_count = 0
_frame404_burst_log_last_ts = 0.0


def _browser_portal_roots() -> list[Path]:
    return [
        settings.BASE_DIR / "Data" / "runtime" / "browser_portal",
    ]


def _browser_portal_debug_log_path(root: Path | None = None) -> Path:
    return (root or _browser_portal_roots()[0]) / "debug.jsonl"


def _browser_portal_debug_safe(value: Any, *, depth: int = 0) -> Any:
    if depth > 4:
        return repr(value)[:4000]
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, str):
        return value[:4000]
    if isinstance(value, dict):
        return {
            str(key)[:200]: _browser_portal_debug_safe(child, depth=depth + 1)
            for key, child in value.items()
            if str(key) not in {"data_base64", "preview"}
        }
    if isinstance(value, (list, tuple, set)):
        return [_browser_portal_debug_safe(child, depth=depth + 1) for child in list(value)[:50]]
    return repr(value)[:4000]


def _browser_portal_http_event_body_for_log(data: dict[str, Any] | None) -> dict[str, Any]:
    """Compact portal POST body for debug.jsonl (typing floods the log otherwise)."""

    if not isinstance(data, dict):
        return {}
    event_type = str(data.get("type") or "").strip().lower()
    slim: dict[str, Any] = {}
    for key in ("id", "created_at", "type", "version", "session_id"):
        if key in data:
            slim[key] = data[key]
    client_meta = data.get("client_meta")
    if isinstance(client_meta, dict):
        slim["client_meta_keys"] = list(client_meta.keys())[:40]
    if event_type == "type":
        text = data.get("text")
        slim["text_len"] = len(text) if isinstance(text, str) else 0
    elif event_type == "key":
        slim["key"] = str(data.get("key") or "")[:120]
    else:
        for key in ("x", "y", "delta_x", "delta_y", "viewport_width", "viewport_height"):
            if key in data:
                slim[key] = data[key]
    return slim


def _write_browser_portal_debug_event(root: Path | None, event: str, **fields: Any) -> None:
    """Browser portal debug logging is intentionally disabled."""

    return None


def _read_browser_portal_state_from(root: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads((root / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _is_active_browser_portal_state(payload: dict[str, Any]) -> bool:
    if str(payload.get("status") or "").lower() != "waiting":
        return False
    try:
        updated_at = float(payload.get("updated_at") or 0)
        timeout_seconds = float(payload.get("timeout_seconds") or 45)
        deadline_at = float(payload.get("deadline_at") or 0)
    except (TypeError, ValueError):
        return False
    if deadline_at > 0:
        return time.time() <= deadline_at + 10
    return updated_at > 0 and time.time() <= updated_at + timeout_seconds + 10


def _active_browser_portal_root() -> Path | None:
    candidates: list[tuple[float, Path]] = []
    for root in _browser_portal_roots():
        payload = _read_browser_portal_state_from(root)
        if payload and _is_active_browser_portal_state(payload):
            try:
                candidates.append((float(payload.get("updated_at") or 0), root))
            except (TypeError, ValueError):
                continue
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def _browser_portal_state_path() -> Path:
    root = _active_browser_portal_root()
    if root is None:
        return _browser_portal_roots()[0] / "state.json"
    return root / "state.json"


def _browser_portal_events_dir() -> Path:
    root = _active_browser_portal_root()
    if root is None:
        return _browser_portal_roots()[0] / "events"
    return root / "events"


def _read_browser_portal_state() -> dict[str, Any]:
    root = _active_browser_portal_root()
    if root is None:
        return {"ok": False, "error": "No active browser_wait_for_user session is available."}
    payload = _read_browser_portal_state_from(root)
    return payload if payload else {"ok": False, "error": "Invalid browser portal state."}


def browser_portal_frame_api(request):
    """Return the latest frame published by browser_wait_for_user."""

    global _frame404_burst_log_count, _frame404_burst_log_last_ts

    if request.method != "GET":
        _write_browser_portal_debug_event(None, "frame_rejected_method", method=request.method)
        return JsonResponse({"error": "Invalid request method"}, status=405)
    payload = _read_browser_portal_state()
    status = 200 if payload.get("ok") else 404
    if status == 200:
        _frame404_burst_log_count = 0
    if status != 200:
        should_log_frame = True
        if status == 404:
            now_ts = time.time()
            _frame404_burst_log_count += 1
            if _frame404_burst_log_count <= 8:
                should_log_frame = True
            elif now_ts - _frame404_burst_log_last_ts >= 5.0:
                _frame404_burst_log_last_ts = now_ts
                should_log_frame = True
            else:
                should_log_frame = False
        if should_log_frame:
            _write_browser_portal_debug_event(
                _active_browser_portal_root(),
                "frame_response",
                status_code=status,
                payload_status=payload.get("status"),
                session_id=payload.get("session_id"),
                ok=payload.get("ok"),
                error=payload.get("error"),
                has_frame=isinstance(payload.get("frame"), dict),
                url=payload.get("url"),
            )
    return JsonResponse(payload, status=status)


def browser_portal_event_api(request):
    """Queue one human portal event for the active browser_wait_for_user loop."""

    if request.method != "POST":
        _write_browser_portal_debug_event(None, "event_rejected_method", method=request.method)
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        data = _read_json_request_body(request)
    except ValueError as exc:
        _write_browser_portal_debug_event(None, "event_rejected_invalid_json", error=str(exc))
        return JsonResponse({"error": str(exc)}, status=400)

    event_type = str(data.get("type") or "").strip().lower()
    _write_browser_portal_debug_event(
        _active_browser_portal_root(),
        "event_received",
        event_type=event_type,
        payload=_browser_portal_http_event_body_for_log(data),
        request_path=request.path,
    )
    if event_type not in {"click", "scroll", "key", "type", "finish", "click_ref"}:
        _write_browser_portal_debug_event(None, "event_rejected_unsupported_type", event_type=event_type, payload=_browser_portal_http_event_body_for_log(data))
        return JsonResponse({"error": "Unsupported browser portal event type."}, status=400)

    active_root = _active_browser_portal_root()
    if active_root is None:
        _write_browser_portal_debug_event(None, "event_rejected_no_active_session", event_type=event_type, payload=_browser_portal_http_event_body_for_log(data))
        return JsonResponse({"error": "No active browser_wait_for_user session is available."}, status=409)

    active_state = _read_browser_portal_state_from(active_root) or {}
    active_session_id = str(active_state.get("session_id") or "").strip()
    requested_session_id = str(data.get("session_id") or "").strip()
    if requested_session_id and active_session_id and requested_session_id != active_session_id:
        _write_browser_portal_debug_event(
            active_root,
            "event_rejected_session_mismatch",
            event_type=event_type,
            requested_session_id=requested_session_id,
            active_session_id=active_session_id,
            payload=_browser_portal_http_event_body_for_log(data),
        )
        return JsonResponse({"error": "This browser_wait_for_user session is no longer active."}, status=409)

    events_dir = active_root / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    event_id = uuid.uuid4().hex
    event_payload = {
        "id": event_id,
        "created_at": time.time(),
        **data,
        "type": event_type,
    }
    if active_session_id:
        event_payload["session_id"] = active_session_id
    event_path = events_dir / f"event_{int(time.time() * 1000)}_{event_id}.json"
    event_path.write_text(json.dumps(event_payload, ensure_ascii=False), encoding="utf-8")
    _write_browser_portal_debug_event(
        active_root,
        "event_written",
        event_id=event_id,
        event_type=event_type,
        event_path=str(event_path),
        active_session_id=active_session_id,
        requested_session_id=requested_session_id,
        payload=_browser_portal_http_event_body_for_log(event_payload),
    )

    if event_type == "finish":
        payload = {
            **active_state,
            "ok": True,
            "status": "done",
            "updated_at": time.time(),
            "version": int(time.time() * 1000),
        }
    else:
        payload = _read_browser_portal_state()
    if not payload.get("ok"):
        payload = {"ok": True, "event_id": event_id, "queued": True}
    else:
        payload = {**payload, "event_id": event_id, "queued": True}
    _write_browser_portal_debug_event(
        active_root,
        "event_response",
        event_id=event_id,
        event_type=event_type,
        queued=True,
        response_status=payload.get("status"),
        response_session_id=payload.get("session_id"),
    )
    return JsonResponse(payload)


# Additional page views.

# Render the profile page.
class ProfileView(TemplateView):
    template_name = "main/profile.html"

    # Build the profile page context.
    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """Return template context for the profile page."""

        context = super().get_context_data(**kwargs)
        context.update(_build_base_context())
        return context


# Render the preloaded chat page.
class ChatView(TemplateView):
    template_name = "main/main.html"

    # Build the preloaded chat page context.
    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """Return template context for a preloaded chat page."""

        context = super().get_context_data(**kwargs)
        context.update(_build_base_context())
        context["preload_chat_id"] = str(kwargs.get("chat_id", ""))
        return context
