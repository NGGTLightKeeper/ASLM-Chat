"""UI views and JSON endpoints for ASLM-Chat."""

from __future__ import annotations

import json
import logging
from typing import Any

from django.http import JsonResponse, StreamingHttpResponse
from django.views.generic import TemplateView

from API import llm_api
from Apps.Data.models import Chat, Message, MessageImage
from Settings import settings

logger = logging.getLogger(__name__)

THINK_PARAM_NAMES = {"think", "thinking", "reasoning"}
THINK_LEVEL_PARAM_NAMES = {"think_level", "thinking_level", "reasoning_effort"}


def _get_active_engine(requested_engine: str | None = None) -> str:
    """Return the canonical engine identifier used for the current request."""
    return settings.normalize_engine_name(requested_engine or settings.get_llm_engine())


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


def _build_base_context() -> dict[str, Any]:
    """Build shared template context used by chat pages."""
    runtime_settings = settings.get_runtime_engine_settings()
    engine = _get_active_engine(runtime_settings.get("llm-engine"))
    return {
        "llm_engine": engine,
        "models": _load_models_for_engine(engine),
        "engine_options": settings.get_supported_engines(),
        "runtime_settings": runtime_settings,
        "chats": Chat.objects.all(),
    }


def _build_runtime_settings_payload() -> dict[str, Any]:
    """Return the settings payload used by the UI settings API."""
    runtime_settings = settings.get_runtime_engine_settings()
    active_engine = _get_active_engine(runtime_settings.get("llm-engine"))
    runtime_settings["llm-engine"] = active_engine
    runtime_settings["active_url"] = runtime_settings["engine_urls"].get(active_engine, "")
    runtime_settings["engine_options"] = settings.get_supported_engines()
    runtime_settings["models"] = _load_models_for_engine(active_engine)
    return runtime_settings


def _build_chat_title(message: str, has_images: bool) -> str:
    """Generate a stable title for a new chat thread."""
    if message:
        return message[:30] + ("..." if len(message) > 30 else "")
    if has_images:
        return "Image chat"
    return "New Chat"


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


def _serialize_message(message: Message) -> dict[str, Any]:
    """Convert a database message to the JSON shape expected by the frontend."""
    payload = {
        "role": message.role,
        "content": message.content,
        "created_at": message.created_at.isoformat(),
    }
    images = list(message.images.all())
    if images:
        payload["images"] = [image.data_url() for image in images]
    return payload


def _extract_ollama_model_info(settings_data: Any) -> dict[str, Any]:
    """Parse Ollama-specific model metadata into a frontend-friendly payload."""
    context_length = 8192
    defaults: dict[str, Any] = {}

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

    for key, value in modelinfo.items():
        if key.endswith(".context_length"):
            try:
                context_length = int(value)
            except (TypeError, ValueError):
                pass
            break

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

    supports_thinking = any(
        marker in template_str
        for marker in (".Think ", ".Think\n", ".ThinkLevel", ".Reasoning", ".Reason ")
    )
    supports_think_level = any(
        marker in template_str for marker in (".ThinkLevel", ".ReasoningEffort")
    )

    if "thinking" in capabilities:
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

    supports_vision = "vision" in capabilities

    return {
        "context_length": context_length,
        "defaults": defaults,
        "supports_thinking": supports_thinking,
        "supports_think_level": supports_think_level,
        "think_param_name": think_param_name,
        "think_level_param_name": think_level_param_name,
        "supports_vision": supports_vision,
    }


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
        }

    capabilities = settings_data.get("capabilities", []) or []
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
        "supports_vision": "vision" in capabilities or bool(settings_data.get("supports_vision", False)),
    }


def _build_model_info_payload(engine: str, model_name: str) -> dict[str, Any]:
    """Load adapter metadata and normalize it for the frontend."""
    settings_data = llm_api.get_model_settings(engine, model_name)
    if settings.is_ollama_engine(engine):
        payload = _extract_ollama_model_info(settings_data)
    else:
        payload = _extract_generic_model_info(settings_data)

    payload["model"] = model_name
    payload["engine"] = engine
    return payload


class MainView(TemplateView):
    """Main chat interface."""

    template_name = "main/main.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context.update(_build_base_context())
        return context


