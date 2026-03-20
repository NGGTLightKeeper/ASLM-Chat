# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

import aiohttp
import asyncio
import json
import re
import threading
from typing import Optional

from .config import LM_STUDIO_URL

_session: Optional[aiohttp.ClientSession] = None
_session_lock = threading.Lock()


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

# Session lifecycle helpers.
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


# LLM request helpers.
async def call_llm(
    prompt: str,
    model: str,
    system: str = "",
    temperature: float = 0.3,
    max_tokens: int = 4096,
    timeout: float = 120.0,
) -> Optional[str]:
    """Call the LM Studio chat-completions endpoint and return response text."""

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "frequency_penalty": 0.5,
        "stream": False,
    }

    try:
        session = await get_session()
        async with session.post(
            f"{LM_STUDIO_URL}/chat/completions",
            json=payload,
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as response:
            if response.status != 200:
                return None

            data = await response.json()
            return data["choices"][0]["message"]["content"]
    except RuntimeError as error:
        # Recover once if the cached session was closed underneath the caller.
        if "Session is closed" in str(error):
            await close_session()
            try:
                session = await get_session()
                async with session.post(
                    f"{LM_STUDIO_URL}/chat/completions",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as response:
                    if response.status != 200:
                        return None

                    data = await response.json()
                    return data["choices"][0]["message"]["content"]
            except (aiohttp.ClientError, asyncio.TimeoutError, KeyError, IndexError, RuntimeError):
                return None

        return None
    except (aiohttp.ClientError, asyncio.TimeoutError, KeyError, IndexError):
        return None

# LLM request helpers.
async def call_llm_json(
    prompt: str,
    model: str,
    temperature: float = 0.3,
    timeout: float = 120.0,
) -> Optional[object]:
    """Call the LLM and parse a JSON object from the response text."""

    response = await call_llm(
        prompt=prompt,
        model=model,
        temperature=temperature,
        timeout=timeout,
    )
    if not response:
        return None

    return extract_json(response)


# JSON extraction helpers.
def extract_json(text: str) -> Optional[object]:
    """Extract a JSON object or array from a model response."""

    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Prefer fenced JSON blocks when the model wrapped the answer in Markdown.
    code_block = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if code_block:
        try:
            return json.loads(code_block.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Fall back to the first array or object-looking fragment in free-form text.
    for pattern in [r"\[.*\]", r"\{.*\}"]:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                continue

    return None
