# Copyright NGGT.LightKeeper. All Rights Reserved.

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from typing import Any

from django.http import JsonResponse, StreamingHttpResponse
from django.views.generic import TemplateView

from API import llm_api, mcp as tool_registry
from Apps.Data.ollama_presets import (
    activate_ollama_preset,
    create_ollama_preset,
    delete_ollama_preset,
    get_ollama_preset_payload,
    rename_ollama_preset,
    sync_active_ollama_preset,
)
from Apps.Data.models import Chat, Message, MessageImage, OllamaPreset
from Settings import settings

logger = logging.getLogger(__name__)

THINK_PARAM_NAMES = {"think", "thinking", "reasoning"}
THINK_LEVEL_PARAM_NAMES = {"think_level", "thinking_level", "reasoning_effort"}
TOOL_CAPABILITY_NAMES = {"tools", "tool", "tool-calling", "tool_calling"}


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
        return []
    except Exception as exc:
        logger.warning("Failed to load models for engine %s: %s", engine, exc)
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
        "available_tool_servers": tool_registry.list_servers(),
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
def _build_chat_title(message: str, has_images: bool) -> str:
    """Generate a stable title for a new chat thread."""

    if message:
        return message[:30] + ("..." if len(message) > 30 else "")
    if has_images:
        return "Image chat"
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

    source = str(content or "")
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
            for key in ("name", "tool_name", "server_id", "server_name", "tool_id", "tool_display_name"):
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
        return [{"role": message.role, "content": message.content}]

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

        segments.append(
            {
                "type": "tool",
                "serverId": str(entry.get("server_id", "") or ""),
                "serverName": str(entry.get("server_name", "") or ""),
                "toolId": str(entry.get("tool_id", entry.get("name", "")) or ""),
                "toolName": str(entry.get("tool_display_name", entry.get("tool_name", entry.get("name", ""))) or ""),
                "arguments": entry.get("arguments") if isinstance(entry.get("arguments"), dict) else {},
            }
        )

    return segments


# Serialize message
def _serialize_message(message: Message) -> dict[str, Any]:
    """Convert a database message to the JSON shape expected by the frontend."""

    payload = {
        "role": message.role,
        "content": message.content,
        "created_at": message.created_at.isoformat(),
    }
    activity_segments = _build_activity_segments(message)
    if activity_segments:
        payload["activity_segments"] = activity_segments
    images = list(message.images.all())
    if images:
        payload["images"] = [image.data_url() for image in images]
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
    return str(thinking_part), str(text_part)


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
            key = parts[0].strip().lower()
            value = " ".join(parts[1:]).strip()
            defaults[key] = settings.normalize_setting_value(value)

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
            "supports_think_level": False,
            "think_param_name": "think",
            "think_level_param_name": "think_level",
            "supports_vision": False,
            "supports_tool_calling": False,
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
        "supports_think_level": bool(settings_data.get("supports_think_level", False)),
        "think_param_name": settings_data.get("think_param_name", "think"),
        "think_level_param_name": settings_data.get("think_level_param_name", "think_level"),
        "supports_vision": "vision" in normalized_capabilities or bool(settings_data.get("supports_vision", False)),
        "supports_tool_calling": bool(settings_data.get("supports_tool_calling", False)),
    }


# Build model info payload
def _build_model_info_payload(engine: str, model_name: str) -> dict[str, Any]:
    """Load adapter metadata and normalize it for the frontend."""

    settings_data = llm_api.get_model_settings(engine, model_name)
    if settings.is_ollama_engine(engine):
        payload = _extract_ollama_model_info(settings_data)
        preset_payload = get_ollama_preset_payload(model_name)
        payload["defaults"] = {**payload.get("defaults", {}), **preset_payload["active_config"]}
        payload["ollama_presets"] = preset_payload
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


# Resolve selected tool server
def _resolve_tool_server(engine: str, model_name: str, tool_server_id: str) -> dict[str, Any] | None:
    """Return the selected tool server when it is supported by the backend."""

    normalized_tool_server_id = str(tool_server_id or "").strip()
    if not normalized_tool_server_id:
        return None

    selected_tool_server = tool_registry.get_server(
        normalized_tool_server_id,
        engine=engine,
        model_name=model_name,
    )
    if selected_tool_server is None:
        raise ValueError(f"Unknown or unsupported tool server: {normalized_tool_server_id}")

    return selected_tool_server

# Resolve chat instance
def _resolve_chat(chat_id: str, user_message: str, images: list[str]) -> Chat:
    """Return an existing chat or create a new one for the request."""

    if not chat_id:
        return Chat.objects.create(title=_build_chat_title(user_message, bool(images)))

    try:
        return Chat.objects.get(id=chat_id)
    except Chat.DoesNotExist as exc:
        raise LookupError("Chat not found") from exc

# Save message images
def _store_message_images(user_message_record: Message, images: list[str]) -> None:
    """Persist uploaded images for the current user message."""

    for order, base64_data in enumerate(images):
        MessageImage.objects.create(
            message=user_message_record,
            data=base64_data,
            mime_type=_detect_image_mime(base64_data),
            order=order,
        )

