# Copyright NGGT.LightKeeper. All Rights Reserved.

from __future__ import annotations

import base64
import binascii
import io
import json
import logging
import mimetypes
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from django.http import JsonResponse, StreamingHttpResponse
from django.views.generic import TemplateView

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
from Settings import settings

logger = logging.getLogger(__name__)

THINK_PARAM_NAMES = {"think", "thinking", "reasoning"}
THINK_LEVEL_PARAM_NAMES = {"think_level", "thinking_level", "reasoning_effort"}
TOOL_CAPABILITY_NAMES = {"tools", "tool", "tool-calling", "tool_calling"}
TEXT_ATTACHMENT_EXTENSIONS = {
    ".c", ".cc", ".cpp", ".cs", ".css", ".csv", ".go", ".h", ".hpp", ".html", ".ini",
    ".java", ".js", ".json", ".jsx", ".md", ".php", ".py", ".rb", ".rs", ".sh", ".sql",
    ".svg", ".toml", ".ts", ".tsx", ".txt", ".xml", ".yaml", ".yml",
}
ATTACHMENT_TEXT_CHAR_LIMIT = 24000
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


def _print_runtime_event(message: str) -> None:
    """Emit one concise runtime event for the ASLM console."""

    print(f"[ASLM-Chat] {message}", flush=True)


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

    if engine == "lms" and _is_expected_runtime_error(exc):
        return "Failed to connect to LM Studio."

    if engine == "lms":
        if "v cache quantization requires flash attention" in normalized_message:
            return (
                "The current LM Studio load settings are incompatible. "
                "Enable Flash Attention or set V Cache Quantization Type to f16."
            )
        if "model get/load error" in normalized_message or "failed to load model" in normalized_message:
            return "LM Studio could not load the selected model with the current load settings."

    return message


def _strip_llm_control_tokens(content: str) -> str:
    """Remove assistant-control tokens that should never be shown to the user."""

    cleaned = str(content or "")
    for pattern in LLM_CONTROL_TOKEN_PATTERNS:
        cleaned = pattern.sub("", cleaned)
    return cleaned


def _summarize_option_keys(options: dict[str, Any] | None, max_keys: int = 6) -> str:
    """Return a short, readable summary of option keys."""

    if not isinstance(options, dict) or not options:
        return "none"

    option_keys = sorted({str(key).strip() for key in options if str(key).strip()}, key=str.casefold)
    if len(option_keys) <= max_keys:
        return ", ".join(option_keys)
    return f"{', '.join(option_keys[:max_keys])}, +{len(option_keys) - max_keys} more"


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


def _guess_attachment_kind(mime_type: str, name: str = "") -> str:
    """Return the normalized attachment kind for the payload."""

    normalized_mime = str(mime_type or "").strip().lower()
    if normalized_mime.startswith("image/"):
        return MessageAttachmentKind.IMAGE

    guessed_mime, _encoding = mimetypes.guess_type(name or "")
    if guessed_mime and guessed_mime.startswith("image/"):
        return MessageAttachmentKind.IMAGE

    return MessageAttachmentKind.FILE


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

    file_bytes = _decode_base64_payload(encoded)
    if not file_bytes:
        return None

    if encoded.startswith("data:"):
        parsed_mime, parsed_data = _parse_data_url(encoded)
        if parsed_mime:
            mime_type = parsed_mime
        encoded = parsed_data

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
        "size_bytes": len(file_bytes),
        "order": order,
    }


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


def _serialize_attachment_record(attachment: Any) -> dict[str, Any]:
    """Convert a persisted attachment-like object into the frontend payload."""

    if isinstance(attachment, MessageAttachment):
        return {
            "kind": attachment.kind,
            "name": attachment.name,
            "mime_type": attachment.mime_type,
            "size_bytes": attachment.size_bytes,
            "order": attachment.order,
            "data_url": attachment.data_url(),
        }

    if isinstance(attachment, MessageImage):
        payload = {
            "kind": MessageAttachmentKind.IMAGE,
            "name": f"image-{attachment.order + 1}",
            "mime_type": attachment.mime_type,
            "size_bytes": len(_decode_base64_payload(attachment.data)),
            "order": attachment.order,
            "data_url": attachment.data_url(),
        }
        return payload

    return {}


def _get_message_attachments(message: Message) -> list[dict[str, Any]]:
    """Return all persisted attachments for a message in a shared shape."""

    attachments = [_serialize_attachment_record(item) for item in message.attachments.all()]
    legacy_images = [_serialize_attachment_record(item) for item in message.images.all()]
    combined = [item for item in attachments + legacy_images if item]
    combined.sort(key=lambda item: (int(item.get("order") or 0), item.get("name", "")))
    return combined


