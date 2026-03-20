# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

import gc
import math
import os
import re
import threading
import importlib.util
import sys
import logging
from pathlib import Path
from typing import List, Optional, Tuple, Union

try:
    from .config import EMBEDDING_MODEL, EMBEDDING_FORCE_CPU
except Exception:
    _shared_config_path = Path(__file__).resolve().parents[2] / "config.py"
    if not _shared_config_path.exists():
        raise
    _cfg_spec = importlib.util.spec_from_file_location(
        "_mcp_web_search_config_for_semantic",
        _shared_config_path,
    )
    if _cfg_spec is None or _cfg_spec.loader is None:
        raise
    _cfg_module = importlib.util.module_from_spec(_cfg_spec)
    sys.modules[_cfg_spec.name] = _cfg_module
    _cfg_spec.loader.exec_module(_cfg_module)
    EMBEDDING_MODEL = getattr(_cfg_module, "EMBEDDING_MODEL")
    EMBEDDING_FORCE_CPU = getattr(_cfg_module, "EMBEDDING_FORCE_CPU")


# Lazy global model
_embedder = None
_embed_backend = "uninitialized"
_embed_model_name = ""
_embed_lock = threading.Lock()
_embedder_self_check_done = False
_semantic_debug_enabled = os.getenv("SEMANTIC_DEBUG", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


# Write debug output when semantic tracing is enabled.
def _debug_log(message: str) -> None:
    if _semantic_debug_enabled:
        print(message, file=sys.stderr, flush=True)


logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
logging.getLogger("transformers").setLevel(logging.ERROR)


# Detect CUDA out-of-memory failures.
def _is_cuda_oom(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "out of memory" in text or "cuda error" in text


# Clear CUDA caches when available.
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


# Check whether the GPU has enough free memory.
def _gpu_has_min_free_gb(min_free_gb: float = 1.0) -> bool:
    try:
        import torch

        if not torch.cuda.is_available():
            return False
        free_bytes, _ = torch.cuda.mem_get_info()
        return free_bytes >= int(min_free_gb * (1024 ** 3))
    except Exception:
        return False


# Prepare GPU memory before embedding model init.
def prepare_embedding_vram(target_free_gb: float = 1.0) -> Tuple[bool, float]:
    """
    Best-effort VRAM cleanup before embedding model init.
    Returns (has_target_headroom, free_gb).
    """
    _clear_cuda_cache()
    try:
        import torch

        if not torch.cuda.is_available():
            return False, 0.0
        free_bytes, _ = torch.cuda.mem_get_info()
        free_gb = free_bytes / (1024 ** 3)
        return free_gb >= target_free_gb, free_gb
    except Exception:
        return False, 0.0


# Build the list of candidate model names.
def _model_name_candidates() -> List[str]:
    primary = (EMBEDDING_MODEL or "").strip()
    candidates = [primary] if primary else []

    # Compatibility alias for the released HF model id.
    if primary.lower() in {"pplx-embed-v1-0.6b", "pplx-embed-v1"}:
        candidates.append("perplexity-ai/pplx-embed-v1-0.6b")

    deduped = []
    seen = set()
    for name in candidates:
        key = name.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(name)
    return deduped


# Load a sentence-transformers model with compatibility fallbacks.
def _load_sentence_transformer(
    model_name: str,
    *,
    local_files_only: bool,
    device: Optional[str] = None,
    model_kwargs: Optional[dict] = None,
):
    from sentence_transformers import SentenceTransformer

    kwargs = {
        "local_files_only": local_files_only,
        "trust_remote_code": True,
    }
    if device is not None:
        kwargs["device"] = device
    if model_kwargs:
        cleaned_model_kwargs = dict(model_kwargs)
        # Keep trust_remote_code only at top-level to avoid duplicate kwarg conflicts.
        cleaned_model_kwargs.pop("trust_remote_code", None)
        kwargs["model_kwargs"] = cleaned_model_kwargs

    try:
        return SentenceTransformer(model_name, **kwargs)
    except TypeError:
        # Older sentence-transformers may not support trust_remote_code.
        kwargs.pop("trust_remote_code", None)
        return SentenceTransformer(model_name, **kwargs)


# Try to load the embedder in one execution mode.
def _try_load_embedder(
    model_name: str,
    *,
    mode: str,
    local_files_only: bool,
):
    if mode == "cuda":
        import torch

        return _load_sentence_transformer(
            model_name,
            local_files_only=local_files_only,
            device="cuda",
            model_kwargs={
                "torch_dtype": torch.float16,
                "low_cpu_mem_usage": True,
            },
        )

    if mode == "cuda-offload":
        import torch

        offload_dir = Path(__file__).resolve().parents[1] / "_cache" / "embed_offload"
        offload_dir.mkdir(parents=True, exist_ok=True)
        return _load_sentence_transformer(
            model_name,
            local_files_only=local_files_only,
            model_kwargs={
                "device_map": "auto",
                "offload_folder": str(offload_dir),
                "offload_state_dict": True,
                "low_cpu_mem_usage": True,
                "torch_dtype": torch.float16,
            },
        )

    # CPU fallback
    return _load_sentence_transformer(
        model_name,
        local_files_only=local_files_only,
        device="cpu",
    )


# Encode text with stable embedding options.
def _encode(
    model,
    texts: Union[str, List[str]],
    *,
    convert_to_tensor: bool = True,
):
    # pplx-embed recommends unnormalized embeddings + cosine.
    # Do not force int8 precision here: embedder can be loaded in float16/cpu modes,
    # and mixed precision hints may trigger backend-specific incompatibilities.
    kwargs = {
        "convert_to_tensor": convert_to_tensor,
        "normalize_embeddings": False,
        "show_progress_bar": False,
    }
    embeddings = model.encode(texts, **kwargs)

    # sentence_transformers.util.cos_sim expects floating point inputs.
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


# Run a small warm-up pass through the embedder.
def _warmup_embedder(model) -> None:
    from sentence_transformers import util

    q = _encode(model, ["warmup query"], convert_to_tensor=True)
    d = _encode(model, ["warmup document"], convert_to_tensor=True)
    _ = util.cos_sim(q, d)


# Log one embedder self-check score.
def _log_embedder_self_check(model) -> None:
    from sentence_transformers import util

    text_a = "flashlight battery life"
    text_b = "how long does a flashlight battery last"
    try:
        emb_a = _encode(model, [text_a], convert_to_tensor=True)
        emb_b = _encode(model, [text_b], convert_to_tensor=True)
        score = float(util.cos_sim(emb_a, emb_b)[0][0])
        _debug_log(
            f"DEBUG semantic.self_check cosine={score:.4f} | a='{text_a}' | b='{text_b}'",
        )
    except Exception as e:
        _debug_log(
            f"DEBUG semantic.self_check failed: {type(e).__name__}: {e}",
        )


# Load the embedder with backend fallback logic.
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

    model_names = _model_name_candidates()
    if not model_names:
        raise RuntimeError("EMBEDDING_MODEL is empty")

    cuda_available = torch.cuda.is_available() and not EMBEDDING_FORCE_CPU
    mode_plan = []
    if cuda_available:
        mode_plan.append("cuda")
        mode_plan.append("cuda-offload")
    mode_plan.append("cpu")

    if cuda_available:
        _clear_cuda_cache()
        if not _gpu_has_min_free_gb(1.0):
            _debug_log(
                "Low free GPU memory before embedder init; trying offload/CPU fallback if needed."
            )

    last_exc: Optional[BaseException] = None

    for local_files_only in (True, False):
        for model_name in model_names:
            for mode in mode_plan:
                try:
                    if _semantic_debug_enabled:
                        model = _try_load_embedder(
                            model_name,
                            mode=mode,
                            local_files_only=local_files_only,
                        )
                        # Warmup immediately so failures happen during init, not on first real query.
                        _warmup_embedder(model)
                    else:
                        model = _try_load_embedder(
                            model_name,
                            mode=mode,
                            local_files_only=local_files_only,
                        )
                        # Warmup immediately so failures happen during init, not on first real query.
                        _warmup_embedder(model)
                    return model, mode, model_name
                except Exception as exc:
                    last_exc = exc
                    if _semantic_debug_enabled:
                        import traceback

                        _debug_log(
                            f"DEBUG embed-fallback mode={mode} model={model_name} "
                            f"local={local_files_only}: {type(exc).__name__}: {exc}\n"
                            + traceback.format_exc()
                        )

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Failed to initialize embedder")


# Lazily initialize and return the shared embedder.
def _get_embedder():
    global _embedder, _embed_backend, _embed_model_name
    if _embedder is None:
        with _embed_lock:
            if _embedder is None:
                model, backend, model_name = _load_embedder_with_fallback()
                _embedder = model
                _embed_backend = backend
                _embed_model_name = model_name
                _debug_log(
                    f"Semantic embedder initialized: model={model_name}, backend={backend}"
                )
    return _embedder


# Ensure the shared embedder is loaded and warmed up.
def ensure_embedder_ready(require_cuda: bool = False) -> bool:
    """
    Ensure embedder is loaded and warmed up.
    Intended to be called before timed semantic scoring so init time is separate.
    """
    global _embedder_self_check_done

    model = _get_embedder()
    if require_cuda and not _embed_backend.startswith("cuda"):
        raise RuntimeError(
            f"CUDA backend required for semantic mode, got '{_embed_backend}'"
        )
    if not _embedder_self_check_done:
        with _embed_lock:
            if not _embedder_self_check_done:
                _log_embedder_self_check(model)
                _embedder_self_check_done = True
    return True


# Return the current embedder backend name.
def get_embedder_backend() -> str:
    with _embed_lock:
        return _embed_backend


# Move the embedder to CPU to free GPU memory.
def park_embedder_on_cpu() -> bool:
    """
    Move embedder to CPU to reduce VRAM pressure for downstream LLM tasks.
    """
    global _embedder, _embed_backend
    with _embed_lock:
        if _embedder is None:
            return False
        if _embed_backend.startswith("cpu"):
            return False
        try:
            _embedder.to("cpu")
            _embed_backend = "cpu-parked"
            _clear_cuda_cache()
            return True
        except Exception:
            return False


# Split source text into semantic chunks.
def chunk_text(
    text: str,
    chunk_size: int = 500,
    overlap: int = 50,
) -> List[str]:
    """Split text into chunks by paragraphs with sentence-based fallback."""
    if not text or len(text) < 100:
        return [text] if text else []

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]

    chunks = []
    current = ""

    # Split overlong fragments when sentence boundaries are not enough.
    def _hard_split_long_text(value: str) -> List[str]:
        """Fallback splitter for long fragments without sentence boundaries."""
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
                    chunks.extend(_hard_split_long_text(sent))
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

    # Final guard against rare overlong chunks that escaped sentence splitting.
    normalized: List[str] = []
    for c in chunks:
        if len(c) <= chunk_size:
            normalized.append(c)
            continue
        normalized.extend(_hard_split_long_text(c))

    return [c for c in normalized if len(c) >= 50]


# Score chunks against the query.
def score_chunks(
    query: str,
    chunks: List[str],
) -> List[Tuple[str, float]]:
    """
    Cosine similarity of each chunk to query.
    Returns (chunk, raw_cosine_score) sorted desc.
    """
    if not chunks:
        return []

    try:
        model = _get_embedder()
    except Exception:
        return [(c, 0.0) for c in chunks]

    try:
        from sentence_transformers import util

        # E5 models require explicit task prefixes for stable similarity scores.
        query_input = f"query: {query}"
        chunk_inputs = [f"passage: {c}" for c in chunks]
        query_emb = _encode(model, [query_input], convert_to_tensor=True)
        chunk_embs = _encode(model, chunk_inputs, convert_to_tensor=True)
        scores = util.cos_sim(query_emb, chunk_embs)[0]
    except Exception:
        return [(c, 0.0) for c in chunks]

    scored = []
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


# Compute one relevance score for the full source.
def compute_source_relevance(
    text: str,
    query: str,
) -> float:
    """
    Compute whole-source relevance score.
    Uses max RAW cosine score among chunks (no min-max normalization).
    """
    chunks = chunk_text(text)
    if not chunks:
        return 0.0

    try:
        model = _get_embedder()
        from sentence_transformers import util

        # E5 models require explicit task prefixes for stable similarity scores.
        query_input = f"query: {query}"
        chunk_inputs = [f"passage: {c}" for c in chunks]
        query_emb = _encode(model, [query_input], convert_to_tensor=True)
        chunk_embs = _encode(model, chunk_inputs, convert_to_tensor=True)
        raw_scores = util.cos_sim(query_emb, chunk_embs)[0].tolist()
    except Exception as e:
        _debug_log(f"DEBUG semantic.compute_source_relevance failed: {type(e).__name__}: {e}")
        return 0.5

    scores = []
    nan_count = 0
    for raw in raw_scores:
        try:
            value = float(raw)
        except Exception:
            nan_count += 1
            value = 0.0
        if not math.isfinite(value):
            nan_count += 1
            value = 0.0
        scores.append(value)

    if scores:
        _debug_log(
            "DEBUG semantic.compute_source_relevance "
            f"min={min(scores):.3f} max={max(scores):.3f} chunks={len(scores)} nan={nan_count}"
        )
    else:
        _debug_log("DEBUG semantic.compute_source_relevance empty scores")

    return max(scores) if scores else 0.0


# Extract the most relevant content window from a source.
def extract_relevant_content(
    text: str,
    query: str,
    max_chars: int = 3000,
    top_k: int = 5,
    min_score: float = 0.20,
) -> Tuple[str, List[Tuple[str, float]]]:
    """
    Extract the most relevant chunks from the source text.

    Returns:
        (relevant_text, scored_chunks)
    """
    chunks = chunk_text(text)
    if not chunks:
        return text[:max_chars], []

    scored = score_chunks(query, chunks)

    selected = []
    total_chars = 0

    for chunk_text_item, score in scored[:top_k]:
        if score < min_score:
            break
        if total_chars + len(chunk_text_item) > max_chars:
            remaining = max_chars - total_chars
            if remaining > 100:
                selected.append(chunk_text_item[:remaining])
            break
        selected.append(chunk_text_item)
        total_chars += len(chunk_text_item)

    if not selected:
        if scored:
            return scored[0][0][:max_chars], scored
        return chunks[0][:max_chars], scored

    return "\n\n".join(selected), scored