# Build LLM message history
def _build_chat_history(
    chat: Chat,
    user_message_record: Message,
    user_message: str,
    system_prompt: str,
    images: list[str],
) -> list[dict[str, Any]]:
    """Build the message history sent to the selected backend."""

    llm_messages: list[dict[str, Any]] = []
    if system_prompt:
        llm_messages.append({"role": "system", "content": system_prompt})

    history_qs = chat.messages.exclude(id=user_message_record.id)
    for historical_message in history_qs:
        llm_messages.extend(_build_llm_history_entries(historical_message))

    current_entry: dict[str, Any] = {"role": "user", "content": user_message}
    if images:
        current_entry["images"] = images
    llm_messages.append(current_entry)

    return llm_messages

# Split generation options
def _split_generation_options(options: dict[str, Any]) -> tuple[Any, Any, dict[str, Any]]:
    """Split thinking controls from generic model options."""

    think_value = None
    think_level_value = None
    clean_options: dict[str, Any] = {}

    for key, value in options.items():
        if key in THINK_PARAM_NAMES:
            think_value = value
        elif key in THINK_LEVEL_PARAM_NAMES:
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
    selected_tool_server: dict[str, Any] | None,
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
    if clean_options:
        generate_kwargs["options"] = clean_options

    if settings.is_ollama_engine(engine) and selected_tool_server is not None:
        generate_kwargs["tool_server_id"] = selected_tool_server["id"]
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
    transcript_entries: list[dict[str, Any]] = []
    is_thinking = False

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
        logger.exception("Error during streaming generation")
        if is_thinking:
            yield "\n</think>\n"
        yield f"\n[Error during generation: {exc}]"
    finally:
        if is_thinking:
            yield "\n</think>\n"

        visible_content = "".join(visible_parts).strip()
        if visible_content or transcript_entries:
            Message.objects.create(
                chat=chat,
                role="assistant",
                content=visible_content,
                llm_transcript=transcript_entries,
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
        images = data.get("images", []) or []
        engine = _get_active_engine(data.get("engine"))
        tool_server_id = str(data.get("tool_server_id", data.get("tool_id", "")) or "").strip()

        if not model_name:
            return JsonResponse({"error": "Missing model parameter"}, status=400)
        if not user_message and not images:
            return JsonResponse({"error": "Missing message or images"}, status=400)

        # Resolve the tool server before persisting the message.
        selected_tool_server = _resolve_tool_server(engine, model_name, tool_server_id)

        # Reuse the existing chat when provided, otherwise create a new one.
        try:
            chat = _resolve_chat(chat_id, user_message, images)
        except LookupError as exc:
            return JsonResponse({"error": str(exc)}, status=404)

        normalized_tool_server_id = selected_tool_server["id"] if selected_tool_server else ""
        if chat.active_tool_slug != normalized_tool_server_id:
            chat.active_tool_slug = normalized_tool_server_id
            chat.save(update_fields=["active_tool_slug", "updated_at"])

        # Persist the incoming user message and its attachments.
        user_message_record = Message.objects.create(
            chat=chat,
            role="user",
            content=user_message,
        )
        _store_message_images(user_message_record, images)

        # Rebuild the message history expected by the selected backend.
        llm_messages = _build_chat_history(
            chat,
            user_message_record,
            user_message,
            system_prompt,
            images,
        )

        # Split generic options from thinking-specific controls.
        think_value, think_level_value, clean_options = _split_generation_options(options)

        # Build the final generation payload for the adapter layer.
        generate_kwargs = _build_generate_kwargs(
            engine,
            model_name,
            llm_messages,
            think_value,
            think_level_value,
            clean_options,
            chat,
            selected_tool_server,
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


# Load saved chat
def load_chat_api(request, chat_id):
    """Load persisted messages for a chat thread."""

    if request.method != "GET":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        chat = Chat.objects.get(id=chat_id)
        messages = chat.messages.all().prefetch_related("images")
        payload = [_serialize_message(message) for message in messages]
        return JsonResponse({
            "chat_id": str(chat.id),
            "title": chat.title,
            "messages": payload,
            "active_tool_id": chat.active_tool_slug,
            "active_tool_server_id": chat.active_tool_slug,
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

    try:
        return JsonResponse(_build_model_info_payload(engine, model_name))
    except NotImplementedError as exc:
        logger.info("Model info is not implemented for engine %s: %s", engine, exc)
        return JsonResponse({"error": str(exc)}, status=501)
    except Exception as exc:
        logger.exception("Error getting model info for %s on engine %s", model_name, engine)
        return JsonResponse({"error": str(exc)}, status=500)


# Load model list
def get_models_api(request):
    """Return model names for the requested engine."""

    if request.method != "GET":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    engine = _get_active_engine(request.GET.get("engine"))
    return JsonResponse({"engine": engine, "models": _load_models_for_engine(engine)})


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
