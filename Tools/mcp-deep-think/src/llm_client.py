# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

import asyncio
import ast
import json
import logging
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from .config import settings
from .tracer import tracer

logger = logging.getLogger(__name__)

CURRENT_LLM_ENGINE = ContextVar("deep_think_llm_engine", default=None)
CURRENT_LLM_MODEL = ContextVar("deep_think_llm_model", default=None)


# JSON parsing helpers

# Extract the first valid JSON object from a model response
def _extract_json(content: str) -> dict:
    """Extract a JSON object from a model response using several fallbacks."""

    import re

    content = content.strip().lstrip("\ufeff")

    def _try_parse(text: str) -> dict | None:
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            try:
                parsed = ast.literal_eval(text)
            except (ValueError, SyntaxError):
                return None
            return parsed if isinstance(parsed, dict) else None

    # Try a direct parse first.
    result = _try_parse(content)
    if result is not None:
        return result

    # Then try fenced Markdown payloads.
    for pattern in (r"```json\s*(.*?)```", r"```\s*(.*?)```"):
        match = re.search(pattern, content, re.DOTALL)
        if match:
            result = _try_parse(match.group(1).strip())
            if result is not None:
                return result

    # Finally extract the first balanced object-shaped block.
    start = content.find("{")
    if start != -1:
        depth = 0
        for index, char in enumerate(content[start:], start):
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    candidate = content[start : index + 1]
                    result = _try_parse(candidate)
                    if result is not None:
                        return result

                    # Escape control characters inside quoted strings and try again.
                    sanitized = re.sub(
                        r'("(?:[^"\\]|\\.)*")',
                        lambda match: match.group(0)
                        .replace("\n", "\\n")
                        .replace("\r", "\\r")
                        .replace("\t", "\\t"),
                        candidate,
                    )
                    result = _try_parse(sanitized)
                    if result is not None:
                        return result
                    break

    raise json.JSONDecodeError("Could not extract valid JSON from LLM response", content, 0)


# Retry classification

# Decide whether a request failure should be retried
def _is_retryable_exception(exc: BaseException) -> bool:
    """Return whether an HTTP or transport failure is worth retrying."""

    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status in {408, 409, 425, 429} or status >= 500

    return isinstance(exc, (httpx.ConnectError, httpx.ReadTimeout))


# Async LLM client

