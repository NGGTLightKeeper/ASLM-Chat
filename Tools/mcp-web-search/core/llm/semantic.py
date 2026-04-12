# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""
Shared embedding model for deep research semantic operations.

Ported from legacy deep-research/src/semantic.py.
Cleaned up: removed relative config import, replaced with simple env-var / default.
The embedder singleton is thread-safe and lazy-loaded on first use.

Public API
----------
get_embedder()                      — lazy singleton (SentenceTransformer instance)
ensure_embedder_ready()             — load + warm-up, return True on success
get_embedder_backend() -> str       — "cuda" | "cpu" | "cpu-parked" | "uninitialized"
park_embedder_on_cpu() -> bool      — move to CPU to reduce VRAM pressure
chunk_text(text, ...) -> list[str]  — split text into semantic chunks
score_chunks(query, chunks)         — cosine similarity, sorted desc
compute_source_relevance(text, query) -> float
extract_relevant_content(text, query, ...) -> (str, scored_chunks)
_encode(model, texts, ...)          — internal encode helper (used by semantic_dedup)
"""

from __future__ import annotations

import gc
import math
import os
import re
import threading
import logging
from typing import List, Optional, Tuple, Union

logger = logging.getLogger("core.llm.semantic")

# ---------------------------------------------------------------------------
# Config — env-var overrides, sensible defaults
# ---------------------------------------------------------------------------

EMBEDDING_MODEL: str = os.getenv(
    "ASLM_EMBEDDING_MODEL",
    "intfloat/multilingual-e5-small",
)
EMBEDDING_FORCE_CPU: bool = os.getenv("ASLM_EMBEDDING_FORCE_CPU", "0").strip() in ("1", "true", "yes")

# Suppress noisy HF loggers at module level.
logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
logging.getLogger("transformers").setLevel(logging.ERROR)

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_embedder = None
_embed_backend: str = "uninitialized"
_embed_model_name: str = ""
_embed_lock = threading.Lock()
_embedder_self_check_done: bool = False

# ---------------------------------------------------------------------------
# CUDA helpers
# ---------------------------------------------------------------------------

def _is_cuda_oom(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "out of memory" in text or "cuda error" in text


def _clear_cuda_cache() -> None:
    try:
        import torch
        if torch.cuda.is_available():
            gc.collect()
            torch.cuda.empty_cache()
            try:
                torch.cuda.ipc_collect()
            except Exception:
                pass
    except Exception:
        pass


def _gpu_has_min_free_gb(min_free_gb: float = 1.0) -> bool:
    try:
        import torch
        if not torch.cuda.is_available():
            return False
        free_bytes, _ = torch.cuda.mem_get_info()
        return free_bytes >= int(min_free_gb * (1024 ** 3))
    except Exception:
        return False

# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------

def _load_sentence_transformer(
    model_name: str,
    *,
    local_files_only: bool,
    device: Optional[str] = None,
    model_kwargs: Optional[dict] = None,
):
    from sentence_transformers import SentenceTransformer

    kwargs: dict = {"local_files_only": local_files_only, "trust_remote_code": True}
    if device is not None:
        kwargs["device"] = device
    if model_kwargs:
        cleaned = dict(model_kwargs)
        cleaned.pop("trust_remote_code", None)
        kwargs["model_kwargs"] = cleaned
    try:
        return SentenceTransformer(model_name, **kwargs)
    except TypeError:
        kwargs.pop("trust_remote_code", None)
        return SentenceTransformer(model_name, **kwargs)


def _try_load_embedder(model_name: str, *, mode: str, local_files_only: bool):
    if mode == "cuda":
        import torch
        return _load_sentence_transformer(
            model_name, local_files_only=local_files_only, device="cuda",
            model_kwargs={"torch_dtype": torch.float16, "low_cpu_mem_usage": True},
        )
    if mode == "cuda-offload":
        import torch
        from pathlib import Path
        offload_dir = Path(__file__).resolve().parents[2] / "_cache" / "embed_offload"
        offload_dir.mkdir(parents=True, exist_ok=True)
        return _load_sentence_transformer(
            model_name, local_files_only=local_files_only,
            model_kwargs={
                "device_map": "auto",
                "offload_folder": str(offload_dir),
                "offload_state_dict": True,
                "low_cpu_mem_usage": True,
                "torch_dtype": torch.float16,
            },
        )
    return _load_sentence_transformer(
        model_name, local_files_only=local_files_only, device="cpu",
    )


def _warmup_embedder(model) -> None:
    from sentence_transformers import util
    q = _encode(model, ["warmup query"], convert_to_tensor=True)
    d = _encode(model, ["warmup document"], convert_to_tensor=True)
    _ = util.cos_sim(q, d)


def _load_embedder_with_fallback():
    import torch

    os.environ.setdefault("HF_HUB_OFFLINE", "0")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
    os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")
    try:
        from transformers.utils import logging as hf_logging
        hf_logging.set_verbosity_error()
    except Exception:
        pass

    primary = (EMBEDDING_MODEL or "").strip()
    model_names = [primary] if primary else []
    if not model_names:
        raise RuntimeError("EMBEDDING_MODEL is empty — set ASLM_EMBEDDING_MODEL env var")

    cuda_available = torch.cuda.is_available() and not EMBEDDING_FORCE_CPU
    mode_plan: list[str] = []
    if cuda_available:
        _clear_cuda_cache()
        mode_plan.extend(["cuda", "cuda-offload"])
    mode_plan.append("cpu")

    last_exc: Optional[BaseException] = None
    for local_files_only in (True, False):
        for model_name in model_names:
            for mode in mode_plan:
                try:
                    model = _try_load_embedder(model_name, mode=mode, local_files_only=local_files_only)
                    _warmup_embedder(model)
                    return model, mode, model_name
                except Exception as exc:
                    last_exc = exc
                    logger.debug(
                        "embed-fallback mode=%s model=%s local=%s: %s: %s",
                        mode, model_name, local_files_only, type(exc).__name__, exc,
                    )

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Failed to initialize embedder")

# ---------------------------------------------------------------------------
# Public: singleton access
# ---------------------------------------------------------------------------

def _get_embedder():
    """Load and cache the shared embedding model (thread-safe, lazy)."""
    global _embedder, _embed_backend, _embed_model_name
    if _embedder is None:
        with _embed_lock:
            if _embedder is None:
                model, backend, model_name = _load_embedder_with_fallback()
                _embedder = model
                _embed_backend = backend
                _embed_model_name = model_name
                logger.info("Semantic embedder ready: model=%s backend=%s", model_name, backend)
    return _embedder


def ensure_embedder_ready(require_cuda: bool = False) -> bool:
    """Load and warm up the embedder. Returns True on success."""
    global _embedder_self_check_done
    model = _get_embedder()
    if require_cuda and not _embed_backend.startswith("cuda"):
        raise RuntimeError(
            f"CUDA backend required for semantic mode, got '{_embed_backend}'"
        )
    if not _embedder_self_check_done:
        with _embed_lock:
            if not _embedder_self_check_done:
                try:
                    from sentence_transformers import util
                    emb_a = _encode(model, ["flashlight battery life"], convert_to_tensor=True)
                    emb_b = _encode(model, ["how long does a flashlight battery last"], convert_to_tensor=True)
                    score = float(util.cos_sim(emb_a, emb_b)[0][0])
                    logger.debug("Embedder self-check cosine=%.4f", score)
                except Exception as exc:
                    logger.debug("Embedder self-check failed: %s", exc)
                _embedder_self_check_done = True
    return True


def get_embedder_backend() -> str:
    with _embed_lock:
        return _embed_backend


def park_embedder_on_cpu() -> bool:
    """Move embedder to CPU to free VRAM for LLM tasks. Returns True if parked."""
    global _embed_backend
    with _embed_lock:
        if _embedder is None or _embed_backend.startswith("cpu"):
            return False
        try:
            _embedder.to("cpu")
            _embed_backend = "cpu-parked"
            _clear_cuda_cache()
            return True
        except Exception:
            return False

# ---------------------------------------------------------------------------
# Encode helper (used internally by semantic_dedup)
# ---------------------------------------------------------------------------

def _encode(
    model,
    texts: Union[str, List[str]],
    *,
    convert_to_tensor: bool = True,
):
    """Encode texts, ensuring float dtype for cosine-sim compatibility."""
    kwargs = {
        "convert_to_tensor": convert_to_tensor,
        "normalize_embeddings": False,
        "show_progress_bar": False,
    }
    embeddings = model.encode(texts, **kwargs)
    try:
        import torch
        if isinstance(embeddings, torch.Tensor):
            return embeddings.float() if not embeddings.is_floating_point() else embeddings
    except Exception:
        pass
    try:
        import numpy as np
        if isinstance(embeddings, np.ndarray) and embeddings.dtype.kind not in ("f", "c"):
            return embeddings.astype("float32", copy=False)
    except Exception:
        pass
    if hasattr(embeddings, "float"):
        try:
            return embeddings.float()
        except Exception:
            pass
    return embeddings

# ---------------------------------------------------------------------------
# Text chunking
# ---------------------------------------------------------------------------

def chunk_text(
    text: str,
    chunk_size: int = 500,
    overlap: int = 50,
) -> List[str]:
    """Split text into semantic chunks by paragraphs with sentence-based fallback."""
    if not text or len(text) < 100:
        return [text] if text else []

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]

    def _hard_split(value: str) -> List[str]:
        if not value:
            return []
        window = max(120, chunk_size)
        step = max(80, window - max(0, overlap))
        out: List[str] = []
        start = 0
        n = len(value)
        while start < n:
            part = value[start:start + window].strip()
            if part:
                out.append(part)
            if start + window >= n:
                break
            start += step
        return out

    chunks: List[str] = []
    current = ""
    for para in paragraphs:
        if len(para) > chunk_size:
            if current:
                chunks.append(current.strip())
                current = ""
            sentences = re.split(r"(?<=[.!?])\s+", para)
            buf = ""
            for sent in sentences:
                if len(sent) > chunk_size:
                    if buf:
                        chunks.append(buf.strip())
                        buf = ""
                    chunks.extend(_hard_split(sent))
                    continue
                if len(buf) + len(sent) > chunk_size and buf:
                    chunks.append(buf.strip())
                    buf = sent
                else:
                    buf = f"{buf} {sent}" if buf else sent
            if buf:
                chunks.append(buf.strip())
        elif len(current) + len(para) > chunk_size:
            chunks.append(current.strip())
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para

    if current:
        chunks.append(current.strip())

    normalized: List[str] = []
    for c in chunks:
        if len(c) <= chunk_size:
            normalized.append(c)
        else:
            normalized.extend(_hard_split(c))
    return [c for c in normalized if len(c) >= 50]

# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_chunks(query: str, chunks: List[str]) -> List[Tuple[str, float]]:
    """Return (chunk, cosine_score) pairs sorted descending."""
    if not chunks:
        return []
    try:
        model = _get_embedder()
    except Exception:
        return [(c, 0.0) for c in chunks]
    try:
        from sentence_transformers import util
        query_emb = _encode(model, [f"query: {query}"], convert_to_tensor=True)
        chunk_embs = _encode(model, [f"passage: {c}" for c in chunks], convert_to_tensor=True)
        scores = util.cos_sim(query_emb, chunk_embs)[0]
    except Exception:
        return [(c, 0.0) for c in chunks]

    scored: List[Tuple[str, float]] = []
    for chunk, raw in zip(chunks, scores.tolist()):
        try:
            value = float(raw)
        except Exception:
            value = 0.0
        if not math.isfinite(value):
            value = 0.0
        scored.append((chunk, round(value, 4)))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def compute_source_relevance(text: str, query: str) -> float:
    """Max cosine score over all chunks. Returns 0.5 on embedding failure."""
    chunks = chunk_text(text)
    if not chunks:
        return 0.0
    try:
        model = _get_embedder()
        from sentence_transformers import util
        query_emb = _encode(model, [f"query: {query}"], convert_to_tensor=True)
        chunk_embs = _encode(model, [f"passage: {c}" for c in chunks], convert_to_tensor=True)
        raw_scores = util.cos_sim(query_emb, chunk_embs)[0].tolist()
    except Exception as exc:
        logger.debug("compute_source_relevance failed: %s: %s", type(exc).__name__, exc)
        return 0.5

    scores = []
    for raw in raw_scores:
        try:
            value = float(raw)
        except Exception:
            value = 0.0
        if not math.isfinite(value):
            value = 0.0
        scores.append(value)
    return max(scores) if scores else 0.0


def extract_relevant_content(
    text: str,
    query: str,
    max_chars: int = 3000,
    top_k: int = 5,
    min_score: float = 0.20,
) -> Tuple[str, List[Tuple[str, float]]]:
    """Extract the most relevant chunks from source text up to max_chars."""
    chunks = chunk_text(text)
    if not chunks:
        return text[:max_chars], []

    scored = score_chunks(query, chunks)
    selected: List[str] = []
    total_chars = 0

    for chunk_item, score in scored[:top_k]:
        if score < min_score:
            break
        if total_chars + len(chunk_item) > max_chars:
            remaining = max_chars - total_chars
            if remaining > 100:
                selected.append(chunk_item[:remaining])
            break
        selected.append(chunk_item)
        total_chars += len(chunk_item)

    if not selected:
        if scored:
            return scored[0][0][:max_chars], scored
        return chunks[0][:max_chars], scored
    return "\n\n".join(selected), scored
