"""Chunk quality signals: SEO keyword-stuffing penalty (language-agnostic)."""

from __future__ import annotations

import re
from collections import Counter
from typing import Iterable

SEO_HARD_REJECT_THRESHOLD: float = 0.88

_SENTENCE_END_RE = re.compile(r"[.!?;»]\s*$")
_TOKEN_RE = re.compile(r"\b\w+\b", re.UNICODE)
_BIGRAM_WORD_RE = _TOKEN_RE


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "") if len(t) > 1]


def _sentence_like_ratio(text: str) -> float:
    compact = (text or "").strip()
    if len(compact) < 40:
        return 0.0
    endings = len(re.findall(r"[.!?…]", compact))
    return min(1.0, endings / max(1, len(compact) / 180))


def _repeated_trigram_penalty(tokens: list[str]) -> float:
    if len(tokens) < 12:
        return 0.0
    trigrams = Counter(tuple(tokens[i : i + 3]) for i in range(len(tokens) - 2))
    if not trigrams:
        return 0.0
    top = trigrams.most_common(1)[0][1]
    return min(1.0, max(0.0, (top - 2) / max(4, len(tokens) / 20)))


def seo_keyword_stuffing_penalty(
    text: str,
    query_terms: Iterable[str] | None = None,
) -> float:
    """Return 0..1 penalty for SEO keyword piles (1 = reject-worthy spam)."""
    tokens = _tokenize(text)
    if len(tokens) < 12:
        return 0.0

    unique_ratio = len(set(tokens)) / len(tokens)
    counts = Counter(tokens)
    top_share = counts.most_common(1)[0][1] / len(tokens)

    query_set = {t for t in (query_terms or []) if t}
    query_token_hits = sum(counts.get(t, 0) for t in query_set)
    query_share = query_token_hits / len(tokens)

    words = _BIGRAM_WORD_RE.findall(text.lower())
    bigram_counts = Counter(zip(words, words[1:]))
    top_bigram_share = 0.0
    if bigram_counts and len(words) > 1:
        top_bigram_share = bigram_counts.most_common(1)[0][1] / max(1, len(words) - 1)

    trigram_p = _repeated_trigram_penalty(tokens)

    penalty = 0.0
    if unique_ratio < 0.52:
        penalty += min(0.40, (0.52 - unique_ratio) * 1.2)
    if top_share > 0.08:
        penalty += min(0.40, (top_share - 0.08) * 3.5)
    if query_share > 0.14:
        penalty += min(0.40, (query_share - 0.14) * 3.0)
    if top_bigram_share > 0.06:
        penalty += min(0.30, (top_bigram_share - 0.06) * 2.5)
    if trigram_p > 0.2:
        penalty += min(0.35, trigram_p * 0.5)
    if len(text) > 350 and _sentence_like_ratio(text) < 0.18 and unique_ratio < 0.62:
        penalty += 0.20

    return min(1.0, round(penalty, 4))


# Alias used in tests and profile_chunk_selector.
seo_penalty = seo_keyword_stuffing_penalty


def is_seo_hard_reject(
    chunk_text: str,
    query_tokens: Iterable[str] | None = None,
    threshold: float = SEO_HARD_REJECT_THRESHOLD,
) -> bool:
    return seo_keyword_stuffing_penalty(chunk_text, query_tokens) >= threshold
