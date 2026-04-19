# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""
Semantic deduplication for search results and extracted sources.

Ported from legacy deep-research/src/semantic_dedup.py.
Dependency on relative-import semantic.py replaced with core.llm.semantic.

Provides three levels of dedup that compose in a pipeline:
  1. minhash_dedup   — lightweight near-duplicate removal (no model required)
  2. embedding_dedup — cosine-similarity pass (requires embedder from semantic.py)
  3. hybrid_dedup    — MinHash first, optional embedding refinement

The generic TypeVar T means these work on any objects — search results,
extracted sources, annotated paragraphs, etc.  Callers supply a text_fn
that extracts the comparable text from each item.

Public API
----------
minhash_dedup(items, text_fn, threshold, num_perm)  -> List[T]
embedding_dedup(items, text_fn, threshold, ...)      -> List[T]
hybrid_dedup(items, text_fn, ...)                    -> List[T]
"""

from __future__ import annotations

import logging
from typing import Callable, List, TypeVar

logger = logging.getLogger("core.extract.semantic_dedup")

T = TypeVar("T")

# ---------------------------------------------------------------------------
# MinHash dedup (no ML model required)
# ---------------------------------------------------------------------------

def _word_ngrams(text: str, n: int = 3) -> list[str]:
    words = text.lower().split()
    if len(words) < n:
        return words
    return [" ".join(words[i:i + n]) for i in range(len(words) - n + 1)]


def minhash_dedup(
    items: List[T],
    text_fn: Callable[[T], str],
    threshold: float = 0.70,
    num_perm: int = 128,
) -> List[T]:
    """Remove near-duplicates using MinHash + LSH.

    Items with text shorter than 30 characters are always kept.
    First occurrence wins; order is preserved.
    Falls back to identity (no-op) if datasketch is not installed.
    """
    try:
        from datasketch import MinHash, MinHashLSH
    except ImportError:
        logger.warning("datasketch not installed — skipping minhash dedup")
        return list(items)

    if not items:
        return []

    lsh = MinHashLSH(threshold=threshold, num_perm=num_perm)
    kept: List[T] = []

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
            continue  # duplicate — drop

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
# Embedding dedup (requires sentence-transformers)
# ---------------------------------------------------------------------------

def embedding_dedup(
    items: List[T],
    text_fn: Callable[[T], str],
    threshold: float = 0.85,
    batch_size: int = 4,
) -> List[T]:
    """Remove near-duplicates using cosine similarity on embeddings.

    Uses the shared embedder from core.llm.semantic.
    Greedy: iterates in order, marks any later item whose similarity to an
    already-kept item exceeds *threshold*.
    Falls back to identity (no-op) if embedder or numpy unavailable.
    """
    if len(items) <= 1:
        return list(items)

    try:
        from core.llm.semantic import _get_embedder, _encode
    except ImportError:
        logger.warning("Cannot import semantic embedder — skipping embedding dedup")
        return list(items)

    try:
        import numpy as np
    except ImportError:
        logger.warning("numpy not available — skipping embedding dedup")
        return list(items)

    model = _get_embedder()
    texts = [text_fn(item) for item in items]

    all_embeddings = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start:start + batch_size]
        embs = _encode(model, batch, convert_to_tensor=False)
        if hasattr(embs, "cpu"):
            embs = embs.cpu().numpy()
        all_embeddings.append(embs)

    embeddings = np.vstack(all_embeddings)
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
# Hybrid dedup
# ---------------------------------------------------------------------------

def hybrid_dedup(
    items: List[T],
    text_fn: Callable[[T], str],
    minhash_threshold: float = 0.70,
    embedding_threshold: float = 0.85,
    use_embeddings: bool = True,
    num_perm: int = 128,
    batch_size: int = 4,
) -> List[T]:
    """MinHash first, then optional embedding refinement.

    This is the recommended entry-point for the dedup pipeline in
    services/deep_research/dedup_filter.py:
      1. MinHash catches cheap exact near-duplicates quickly.
      2. Embedding pass catches semantically equivalent but differently phrased items.
    """
    result = minhash_dedup(items, text_fn, threshold=minhash_threshold, num_perm=num_perm)
    if use_embeddings and len(result) > 1:
        result = embedding_dedup(result, text_fn, threshold=embedding_threshold, batch_size=batch_size)
    return result
