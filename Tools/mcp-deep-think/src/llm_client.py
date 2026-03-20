# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

import asyncio
import json
import logging
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from .config import settings
from .tracer import tracer

logger = logging.getLogger(__name__)


# JSON parsing helpers

# Extract the first valid JSON object from a model response
def _extract_json(content: str) -> dict:
    """Extract a JSON object from a model response using several fallbacks."""

    import re

    def _try_parse(text: str) -> dict | None:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

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
        self._resolved_model: Optional[str] = None


    # HTTP client lifecycle
    def _models_url(self) -> str:
        """Convert the chat completions URL into the matching models URL."""

        parts = urlsplit(self.base_url)
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


    # Model resolution
    async def _resolve_model(self, force_refresh: bool = False) -> str:
        """Resolve the configured model id or query LM Studio for an active model."""

        configured = (settings.lm_studio_model or "").strip()
        if configured and configured.lower() not in {"local-model", "auto"} and not force_refresh:
            return configured
        if self._resolved_model and not force_refresh:
            return self._resolved_model

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

        self._resolved_model = model_id
        return model_id


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
        response = await client.post(self.base_url, json=payload)
        if response.status_code == 400:
            self._resolved_model = None
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

        model_name = await self._resolve_model()
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


    # JSON completions
    async def chat_completion_json(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 1200,
    ) -> dict:
        """Request a JSON-shaped response and parse it robustly."""

        # Append a strict JSON reminder when the last user turn does not already request it.
        if messages and messages[-1]["role"] == "user":
            if "JSON" not in messages[-1]["content"] and "json" not in messages[-1]["content"]:
                messages[-1]["content"] += "\n\nRESPOND STRICTLY IN JSON FORMAT WITH NO EXTRA TEXT."

        content = await self.chat_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=False,
        )
        return _extract_json(content)


# Singleton instance
llm_client = LLMClient()