# Wrap LM Studio requests with concurrency limits and retries
class LLMClient:
    """Async LM Studio client with retry and concurrency control."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        max_concurrent: Optional[int] = None,
        timeout: Optional[float] = None,
    ):
        """Initialize the client with settings defaults when values are omitted."""

        self.base_url = base_url or settings.lm_studio_url
        self.max_concurrent = max_concurrent or settings.max_concurrent_llm_requests
        self.timeout = timeout or settings.llm_timeout_seconds

        self._semaphore = asyncio.Semaphore(self.max_concurrent)
        self._client: Optional[httpx.AsyncClient] = None
        self._resolved_models: dict[str, str] = {}


    # HTTP client lifecycle
    def _runtime_engine(self) -> str:
        """Return the current engine, preferring ASLM runtime context when available."""

        contextual = CURRENT_LLM_ENGINE.get()
        if contextual:
            return str(contextual)

        try:
            from Settings import settings as aslm_settings

            return aslm_settings.get_llm_engine()
        except Exception:
            return "lms"

    def _runtime_model(self) -> str:
        """Return the current model override from ASLM runtime context when available."""

        contextual = CURRENT_LLM_MODEL.get()
        return str(contextual or "").strip()

    def _engine_base_url(self, engine: str) -> str:
        """Resolve the chat completions endpoint for OpenAI-compatible engines."""

        normalized_engine = str(engine or "").strip().lower()
        if normalized_engine == "ollama-service":
            return self.base_url

        try:
            from Settings import settings as aslm_settings

            if normalized_engine == "openai":
                endpoint = aslm_settings.get_engine_url("openai")
            elif normalized_engine == "lms":
                endpoint = aslm_settings.get_engine_url("lms")
            else:
                endpoint = ""
        except Exception:
            endpoint = ""

        raw_base = str(endpoint or self.base_url).strip().rstrip("/")
        if not raw_base:
            return self.base_url

        if "://" not in raw_base:
            raw_base = f"http://{raw_base}"

        if raw_base.endswith("/chat/completions"):
            return raw_base
        if raw_base.endswith("/v1"):
            return f"{raw_base}/chat/completions"
        if raw_base.endswith("/v1/"):
            return f"{raw_base}chat/completions"
        return f"{raw_base}/v1/chat/completions"

    def _models_url(self) -> str:
        """Convert the chat completions URL into the matching models URL."""

        parts = urlsplit(self._engine_base_url(self._runtime_engine()))
        path = parts.path.rstrip("/")
        if path.endswith("/chat/completions"):
            path = path[: -len("/chat/completions")] + "/models"
        else:
            path = path.rsplit("/", 1)[0] + "/models"
        return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))

    async def _get_client(self) -> httpx.AsyncClient:
        """Create the shared async HTTP client on first use."""

        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=10.0,
                    read=self.timeout,
                    write=30.0,
                    pool=10.0,
                )
            )

        return self._client

    async def close(self):
        """Close the shared HTTP client."""

        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    @contextmanager
    def runtime_target(self, engine: str | None = None, model_name: str | None = None):
        """Temporarily bind Deep Think requests to a specific ASLM engine/model."""

        engine_token = CURRENT_LLM_ENGINE.set(str(engine).strip() if engine else None)
        model_token = CURRENT_LLM_MODEL.set(str(model_name).strip() if model_name else None)
        try:
            yield
        finally:
            CURRENT_LLM_ENGINE.reset(engine_token)
            CURRENT_LLM_MODEL.reset(model_token)


    # Prompt shaping
    def _prepare_json_messages(self, messages: list[dict]) -> list[dict]:
        """Clone messages and add a strict machine-readable JSON reminder."""

        prepared = [{**message} for message in messages]
        reminder = (
            "Return exactly one valid JSON object. "
            "Do not use markdown fences, commentary, or prose before or after the JSON."
        )

        if prepared and prepared[-1]["role"] == "user":
            last_content = str(prepared[-1].get("content", ""))
            lowered = last_content.lower()
            if "json" not in lowered or "valid json object" not in lowered:
                prepared[-1]["content"] = f"{last_content}\n\n{reminder}".strip()
        else:
            prepared.append({"role": "user", "content": reminder})

        return prepared

    async def _repair_json_response(
        self,
        invalid_content: str,
        temperature: float,
        max_tokens: int,
    ) -> dict:
        """Ask the model to convert its previous answer into strict JSON only."""

        repair_messages = [
            {
                "role": "system",
                "content": (
                    "You repair model outputs into strict JSON. "
                    "Return exactly one valid JSON object and preserve the original meaning. "
                    "Do not add markdown or explanations."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Convert the following content into a valid JSON object only.\n\n"
                    f"{invalid_content}"
                ),
            },
        ]

        # Try native JSON mode first, then fall back to plain text extraction.
        for json_mode in (True, False):
            content = await self.chat_completion(
                messages=repair_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                json_mode=json_mode,
            )
            try:
                return _extract_json(content)
            except json.JSONDecodeError:
                continue

        raise json.JSONDecodeError("Could not repair invalid JSON response", invalid_content, 0)


    # Model resolution
    async def _resolve_model(self, force_refresh: bool = False) -> str:
        """Resolve the configured model id or query LM Studio for an active model."""

        runtime_engine = self._runtime_engine()
        runtime_model = self._runtime_model()
        if runtime_model:
            return runtime_model

        configured = (settings.lm_studio_model or "").strip()
        if configured and configured.lower() not in {"local-model", "auto"} and not force_refresh:
            return configured

        if runtime_engine == "ollama-service":
            return await self._resolve_ollama_model(force_refresh=force_refresh)

        cached_model = self._resolved_models.get(runtime_engine)
        if cached_model and not force_refresh:
            return cached_model

        client = await self._get_client()
        response = await client.get(self._models_url())
        response.raise_for_status()

        data = response.json()
        models = data.get("data") or []
        if not models:
            raise RuntimeError("LM Studio API reports that no models are loaded.")

        model_id = models[0].get("id")
        if not model_id:
            raise RuntimeError("LM Studio API returned a model entry without an id.")

        self._resolved_models[runtime_engine] = model_id
        return model_id

    async def _resolve_ollama_model(self, force_refresh: bool = False) -> str:
        """Resolve the active Ollama model from ASLM when no explicit model was provided."""

        cached_model = self._resolved_models.get("ollama-service")
        if cached_model and not force_refresh:
            return cached_model

        from API import ollama as ollama_api

        def _extract_model_name(entry: object) -> str:
            if isinstance(entry, dict):
                for key in ("model", "name", "id"):
                    value = entry.get(key)
                    if value:
                        return str(value)
                return ""

            for attr in ("model", "name", "id"):
                value = getattr(entry, attr, None)
                if value:
                    return str(value)
            return ""

        await asyncio.to_thread(ollama_api.prepare_runtime)
        models = await asyncio.to_thread(ollama_api.get_models)
        if not models:
            raise RuntimeError("ASLM Ollama service reports that no models are available.")

        for model_entry in models:
            model_name = _extract_model_name(model_entry)
            if model_name:
                self._resolved_models["ollama-service"] = model_name
                return model_name

        raise RuntimeError("ASLM Ollama service returned models without identifiers.")


    # Request execution
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception(_is_retryable_exception),
        reraise=True,
    )
    async def _make_request(self, payload: dict) -> dict:
        """Send a single chat completion request with retry support."""

        client = await self._get_client()
        response = await client.post(self._engine_base_url(self._runtime_engine()), json=payload)
        if response.status_code == 400:
            self._resolved_models.pop(self._runtime_engine(), None)
        response.raise_for_status()
        return response.json()

    async def chat_completion(
        self,
        messages: list[dict],
        temperature: float = 0.5,
        max_tokens: int = 1200,
        stop_sequences: Optional[list[str]] = None,
        json_mode: bool = False,
    ) -> str:
        """Request a chat completion and return the assistant content."""

        runtime_engine = self._runtime_engine()
        model_name = await self._resolve_model()
        if runtime_engine == "ollama-service":
            return await self._chat_completion_ollama(
                model_name=model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stop_sequences=stop_sequences,
                json_mode=json_mode,
            )

        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if stop_sequences:
            payload["stop"] = stop_sequences

        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        async with self._semaphore:
            logger.debug(
                "LLM request: model=%s, temp=%s, max_tokens=%s",
                model_name,
                temperature,
                max_tokens,
            )

            # Mirror requests into the tracer for postmortem debugging.
            tracer.log(
                "llm_client",
                "llm_request",
                {
                    "model": model_name,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stop": stop_sequences,
                },
            )

            try:
                result = await self._make_request(payload)
                content = result["choices"][0]["message"]["content"]
                logger.debug("LLM response received, length=%s", len(content))

                tracer.log(
                    "llm_client",
                    "llm_response",
                    {
                        "content": content,
                        "finish_reason": result["choices"][0].get("finish_reason"),
                        "usage": result.get("usage"),
                    },
                )
                return content
            except Exception as exc:
                logger.error("LLM request failed: %s", exc)
                tracer.log("llm_client", "error", f"Request failed: {exc}")
                raise

    async def _chat_completion_ollama(
        self,
        model_name: str,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        stop_sequences: Optional[list[str]] = None,
        json_mode: bool = False,
    ) -> str:
        """Run one non-streaming chat completion through ASLM's Ollama adapter."""

        from API import ollama as ollama_api

        options: dict[str, object] = {
            "temperature": temperature,
            "num_predict": max_tokens,
        }
        if stop_sequences:
            options["stop"] = stop_sequences

        request_kwargs: dict[str, object] = {
            "stream": False,
            "options": options,
        }
        if json_mode:
            request_kwargs["format"] = "json"

        async with self._semaphore:
            logger.debug(
                "LLM request (ollama): model=%s, temp=%s, max_tokens=%s",
                model_name,
                temperature,
                max_tokens,
            )
            tracer.log(
                "llm_client",
                "llm_request",
                {
                    "engine": "ollama-service",
                    "model": model_name,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stop": stop_sequences,
                    "json_mode": json_mode,
                },
            )

            try:
                await asyncio.to_thread(ollama_api.prepare_runtime)
                result = await asyncio.to_thread(
                    ollama_api.generate,
                    model_name,
                    messages,
                    **request_kwargs,
                )

                if isinstance(result, dict):
                    message = result.get("message") or {}
                    content = str(message.get("content", "") or "")
                    done_reason = result.get("done_reason")
                else:
                    raw_message = getattr(result, "message", None)
                    content = str(getattr(raw_message, "content", "") or "")
                    done_reason = getattr(result, "done_reason", None)

                tracer.log(
                    "llm_client",
                    "llm_response",
                    {
                        "engine": "ollama-service",
                        "content": content,
                        "finish_reason": done_reason,
                    },
                )
                return content
            except Exception as exc:
                logger.error("LLM request (ollama) failed: %s", exc)
                tracer.log("llm_client", "error", f"Ollama request failed: {exc}")
                raise


    # JSON completions
    async def chat_completion_json(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 1200,
    ) -> dict:
        """Request a JSON-shaped response and parse it robustly."""

        prepared_messages = self._prepare_json_messages(messages)
        last_error: Exception | None = None
        invalid_content: str | None = None

        for json_mode in (True, False):
            try:
                content = await self.chat_completion(
                    messages=prepared_messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    json_mode=json_mode,
                )
                try:
                    parsed = _extract_json(content)
                    tracer.log(
                        "llm_client",
                        "json_parse_success",
                        {"json_mode": json_mode},
                    )
                    return parsed
                except json.JSONDecodeError as exc:
                    invalid_content = content
                    last_error = exc
                    tracer.log(
                        "llm_client",
                        "json_parse_retry",
                        {
                            "json_mode": json_mode,
                            "error": str(exc),
                            "content_preview": content[:1200],
                        },
                    )
            except Exception as exc:
                last_error = exc
                tracer.log(
                    "llm_client",
                    "json_request_retry",
                    {
                        "json_mode": json_mode,
                        "error": str(exc),
                    },
                )

        if invalid_content:
            try:
                repaired = await self._repair_json_response(
                    invalid_content=invalid_content,
                    temperature=min(temperature, 0.2),
                    max_tokens=max_tokens,
                )
                tracer.log("llm_client", "json_repair_success", {})
                return repaired
            except Exception as exc:
                last_error = exc
                tracer.log(
                    "llm_client",
                    "json_repair_failed",
                    {"error": str(exc), "content_preview": invalid_content[:1200]},
                )

        if isinstance(last_error, json.JSONDecodeError):
            raise last_error
        if last_error is not None:
            raise RuntimeError(f"JSON completion failed: {last_error}") from last_error
        raise json.JSONDecodeError("JSON completion returned no parseable response", "", 0)


# Singleton instance
llm_client = LLMClient()