def _attachment_data_to_bytes(attachment: dict[str, Any]) -> bytes:
    """Decode one serialized attachment payload into bytes."""

    return _decode_base64_payload(attachment.get("data_url") or attachment.get("data"))


def _is_text_attachment(mime_type: str, name: str) -> bool:
    """Return whether the attachment should be decoded as text."""

    normalized_mime = str(mime_type or "").strip().lower()
    if normalized_mime.startswith("text/"):
        return True
    if normalized_mime in {
        "application/json",
        "application/javascript",
        "application/sql",
        "application/xml",
        "image/svg+xml",
    }:
        return True

    return Path(name or "").suffix.lower() in TEXT_ATTACHMENT_EXTENSIONS


def _truncate_attachment_text(text: str, limit: int = ATTACHMENT_TEXT_CHAR_LIMIT) -> str:
    """Trim attachment text so prompts stay bounded."""

    normalized = str(text or "").strip()
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit].rstrip()}\n...[truncated]"


def _extract_attachment_text(attachment: dict[str, Any]) -> str:
    """Extract prompt-friendly text from a file attachment when possible."""

    attachment_name = str(attachment.get("name") or "file").strip() or "file"
    mime_type = str(attachment.get("mime_type") or "application/octet-stream").strip()
    file_bytes = _attachment_data_to_bytes(attachment)
    if not file_bytes:
        return ""

    suffix = Path(attachment_name).suffix.lower()
    if mime_type == "application/pdf" or suffix == ".pdf":
        try:
            import fitz

            with fitz.open(stream=file_bytes, filetype="pdf") as document:
                pages = [page.get_text("text") for page in document]
            return _truncate_attachment_text("\n".join(pages))
        except Exception:
            return ""

    if _is_text_attachment(mime_type, attachment_name):
        for encoding in ("utf-8", "utf-8-sig", "cp1251", "latin-1"):
            try:
                return _truncate_attachment_text(file_bytes.decode(encoding))
            except UnicodeDecodeError:
                continue

    return ""


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

    return sorted(set(model_names), key=str.casefold)


# Build shared template context
def _build_base_context() -> dict[str, Any]:
    """Build shared template context used by chat pages."""

    runtime_settings = settings.get_runtime_engine_settings()
    engine = _get_active_engine(runtime_settings.get("llm-engine"))
    return {
        "llm_engine": engine,
        "models": [],
        "engine_options": settings.get_supported_engines(),
        "runtime_settings": runtime_settings,
        "available_tool_servers": tool_registry.list_servers(engine=engine),
        "chats": Chat.objects.all(),
    }


# Build runtime settings payload
def _build_runtime_settings_payload() -> dict[str, Any]:
    """Return the settings payload used by the UI settings API."""

    runtime_settings = settings.get_runtime_engine_settings()
    active_engine = _get_active_engine(runtime_settings.get("llm-engine"))
    runtime_settings["llm-engine"] = active_engine
    runtime_settings["active_url"] = runtime_settings["engine_urls"].get(active_engine, "")
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
        entries.append(entry)

    return entries


# Build LLM history entries
def _build_llm_history_entries(message: Message) -> list[dict[str, Any]]:
    """Convert one stored message into the message list expected by the LLM backend."""

    if message.role != "assistant":
        payload = {"role": message.role, "content": message.content}
        return [_apply_attachments_to_llm_entry(payload, _get_message_attachments(message))]

    transcript_entries = _normalize_transcript_entries(message.llm_transcript)
    if transcript_entries:
        llm_entries: list[dict[str, Any]] = []
        for entry in transcript_entries:
            payload = {
                "role": entry["role"],
                "content": entry.get("content", ""),
            }
            if entry["role"] == "assistant":
                if entry.get("thinking"):
                    payload["thinking"] = entry["thinking"]
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


