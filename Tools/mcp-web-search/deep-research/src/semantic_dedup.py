# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Semantic deduplication for search results and extracted sources.

Provides MinHash-based and embedding-based dedup that sits between
the existing 3-level dedup (URL/title/snippet) and downstream triage.
"""

from __future__ import annotations

import logging
from typing import Callable, List, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# ---------------------------------------------------------------------------
# MinHash dedup (lightweight, no model required)
# ---------------------------------------------------------------------------

def _word_ngrams(text: str, n: int = 3) -> list[str]:
    """Tokenize *text* into overlapping word n-grams."""
    words = text.lower().split()
    if len(words) < n:
        return words
    return [" ".join(words[i : i + n]) for i in range(len(words) - n + 1)]


def minhash_dedup(
    items: List[T],
    text_fn: Callable[[T], str],
    threshold: float = 0.7,
    num_perm: int = 128,
) -> List[T]:
    """Remove near-duplicates using MinHash/LSH.

    Items with text shorter than 30 characters are kept unconditionally.
    First occurrence wins; order is preserved.
    """
    try:
        from datasketch import MinHash, MinHashLSH
    except ImportError:
        logger.warning("datasketch not installed; skipping minhash dedup")
        return list(items)

    if not items:
        return []

    lsh = MinHashLSH(threshold=threshold, num_perm=num_perm)
    kept: list[T] = []
    seen_keys: set[int] = set()

    for idx, item in enumerate(items):
        text = text_fn(item)
        if len(text) < 30:
            kept.append(item)
            continue

        m = MinHash(num_perm=num_perm)
        for gram in _word_ngrams(text):
            m.update(gram.encode("utf-8"))

        key = f"item_{idx}"
        try:
            matches = lsh.query(m)
        except Exception:
            matches = []

        if matches:
            continue

        try:
            lsh.insert(key, m)
        except Exception:
            pass
        kept.append(item)

    removed = len(items) - len(kept)
    if removed:
        logger.info("minhash_dedup: removed %d near-duplicates from %d items", removed, len(items))
    return kept


# ---------------------------------------------------------------------------
# Embedding dedup (requires the shared embedder from semantic.py)
# ---------------------------------------------------------------------------

def embedding_dedup(
    items: List[T],
    text_fn: Callable[[T], str],
    threshold: float = 0.85,
    batch_size: int = 4,
) -> List[T]:
    """Remove near-duplicates using cosine similarity on embeddings.

    Uses the shared embedder from semantic.py.  Greedy removal:
    iterate in order, mark any later item whose similarity to an
    already-kept item exceeds *threshold*.
    """
    if len(items) <= 1:
        return list(items)

    try:
        from .semantic import _get_embedder, _encode
    except ImportError:
        logger.warning("Cannot import semantic embedder; skipping embedding dedup")
        return list(items)

    try:
        import numpy as np
    except ImportError:
        logger.warning("numpy not available; skipping embedding dedup")
        return list(items)

    model = _get_embedder()
    texts = [text_fn(item) for item in items]

    # Encode in batches to limit peak memory.
    all_embeddings = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        embs = _encode(model, batch, convert_to_tensor=False)
        if hasattr(embs, "cpu"):
            embs = embs.cpu().numpy()
        all_embeddings.append(embs)

    embeddings = np.vstack(all_embeddings)
    # L2-normalize for cosine similarity via dot product.
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    embeddings = embeddings / norms

    keep_mask = [True] * len(items)
    for i in range(len(items)):
        if not keep_mask[i]:
            continue
        for j in range(i + 1, len(items)):
            if not keep_mask[j]:
                continue
            sim = float(np.dot(embeddings[i], embeddings[j]))
            if sim >= threshold:
                keep_mask[j] = False

    kept = [item for item, keep in zip(items, keep_mask) if keep]
    removed = len(items) - len(kept)
    if removed:
        logger.info("embedding_dedup: removed %d near-duplicates from %d items", removed, len(items))
    return kept


# ---------------------------------------------------------------------------
# Hybrid dedup (MinHash first, then optional embedding pass)
# ---------------------------------------------------------------------------

def hybrid_dedup(
    items: List[T],
    text_fn: Callable[[T], str],
    minhash_threshold: float = 0.7,
    embedding_threshold: float = 0.85,
    use_embeddings: bool = True,
    num_perm: int = 128,
    batch_size: int = 4,
) -> List[T]:
    """Run MinHash dedup first, then optionally refine with embedding dedup."""
    result = minhash_dedup(items, text_fn, threshold=minhash_threshold, num_perm=num_perm)
    if use_embeddings and len(result) > 1:
        result = embedding_dedup(result, text_fn, threshold=embedding_threshold, batch_size=batch_size)
    return result
