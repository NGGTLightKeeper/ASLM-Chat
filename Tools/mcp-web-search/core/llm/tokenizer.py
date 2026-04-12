# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Lightweight token counting helpers for prompt budgeting."""

from __future__ import annotations

import logging
import os
import re
import threading

logger = logging.getLogger("core.llm.tokenizer")

_TOKENIZER = None
_TOKENIZER_NAME = ""
_TOKENIZER_LOCK = threading.Lock()
_TOKENIZER_LOAD_ATTEMPTED = False


def _configured_tokenizer_model() -> str:
    """Return the configured HF tokenizer model id, if any."""
    return (
        os.getenv("ASLM_LLM_TOKENIZER_MODEL", "").strip()
        or os.getenv("ASLM_TOKENIZER_MODEL", "").strip()
    )


def _load_tokenizer():
    global _TOKENIZER, _TOKENIZER_NAME, _TOKENIZER_LOAD_ATTEMPTED
    if _TOKENIZER is not None or _TOKENIZER_LOAD_ATTEMPTED:
        return _TOKENIZER
    with _TOKENIZER_LOCK:
        if _TOKENIZER is not None or _TOKENIZER_LOAD_ATTEMPTED:
            return _TOKENIZER
        _TOKENIZER_LOAD_ATTEMPTED = True
        model_name = _configured_tokenizer_model()
        if not model_name:
            logger.debug("LLM tokenizer model is not configured; using heuristic token counts")
            return None
        try:
            from transformers import AutoTokenizer

            for local_only in (True, False):
                try:
                    tokenizer = AutoTokenizer.from_pretrained(
                        model_name,
                        local_files_only=local_only,
                        trust_remote_code=True,
                    )
                    _TOKENIZER = tokenizer
                    _TOKENIZER_NAME = model_name
                    logger.info("Prompt tokenizer ready: model=%s local_only=%s", model_name, local_only)
                    return _TOKENIZER
                except Exception as exc:
                    logger.debug(
                        "tokenizer load failed model=%s local_only=%s: %s: %s",
                        model_name,
                        local_only,
                        type(exc).__name__,
                        exc,
                    )
        except Exception as exc:
            logger.debug("transformers tokenizer unavailable: %s: %s", type(exc).__name__, exc)
        return None


def heuristic_token_count(text: str) -> int:
    """Conservative fallback when an exact tokenizer is unavailable."""
    cleaned = (text or "").strip()
    if not cleaned:
        return 0
    # Count words, punctuation chunks, and non-ascii runs. This deliberately
    # overestimates compared to pure chars/4 so prompt budgets stay safe.
    pieces = re.findall(r"\w+|[^\w\s]", cleaned, flags=re.UNICODE)
    approx = int(len(pieces) * 1.35)
    # Dense JSON / markup / code tends to tokenize worse than prose.
    dense_bonus = cleaned.count("{") + cleaned.count("[") + cleaned.count("<") + cleaned.count("\n")
    return max(1, approx + (dense_bonus // 8))


def count_tokens(text: str) -> int:
    """Return token count for *text* using HF tokenizer when available."""
    if not text:
        return 0
    tokenizer = _load_tokenizer()
    if tokenizer is not None:
        try:
            return len(tokenizer.encode(text, add_special_tokens=False))
        except Exception as exc:
            logger.debug("tokenizer.encode failed, falling back to heuristic: %s: %s", type(exc).__name__, exc)
    return heuristic_token_count(text)


def token_counter_backend() -> str:
    """Return a short label for observability."""
    if _load_tokenizer() is not None:
        return f"hf:{_TOKENIZER_NAME}"
    return "heuristic"


def derive_token_budget_from_chars(char_budget: int) -> int:
    """Convert old char budgets into safer token budgets.

    The previous system used characters as a proxy for prompt size. That badly
    underestimates token growth for dense prompts, JSON, mixed-language text,
    and markdown. We therefore map the char budget to a conservative token
    budget rather than using a naive chars/4 estimate.
    """
    budget = max(4000, int(char_budget))
    return max(1024, budget // 2)