# Build activity segments
def _build_activity_segments(message: Message) -> list[dict[str, Any]]:
    """Build frontend activity segments from the stored machine transcript."""

    transcript_entries = _normalize_transcript_entries(message.llm_transcript)
    if not transcript_entries:
        return []

    # Index tool results by alias for quick lookup (alias = server__tool_id).
    tool_results: dict[str, str] = {}
    for entry in transcript_entries:
        if entry.get("role") == "tool":
            # Prefer the full alias stored by _build_tool_message, fall back to tool_id/name.
            alias = str(entry.get("alias") or entry.get("tool_id") or entry.get("name") or "")
            if alias:
                tool_results[alias] = str(entry.get("content") or "")

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
        segments.append(
            {
                "type": "tool",
                "alias": seg_alias,
                "serverId": str(entry.get("server_id", "") or ""),
                "serverName": str(entry.get("server_name", "") or ""),
                "toolId": str(entry.get("tool_id", entry.get("name", "")) or ""),
                "toolName": str(entry.get("tool_display_name", entry.get("tool_name", entry.get("name", ""))) or ""),
                "arguments": entry.get("arguments") if isinstance(entry.get("arguments"), dict) else {},
                "result": tool_results.get(seg_alias, None),
            }
        )

    return segments


# Serialize message
def _serialize_message(message: Message) -> dict[str, Any]:
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
    attachments = _get_message_attachments(message)
    if attachments:
        payload["attachments"] = attachments
        payload["images"] = [item["data_url"] for item in attachments if item.get("kind") == MessageAttachmentKind.IMAGE]
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
def _serialize_tool_result_marker(alias: str, content: str) -> str:
    """Encode a tool result into an inline marker so the frontend can show _out_."""

    payload = {"alias": alias, "content": content}
    return f'<tool_result>{json.dumps(payload, ensure_ascii=False)}</tool_result>'


# Extract Ollama model info
def _extract_ollama_model_info(settings_data: Any) -> dict[str, Any]:
    """Parse Ollama-specific model metadata into a frontend-friendly payload."""

    context_length = 8192
    model_layers = 0
    defaults: dict[str, Any] = {}

    # Read raw metadata from dict-like or SDK responses.
    if isinstance(settings_data, dict):
        modelinfo = settings_data.get("modelinfo", {}) or {}
        parameters_str = settings_data.get("parameters", "") or ""
        template_str = settings_data.get("template", "") or ""
        capabilities = settings_data.get("capabilities", []) or []
    else:
        modelinfo = getattr(settings_data, "modelinfo", {}) or {}
        parameters_str = getattr(settings_data, "parameters", "") or ""
        template_str = getattr(settings_data, "template", "") or ""
        capabilities = getattr(settings_data, "capabilities", []) or []

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
    normalized_capabilities = {str(item).strip().lower() for item in capabilities}

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
    supports_tool_calling = bool(normalized_capabilities & TOOL_CAPABILITY_NAMES)

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
            "load_defaults": {},
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
        "load_defaults": settings_data.get("load_defaults", {}) if isinstance(settings_data.get("load_defaults", {}), dict) else {},
        "supports_thinking": bool(settings_data.get("supports_thinking", False)),
        "supports_think_toggle": bool(settings_data.get("supports_think_toggle", settings_data.get("supports_thinking", False))),
        "supports_think_level": bool(settings_data.get("supports_think_level", False)),
        "think_param_name": settings_data.get("think_param_name", "think"),
        "think_level_param_name": settings_data.get("think_level_param_name", "think_level"),
        "think_level_options": settings_data.get("think_level_options", []) if isinstance(settings_data.get("think_level_options", []), list) else [],
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
    return payload


def _build_model_info_payload(
    engine: str,
    model_name: str,
    *,
    allow_fallback: bool = False,
) -> dict[str, Any]:
    """Load adapter metadata and normalize it for the frontend."""

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
            payload["load_defaults"] = {
                **payload.get("load_defaults", {}),
                **(active_config.get("load", {}) if isinstance(active_config.get("load", {}), dict) else {}),
            }
            payload["defaults"] = {
                **payload.get("defaults", {}),
                **(active_config.get("operation", {}) if isinstance(active_config.get("operation", {}), dict) else {}),
            }
        payload["lms_presets"] = preset_payload
    else:
        payload = _extract_generic_model_info(settings_data)

    payload["available_tool_servers"] = (
        tool_registry.list_servers(engine, model_name) if payload.get("supports_tool_calling") else []
    )
    payload["model"] = model_name
    payload["engine"] = engine
    return payload


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


def _validate_tool_server_support(
    engine: str,
    model_name: str,
    tool_server_ids: list[str],
    payload: dict[str, Any] | None = None,
) -> None:
    """Raise when tools are requested for a model that should not call tools."""

    if not tool_server_ids or engine != "lms":
        return

    payload = payload or _build_model_info_payload(engine, model_name)
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

