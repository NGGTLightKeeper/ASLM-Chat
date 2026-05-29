"""Micro-chunk worker: surgically prune SEO-like clauses without lexicons.

Algorithm notes:
- No keyword dictionaries or language-specific word lists.
- Split text into sentence-level units, then into micro-clauses by punctuation.
- Protect numeric punctuation variants so values like "2 . 5" remain intact.
- Remove only anomalous clauses that are query-dense but fact-poor.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from core.extract.chunk_quality import seo_keyword_stuffing_penalty
from core.extract.content_processor import _bm25_tokenize

_NUM_SEP_SENTINELS = {
    ".": "\uE000",
    ",": "\uE001",
    "/": "\uE002",
    ":": "\uE003",
}
_SPACE_RE = re.compile(r"\s+")
_QUERY_CHARS_RE = re.compile(r"\w+", re.UNICODE)


def _normalize_spaces(text: str) -> str:
    return _SPACE_RE.sub(" ", text or "").strip()


def _protect_numeric_punctuation(text: str) -> str:
    """Protect decimal/range/version punctuation between digits.

    Handles compact and spaced forms:
    - 2.5 / 2,5 / 2/5 / 2:5
    - 2 . 5 / 2 ,5 / 2, 5 / 2 / 5
    """
    out: list[str] = []
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        if ch in {".", ",", "/", ":"}:
            left = i - 1
            while left >= 0 and text[left].isspace():
                left -= 1
            right = i + 1
            while right < n and text[right].isspace():
                right += 1
            if left >= 0 and right < n and text[left].isdigit() and text[right].isdigit():
                out.append(_NUM_SEP_SENTINELS[ch])
                i += 1
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def _restore_numeric_punctuation(text: str) -> str:
    out = text
    for sep, sentinel in _NUM_SEP_SENTINELS.items():
        out = out.replace(sentinel, sep)
    return out


def _split_sentences(text: str) -> list[str]:
    """Sentence-like split while preserving punctuation in each sentence."""
    protected = _protect_numeric_punctuation(text)
    parts = re.split(r"(?<=[.!?…])\s+", protected)
    return [_restore_numeric_punctuation(p).strip() for p in parts if p.strip()]


def _split_micro_clauses(sentence: str) -> list[str]:
    """Split sentence into clauses by punctuation excluding dash."""
    protected = _protect_numeric_punctuation(sentence)
    parts = re.split(r"\s*[,;:!?…]+\s*", protected)
    return [_restore_numeric_punctuation(p).strip() for p in parts if p.strip()]


def _query_hits(tokens: list[str], query_set: set[str]) -> int:
    return sum(1 for t in tokens if t in query_set)


def _factual_signal(clause: str) -> float:
    """Language-agnostic fact signal based on structure, not vocabulary."""
    text = clause or ""
    if not text:
        return 0.0
    tokens = _bm25_tokenize(text)
    if not tokens:
        return 0.0

    digit_ratio = sum(ch.isdigit() for ch in text) / max(1, len(text))
    punct_ratio = sum(ch in "[]()=/\\:+-_.%" for ch in text) / max(1, len(text))
    version_like = bool(re.search(r"\d+\s*[.,:/]\s*\d+", text))
    id_like = bool(re.search(r"[A-Za-z]{2,}-\d{3,}", text))

    score = 0.0
    score += min(0.5, digit_ratio * 8.0)
    score += min(0.25, punct_ratio * 2.5)
    score += 0.2 if version_like else 0.0
    score += 0.2 if id_like else 0.0
    return min(1.0, score)


def _query_density(clause_tokens: list[str], query_set: set[str]) -> float:
    if not clause_tokens:
        return 0.0
    return _query_hits(clause_tokens, query_set) / len(clause_tokens)


def _reference_density(clause_tokens: list[str], reference_set: set[str]) -> float:
    if not clause_tokens or not reference_set:
        return 0.0
    return _query_hits(clause_tokens, reference_set) / len(clause_tokens)


@dataclass(frozen=True)
class MicroPruneDebug:
    sentences_total: int = 0
    sentences_dropped: int = 0
    clauses_total: int = 0
    clauses_dropped: int = 0


def prune_micro_chunks(
    text: str,
    query: str,
    *,
    reference_text: str = "",
) -> tuple[str, MicroPruneDebug]:
    """Remove SEO-like micro-clauses and preserve factual fragments.

    Rules:
    - Clause can be dropped only when query-overlap is high and factual signal is low.
    - If all high-overlap content in a sentence is dropped and remaining content is weak,
      the full sentence is dropped.
    """
    text = text or ""
    if not text.strip() or not query.strip():
        return text, MicroPruneDebug()

    query_tokens = set(_bm25_tokenize(query))
    reference_tokens = set(_bm25_tokenize(reference_text))
    if not query_tokens and not reference_tokens:
        return text, MicroPruneDebug()

    kept_sentences: list[str] = []
    total_sent = 0
    dropped_sent = 0
    total_clause = 0
    dropped_clause = 0

    def _clause_is_tumor(
        clause: str,
        *,
        sentence_q_hits: int,
        query_tokens: set[str],
        reference_tokens: set[str],
    ) -> bool:
        clause_tokens = _bm25_tokenize(clause)
        if not clause_tokens:
            return False
        q_hits = _query_hits(clause_tokens, query_tokens)
        q_ratio = _query_density(clause_tokens, query_tokens)
        ref_hits = _query_hits(clause_tokens, reference_tokens)
        ref_ratio = _reference_density(clause_tokens, reference_tokens)
        local_dominance = q_hits / max(1, sentence_q_hits)
        factual = _factual_signal(clause)
        seo = seo_keyword_stuffing_penalty(clause, query_tokens)
        ref_tumor = (
            reference_tokens
            and ref_hits >= 2
            and ref_ratio >= 0.40
            and factual < 0.30
            and (seo >= 0.25 or len(clause_tokens) <= 12)
        )
        query_tumor = (
            query_tokens
            and q_hits >= 2
            and q_ratio >= 0.45
            and local_dominance >= 0.50
            and factual < 0.28
            and (
                seo >= 0.30
                or len(clause_tokens) <= 10
                or local_dominance >= 0.75
            )
        )
        return ref_tumor or query_tumor

    for sentence in _split_sentences(text):
        total_sent += 1
        clauses = _split_micro_clauses(sentence)
        total_clause += len(clauses)

        sentence_tokens = _bm25_tokenize(sentence)
        sentence_q_hits = _query_hits(sentence_tokens, query_tokens)
        sentence_ref_hits = _query_hits(sentence_tokens, reference_tokens)
        if sentence_q_hits <= 0 and sentence_ref_hits <= 0:
            kept_sentences.append(sentence)
            continue

        if len(clauses) == 1:
            if _clause_is_tumor(
                clauses[0],
                sentence_q_hits=max(1, sentence_q_hits, sentence_ref_hits),
                query_tokens=query_tokens,
                reference_tokens=reference_tokens,
            ):
                dropped_sent += 1
                dropped_clause += 1
            else:
                kept_sentences.append(sentence)
            continue

        clause_meta: list[tuple[str, bool]] = []
        for clause in clauses:
            clause_tokens = _bm25_tokenize(clause)
            if not clause_tokens:
                clause_meta.append((clause, True))
                continue

            is_tumor = _clause_is_tumor(
                clause,
                sentence_q_hits=max(1, sentence_q_hits, sentence_ref_hits),
                query_tokens=query_tokens,
                reference_tokens=reference_tokens,
            )
            keep = not is_tumor
            if not keep:
                dropped_clause += 1
            clause_meta.append((clause, keep))

        kept_clauses = [c for c, keep in clause_meta if keep]
        dropped_in_sentence = sum(1 for _, keep in clause_meta if not keep)
        if not kept_clauses:
            dropped_sent += 1
            continue

        if dropped_in_sentence == 0:
            kept_sentences.append(sentence)
            continue

        rest_text = " ".join(kept_clauses).strip()
        rest_tokens = _bm25_tokenize(rest_text)
        rest_hits = _query_hits(rest_tokens, query_tokens)
        rest_fact = _factual_signal(rest_text)

        # Whole-sentence drop if after surgery nothing informative remains.
        # Also drop when all remaining query-bearing content is still low-factual.
        if (rest_hits == 0 and rest_fact < 0.35) or (rest_hits > 0 and rest_fact < 0.20):
            dropped_sent += 1
            continue

        kept_sentences.append(_normalize_spaces(" ".join(kept_clauses)))

    out = "\n\n".join(s for s in kept_sentences if s.strip()).strip()
    debug = MicroPruneDebug(
        sentences_total=total_sent,
        sentences_dropped=dropped_sent,
        clauses_total=total_clause,
        clauses_dropped=dropped_clause,
    )
    return out, debug