def chat_api(request):
    """Handle chat generation requests and stream assistant output."""
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON format"}, status=400)

    try:
        user_message = data.get("message", "")
        model_name = data.get("model", "")
        system_prompt = data.get("system_prompt", "")
        options = data.get("options", {}) or {}
        chat_id = data.get("chat_id", "")
        images = data.get("images", []) or []
        engine = _get_active_engine(data.get("engine"))

        if not model_name:
            return JsonResponse({"error": "Missing model parameter"}, status=400)
        if not user_message and not images:
            return JsonResponse({"error": "Missing message or images"}, status=400)

        if chat_id:
            try:
                chat = Chat.objects.get(id=chat_id)
            except Chat.DoesNotExist:
                return JsonResponse({"error": "Chat not found"}, status=404)
        else:
            chat = Chat.objects.create(title=_build_chat_title(user_message, bool(images)))

        user_message_record = Message.objects.create(
            chat=chat,
            role="user",
            content=user_message,
        )

        for order, base64_data in enumerate(images):
            MessageImage.objects.create(
                message=user_message_record,
                data=base64_data,
                mime_type=_detect_image_mime(base64_data),
                order=order,
            )

        llm_messages: list[dict[str, Any]] = []
        if system_prompt:
            llm_messages.append({"role": "system", "content": system_prompt})

        history_qs = chat.messages.exclude(id=user_message_record.id)
        for historical_message in history_qs:
            llm_messages.append(
                {
                    "role": historical_message.role,
                    "content": historical_message.content,
                }
            )

        current_entry: dict[str, Any] = {"role": "user", "content": user_message}
        if images:
            current_entry["images"] = images
        llm_messages.append(current_entry)

        think_value = None
        think_level_value = None
        clean_options = {}

        for key, value in options.items():
            if key in THINK_PARAM_NAMES:
                think_value = value
            elif key in THINK_LEVEL_PARAM_NAMES:
                think_level_value = value
            else:
                clean_options[key] = value

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

        def stream_response():
            full_response = ""
            is_thinking = False

            try:
                response_iterator = llm_api.generate(**generate_kwargs)
                for chunk in response_iterator:
                    raw_message = chunk.get("message", {}) if isinstance(chunk, dict) else getattr(chunk, "message", {})
                    if isinstance(raw_message, dict):
                        thinking_part = raw_message.get("thinking", "") or ""
                        text_part = raw_message.get("content", "") or ""
                    else:
                        thinking_part = getattr(raw_message, "thinking", "") or ""
                        text_part = getattr(raw_message, "content", "") or ""

                    if thinking_part:
                        if not is_thinking:
                            is_thinking = True
                            full_response += "<think>\n"
                            yield "<think>\n"
                        full_response += thinking_part
                        yield thinking_part

                    if text_part:
                        if is_thinking:
                            is_thinking = False
                            full_response += "\n</think>\n"
                            yield "\n</think>\n"
                        full_response += text_part
                        yield text_part
            except Exception as exc:
                logger.exception("Error during streaming generation")
                if is_thinking:
                    yield "\n</think>\n"
                yield f"\n[Error during generation: {exc}]"
            finally:
                if is_thinking:
                    full_response += "\n</think>\n"
                if full_response:
                    Message.objects.create(chat=chat, role="assistant", content=full_response)

        response = StreamingHttpResponse(stream_response(), content_type="text/plain; charset=utf-8")
        response["X-Chat-ID"] = str(chat.id)
        response["X-LLM-Engine"] = engine
        return response

    except Exception as exc:
        logger.exception("Unhandled exception in chat_api")
        return JsonResponse({"error": str(exc)}, status=500)


def load_chat_api(request, chat_id):
    """Load persisted messages for a chat thread."""
    if request.method != "GET":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        chat = Chat.objects.get(id=chat_id)
        messages = chat.messages.all().prefetch_related("images")
        payload = [_serialize_message(message) for message in messages]
        return JsonResponse({"chat_id": str(chat.id), "title": chat.title, "messages": payload})
    except Chat.DoesNotExist:
        return JsonResponse({"error": "Chat not found"}, status=404)
    except Exception as exc:
        logger.exception("Failed to load chat %s", chat_id)
        return JsonResponse({"error": str(exc)}, status=500)


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


def get_models_api(request):
    """Return model names for the requested engine."""
    if request.method != "GET":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    engine = _get_active_engine(request.GET.get("engine"))
    return JsonResponse({"engine": engine, "models": _load_models_for_engine(engine)})


def runtime_settings_api(request):
    """Read or update runtime engine settings used by the chat UI."""
    if request.method == "GET":
        return JsonResponse(_build_runtime_settings_payload())

    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON format"}, status=400)

    allowed_keys = {"llm-engine", "lms_url", "openai_url", "openai_api_key"}

    for raw_key, raw_value in data.items():
        if raw_key not in allowed_keys:
            continue

        if raw_key == "llm-engine":
            value = settings.normalize_engine_name(raw_value)
        else:
            value = str(raw_value or "").strip()

        settings.set(raw_key, value)

    return JsonResponse(_build_runtime_settings_payload())


class ProfileView(TemplateView):
    """Static account/profile page."""

    template_name = "main/profile.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context.update(_build_base_context())
        return context


class ChatView(TemplateView):
    """Chat permalink page that preloads a specific conversation."""

    template_name = "main/main.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context.update(_build_base_context())
        context["preload_chat_id"] = str(kwargs.get("chat_id", ""))
        return context