# Build LLM message history
def _build_chat_history(
    chat: Chat,
    user_message_record: Message,
    user_message: str,
    system_prompt: str,
    attachments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build the message history sent to the selected backend."""

    llm_messages: list[dict[str, Any]] = []
    if system_prompt:
        llm_messages.append({"role": "system", "content": system_prompt})

    history_qs = chat.messages.exclude(id=user_message_record.id).prefetch_related("attachments", "images")
    for historical_message in history_qs:
        llm_messages.extend(_build_llm_history_entries(historical_message))

    current_entry: dict[str, Any] = {"role": "user", "content": user_message}
    llm_messages.append(_apply_attachments_to_llm_entry(current_entry, attachments))

    return llm_messages

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
    load_config: dict[str, Any] | None = None,
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
    if engine == "lms" and think_param_name:
        generate_kwargs["think_param_name"] = think_param_name
    if engine == "lms" and think_level_param_name:
        generate_kwargs["think_level_param_name"] = think_level_param_name
    if clean_options:
        generate_kwargs["options"] = clean_options
    if engine == "lms" and isinstance(load_config, dict) and load_config:
        generate_kwargs["load_config"] = load_config
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
        }

    return generate_kwargs

# Stream and save assistant response
def _stream_chat_response(chat: Chat, engine: str, generate_kwargs: dict[str, Any]):
    """Stream visible content and persist the machine transcript."""

    visible_parts: list[str] = []
    thinking_parts: list[str] = []
    transcript_entries: list[dict[str, Any]] = []
    is_thinking = False
    failed = False
    started_at = time.perf_counter()
    model_name = str(generate_kwargs.get("model_name", "") or "")
    llm_messages = generate_kwargs.get("messages", [])
    image_count = _count_request_images(llm_messages if isinstance(llm_messages, list) else [])
    selected_tool_server_ids = generate_kwargs.get("tool_server_ids", []) or []
    raw_options = generate_kwargs.get("options", {})
    raw_think_value = generate_kwargs.get("think")
    emit_thinking = raw_think_value is not False and str(raw_think_value).strip().lower() not in {"false", "0", "off", "no"}

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
        llm_api.prepare_runtime(engine)
        response_iterator = llm_api.generate(**generate_kwargs)
        for chunk in response_iterator:
            # Save assistant/tool transcript entries that are not meant
            # to be rendered directly as plain chat text.
            if isinstance(chunk, dict) and chunk.get("transcript_message"):
                transcript_message = chunk["transcript_message"]
                if isinstance(transcript_message, dict):
                    transcript_entries.append(transcript_message)
                continue

            if isinstance(chunk, dict) and chunk.get("tool_result"):
                tool_message = chunk["tool_result"]
                if isinstance(tool_message, dict):
                    transcript_entries.append(tool_message)
                    alias = str(tool_message.get("alias") or tool_message.get("tool_id") or tool_message.get("name") or "")
                    content = str(tool_message.get("content") or "")
                    yield _serialize_tool_result_marker(alias, content)
                continue

            # Tool events are sent as inline markers for the frontend.
            if isinstance(chunk, dict) and chunk.get("tool_event"):
                if is_thinking:
                    is_thinking = False
                    yield "\n</think>\n"
                yield _serialize_tool_call_marker(chunk["tool_event"])
                continue

            thinking_part, text_part = _extract_stream_message_parts(chunk)

            # Thinking fragments are wrapped in custom tags.
            if thinking_part:
                if emit_thinking:
                    thinking_parts.append(thinking_part)
                    if not is_thinking:
                        is_thinking = True
                        yield "<think>\n"
                    yield thinking_part

            # Visible text is streamed and stored separately.
            if text_part:
                if is_thinking:
                    is_thinking = False
                    yield "\n</think>\n"
                visible_parts.append(text_part)
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
        if is_thinking:
            yield "\n</think>\n"

        visible_content = _strip_llm_control_tokens("".join(visible_parts)).strip()
        thinking_content = _strip_llm_control_tokens("".join(thinking_parts)).strip()
        if not transcript_entries and (visible_content or thinking_content):
            synthesized_entry: dict[str, Any] = {"role": "assistant", "content": visible_content}
            if thinking_content:
                synthesized_entry["thinking"] = thinking_content
            transcript_entries.append(synthesized_entry)
        if visible_content or transcript_entries:
            Message.objects.create(
                chat=chat,
                role="assistant",
                content=visible_content,
                llm_transcript=transcript_entries,
            )

        duration_seconds = time.perf_counter() - started_at
        _print_runtime_event(
            "Chat completed: "
            f"engine={engine}, "
            f"model={model_name}, "
            f"status={'failed' if failed else 'ok'}, "
            f"took={duration_seconds:.2f}s, "
            f"visible_chars={len(visible_content)}, "
            f"transcript_entries={len(transcript_entries)}"
        )


# Render main page
class MainView(TemplateView):
    template_name = "main/main.html"

    # Build main page context
    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """Return template context for the main chat page."""

        context = super().get_context_data(**kwargs)
        context.update(_build_base_context())
        return context


# Handle chat request
def chat_api(request):
    """Handle chat generation requests and stream assistant output."""

    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        data = _read_json_request_body(request)

        # Read request payload and validate required inputs.
        user_message = data.get("message", "")
        model_name = data.get("model", "")
        system_prompt = data.get("system_prompt", "")
        options = data.get("options", {}) or {}
        chat_id = data.get("chat_id", "")
        attachments = _normalize_request_attachments(data)
        engine = _get_active_engine(data.get("engine"))
        raw_tool_ids = data.get("tool_server_ids") or data.get("tool_server_id") or data.get("tool_id") or []
        if isinstance(raw_tool_ids, str):
            raw_tool_ids = [raw_tool_ids] if raw_tool_ids.strip() else []
        tool_server_ids = [str(s).strip() for s in raw_tool_ids if str(s).strip()]

        if not model_name:
            return JsonResponse({"error": "Missing model parameter"}, status=400)
        if not user_message and not attachments:
            return JsonResponse({"error": "Missing message or attachments"}, status=400)

        if engine == "lms":
            model_info_payload = _build_model_info_payload(engine, model_name, allow_fallback=True)
        else:
            model_info_payload = _build_fallback_model_info_payload(engine, model_name)
        _validate_tool_server_support(engine, model_name, tool_server_ids, payload=model_info_payload)
        selected_tool_servers = _resolve_tool_servers(engine, model_name, tool_server_ids)

        # Reuse the existing chat when provided, otherwise create a new one.
        try:
            chat = _resolve_chat(chat_id, user_message, attachments)
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
        )
        _store_message_attachments(user_message_record, attachments)

        # Rebuild the message history expected by the selected backend.
        llm_messages = _build_chat_history(
            chat,
            user_message_record,
            user_message,
            system_prompt,
            attachments,
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
            load_config=(
                (
                    model_info_payload.get("lms_presets", {}).get("active_config", {}).get("load", {})
                    if isinstance(model_info_payload.get("lms_presets"), dict)
                    else model_info_payload.get("load_defaults", {})
                )
                if engine == "lms"
                else {}
            ),
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

        response = StreamingHttpResponse(
            _stream_chat_response(chat, engine, generate_kwargs),
            content_type="text/plain; charset=utf-8",
        )
        response["X-Chat-ID"] = str(chat.id)
        response["X-LLM-Engine"] = engine
        return response

    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except Exception as exc:
        logger.exception("Unhandled exception in chat_api")
        return JsonResponse({"error": str(exc)}, status=500)


# Abort active generation
def abort_generation_api(request):
    """Immediately signal the active LLM generation to stop."""

    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        ollama_api.abort_generation()
        return JsonResponse({"ok": True})
    except Exception as exc:
        logger.exception("Failed to abort generation")
        return JsonResponse({"error": str(exc)}, status=500)


# Delete a specific message by ID
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


# Load saved chat
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


def load_chat_api(request, chat_id):
    """Load persisted messages for a chat thread."""

    if request.method != "GET":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        chat = Chat.objects.get(id=chat_id)
        messages = chat.messages.all().prefetch_related("attachments", "images")
        payload = [_serialize_message(message) for message in messages]
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


# Load model info
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


# Load model list
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


# Load tool servers
def get_tools_api(request):
    """Return locally discovered MCP-style tool servers for the requested engine/model."""

    if request.method != "GET":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    engine = _get_active_engine(request.GET.get("engine"))
    model_name = str(request.GET.get("model", "") or "").strip() or None
    servers = tool_registry.list_servers(engine, model_name)
    return JsonResponse({"tool_servers": servers, "servers": servers, "tools": servers})


# Load Ollama presets
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


# Sync active preset
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
        return JsonResponse(sync_active_ollama_preset(model_name, config))
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except Exception as exc:
        logger.exception("Error syncing Ollama preset")
        return JsonResponse({"error": str(exc)}, status=500)


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
        return JsonResponse(sync_active_lms_preset(model_name, config))
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except Exception as exc:
        logger.exception("Error syncing LM Studio preset")
        return JsonResponse({"error": str(exc)}, status=500)


# Select active preset
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
        return JsonResponse(activate_ollama_preset(model_name, preset_id))
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except OllamaPreset.DoesNotExist as exc:
        return JsonResponse({"error": str(exc)}, status=404)
    except Exception as exc:
        logger.exception("Error selecting Ollama preset")
        return JsonResponse({"error": str(exc)}, status=500)


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
        return JsonResponse(activate_lms_preset(model_name, preset_id))
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except LmsPreset.DoesNotExist as exc:
        return JsonResponse({"error": str(exc)}, status=404)
    except Exception as exc:
        logger.exception("Error selecting LM Studio preset")
        return JsonResponse({"error": str(exc)}, status=500)


# Create preset
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
        return JsonResponse(
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
        return JsonResponse(
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


# Rename preset
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
        return JsonResponse(rename_ollama_preset(model_name, preset_id, preset_name))
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except OllamaPreset.DoesNotExist as exc:
        return JsonResponse({"error": str(exc)}, status=404)
    except Exception as exc:
        logger.exception("Error renaming Ollama preset")
        return JsonResponse({"error": str(exc)}, status=500)


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
        return JsonResponse(rename_lms_preset(model_name, preset_id, preset_name))
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except LmsPreset.DoesNotExist as exc:
        return JsonResponse({"error": str(exc)}, status=404)
    except Exception as exc:
        logger.exception("Error renaming LM Studio preset")
        return JsonResponse({"error": str(exc)}, status=500)


# Delete preset
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
        return JsonResponse(delete_ollama_preset(model_name, preset_id))
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except OllamaPreset.DoesNotExist as exc:
        return JsonResponse({"error": str(exc)}, status=404)
    except Exception as exc:
        logger.exception("Error deleting Ollama preset")
        return JsonResponse({"error": str(exc)}, status=500)


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
        return JsonResponse(delete_lms_preset(model_name, preset_id))
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except LmsPreset.DoesNotExist as exc:
        return JsonResponse({"error": str(exc)}, status=404)
    except Exception as exc:
        logger.exception("Error deleting LM Studio preset")
        return JsonResponse({"error": str(exc)}, status=500)


# Reload selected model
def reload_model_api(request):
    """Reload the selected model when the active engine supports explicit reload."""

    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        data = _read_json_request_body(request)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    model_name = str(data.get("model", "") or "").strip()
    engine = _get_active_engine(data.get("engine"))
    if not model_name:
        return JsonResponse({"error": "Model parameter is required"}, status=400)

    try:
        llm_api.reload_model(engine, model_name)
    except NotImplementedError as exc:
        logger.info("Model reload is not implemented for engine %s: %s", engine, exc)
        return JsonResponse({"error": str(exc)}, status=501)
    except Exception as exc:
        logger.exception("Error reloading model %s on engine %s", model_name, engine)
        return JsonResponse({"error": str(exc)}, status=500)

    return JsonResponse({"engine": engine, "model": model_name, "reloaded": True})


# Read or update runtime settings
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

    allowed_keys = {"llm-engine", "lms_url", "lms_load_config", "openai_url", "openai_api_key"}

    previous_engine = settings.get_llm_engine()
    next_engine = previous_engine

    # Persist only known settings and normalize engine-specific values.
    for raw_key, raw_value in data.items():
        if raw_key not in allowed_keys:
            continue

        if raw_key == "llm-engine":
            value = settings.normalize_engine_name(raw_value)
            next_engine = value
        elif raw_key == "lms_load_config":
            value = raw_value if isinstance(raw_value, dict) else {}
        else:
            value = str(raw_value or "").strip()

        settings.set(raw_key, value)

    # Apply runtime transitions after the new settings are saved.
    llm_api.handle_engine_transition(previous_engine, next_engine)

    return JsonResponse(_build_runtime_settings_payload())


# Render profile page
class ProfileView(TemplateView):
    template_name = "main/profile.html"

    # Build profile page context
    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """Return template context for the profile page."""

        context = super().get_context_data(**kwargs)
        context.update(_build_base_context())
        return context


# Render preloaded chat page
class ChatView(TemplateView):
    template_name = "main/main.html"

    # Build chat page context
    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """Return template context for a preloaded chat page."""

        context = super().get_context_data(**kwargs)
        context.update(_build_base_context())
        context["preload_chat_id"] = str(kwargs.get("chat_id", ""))
        return context
