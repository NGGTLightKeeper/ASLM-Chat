# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import logging
import os
import subprocess
from typing import Any, Callable, Optional

logger = logging.getLogger("core.extract.gliner_wrapper")

_MEDIUM_MODEL_ID = os.getenv("ASLM_GLINER_MEDIUM_MODEL", "urchade/gliner_medium-v2.1")
_SMALL_MODEL_ID = os.getenv("ASLM_GLINER_SMALL_MODEL", "urchade/gliner_small-v2.1")
_FORCED_MODEL_ID = os.getenv("ASLM_GLINER_MODEL", "").strip()
_MEDIUM_MIN_VRAM_GB = float(os.getenv("ASLM_GLINER_MEDIUM_MIN_VRAM_GB", "1.5"))
_SMALL_MIN_VRAM_GB = float(os.getenv("ASLM_GLINER_SMALL_MIN_VRAM_GB", "1.0"))

_ENTITY_LABELS = [
    "person", "organization", "location", "date", "event",
    "technology", "product", "concept", "metric", "scientific term",
]

_model_cache: dict[str, Any] = {}
_skip_logged: set[str] = set()


# Log a GLiNER skip reason at most once per key.
def _log_skip_once(key: str, message: str) -> None:
    if key in _skip_logged:
        return
    _skip_logged.add(key)
    logger.warning(message)


# Restore environment variables after a temporary HF offline override.
def _restore_env(previous: dict[str, str | None]) -> None:
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


# Read free CUDA VRAM in GB via nvidia-smi or torch.
def _cuda_free_gb() -> float | None:
    try:
        output = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=memory.free",
                "--format=csv,noheader,nounits",
                "-i",
                "0",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=2.0,
        )
        first = output.strip().splitlines()[0].strip()
        if first:
            return float(first) / 1024.0
    except Exception:
        pass

    try:
        import torch  # type: ignore
        if not torch.cuda.is_available():
            return None
        free_bytes, _ = torch.cuda.mem_get_info()
        return free_bytes / (1024 ** 3)
    except Exception:
        return None


# Return (model_id, device) for a safe CUDA GLiNER runtime, or None.
def get_gliner_runtime(device: str = "cuda") -> tuple[str, str] | None:
    requested = (device or "cuda").lower().strip()
    if requested != "cuda":
        _log_skip_once(
            f"requested-{requested}",
            f"GLiNER disabled: requested device={requested!r}; CPU fallback is not allowed",
        )
        return None

    try:
        import torch  # type: ignore
        if not torch.cuda.is_available():
            _log_skip_once("cuda-unavailable", "GLiNER disabled: torch.cuda.is_available() is false")
            return None
    except Exception as exc:
        _log_skip_once("torch-error", f"GLiNER disabled: CUDA check failed: {exc}")
        return None

    free_gb = _cuda_free_gb()
    if free_gb is None:
        _log_skip_once("vram-unknown", "GLiNER disabled: could not read free CUDA VRAM")
        return None

    if _FORCED_MODEL_ID:
        default_min = _SMALL_MIN_VRAM_GB if "small" in _FORCED_MODEL_ID.lower() else _MEDIUM_MIN_VRAM_GB
        min_gb = float(os.getenv("ASLM_GLINER_MIN_VRAM_GB", str(default_min)))
        if free_gb >= min_gb:
            return _FORCED_MODEL_ID, "cuda"
        _log_skip_once(
            f"forced-low-vram-{_FORCED_MODEL_ID}",
            f"GLiNER disabled: forced model={_FORCED_MODEL_ID!r} needs >= {min_gb:.1f}GB free VRAM, got {free_gb:.1f}GB",
        )
        return None

    if free_gb >= _MEDIUM_MIN_VRAM_GB:
        return _MEDIUM_MODEL_ID, "cuda"
    if free_gb >= _SMALL_MIN_VRAM_GB:
        return _SMALL_MODEL_ID, "cuda"

    _log_skip_once(
        "low-vram",
        f"GLiNER disabled: free CUDA VRAM {free_gb:.1f}GB < small-model threshold {_SMALL_MIN_VRAM_GB:.1f}GB",
    )
    return None


# True when a safe CUDA GLiNER runtime is available; log_fn receives diagnostics.
def gliner_cuda_enabled(log_fn: Callable[[str], None]) -> bool:
    try:
        runtime = get_gliner_runtime("cuda")
    except Exception as exc:
        log_fn(f"  GLiNER skipped: runtime probe failed: {exc}")
        return False
    if runtime is None:
        log_fn("  GLiNER skipped: insufficient CUDA VRAM for configured models")
        return False
    model_id, device = runtime
    log_fn(f"  GLiNER runtime: model={model_id} device={device}")
    return True


# True when the gliner package is importable.
def is_gliner_available() -> bool:
    try:
        import gliner  # noqa: F401
        return True
    except ImportError:
        return False


# Load (or return cached) GLiNER model on the requested device.
def _load_model(device: str = "cuda") -> Optional[Any]:
    runtime = get_gliner_runtime(device)
    if runtime is None:
        return None
    model_id, device = runtime

    cache_key = f"{model_id}:{device}"
    if cache_key in _model_cache:
        return _model_cache[cache_key]

    try:
        logger.info("Loading GLiNER %s on %s", model_id, device)
        previous_env = {
            "HF_HUB_OFFLINE": os.environ.get("HF_HUB_OFFLINE"),
            "TRANSFORMERS_OFFLINE": os.environ.get("TRANSFORMERS_OFFLINE"),
        }
        allow_download = os.getenv("ASLM_GLINER_ALLOW_DOWNLOAD", "").strip().lower() in ("1", "true", "yes")
        try:
            if not allow_download:
                os.environ["HF_HUB_OFFLINE"] = "1"
                os.environ["TRANSFORMERS_OFFLINE"] = "1"

            from gliner import GLiNER

            try:
                model = GLiNER.from_pretrained(model_id, local_files_only=True)
            except Exception:
                if not allow_download:
                    raise
                _restore_env(previous_env)
                model = GLiNER.from_pretrained(model_id)
        except Exception:
            if not allow_download:
                raise
            raise
        finally:
            _restore_env(previous_env)
        model = model.to("cuda")
        _model_cache[cache_key] = model
        logger.info("GLiNER ready: model=%s device=%s", model_id, device)
        return model
    except Exception as exc:
        logger.warning("GLiNER load failed (%s on %s): %s", model_id, device, exc)
        return None


# Return entity-density score [0.0, 1.0] for each paragraph.
def score_entity_density(
    paragraphs: list[str],
    device: str = "cuda",
    threshold: float = 0.35,
    cpu_para_limit: int = 6,
) -> list[float]:
    scored = score_entity_density_with_entities(
        paragraphs,
        device=device,
        threshold=threshold,
        cpu_para_limit=cpu_para_limit,
    )
    return [score for score, _ in scored]


# Normalize raw GLiNER entity dicts to a consistent shape.
def _normalize_entities(raw_entities: list[dict]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for e in raw_entities:
        if not isinstance(e, dict):
            continue
        text_val = str(e.get("text", "")).strip()
        label_val = str(e.get("label", "")).strip()
        score_val = e.get("score", e.get("confidence", 0.0))
        if not text_val or not label_val:
            continue
        try:
            score_float = round(float(score_val), 3)
        except Exception:
            score_float = 0.0
        normalized.append({"text": text_val, "label": label_val, "score": score_float})
    return normalized


# Return entity-density score and normalized entities for each paragraph.
def score_entity_density_with_entities(
    paragraphs: list[str],
    labels: list[str] | None = None,
    device: str = "cuda",
    threshold: float = 0.35,
    cpu_para_limit: int = 6,
) -> list[tuple[float, list[dict[str, Any]]]]:
    if not paragraphs:
        return []

    model = _load_model(device)
    if model is None:
        return [(0.0, []) for _ in paragraphs]

    active_labels = labels or _ENTITY_LABELS
    scored: list[tuple[float, list[dict[str, Any]]]] = []
    limit = len(paragraphs) if device == "cuda" else cpu_para_limit

    try:
        for idx, para in enumerate(paragraphs):
            if idx >= limit or not para.strip():
                scored.append((0.0, []))
                continue
            raw_entities = model.predict_entities(para, active_labels, threshold=threshold)
            entities = _normalize_entities(raw_entities)
            unique = len({e["text"].lower() for e in entities})
            density = unique / max(50, len(para)) * 100
            scored.append((min(density, 1.0), entities))
    except Exception as exc:
        logger.warning("GLiNER scoring error: %s", exc)
        scored.extend([(0.0, [])] * (len(paragraphs) - len(scored)))

    return scored


# Per-domain label presets for focused NER extraction.
LABELS_BY_DOMAIN: dict[str, list[str]] = {
    "general": ["person", "organization", "location", "date", "money", "product"],
    "technical": [
        "company", "product", "technology", "programming language",
        "software", "hardware", "version",
    ],
    "finance": ["company", "revenue", "profit", "stock price", "market cap", "percentage", "currency"],
    "academic": ["researcher", "institution", "method", "finding", "dataset", "metric"],
    "medical": ["gene", "protein", "biomarker", "cancer type", "antibody", "diagnosis", "treatment", "drug"],
    "journalistic": ["person", "organization", "location", "date", "event", "money"],
}

_DR_THRESHOLD: float = float(os.getenv("ASLM_GLINER_THRESHOLD", "0.35"))
_DR_THRESHOLD_RU: float = float(os.getenv("ASLM_GLINER_THRESHOLD_RU", "0.28"))


# Choose GLiNER label set from explicit or inferred query type.
def get_labels_for_query(
    query: str,
    query_type: str | None = None,
) -> list[str]:
    if query_type and query_type in LABELS_BY_DOMAIN:
        return LABELS_BY_DOMAIN[query_type]
    q = query.lower()
    if any(k in q for k in ("api", "code", "python", "github", "library", "framework")):
        return LABELS_BY_DOMAIN["technical"]
    if any(k in q for k in ("revenue", "market", "stock", "invest", "profit")):
        return LABELS_BY_DOMAIN["finance"]
    if any(k in q for k in ("paper", "research", "study", "experiment")):
        return LABELS_BY_DOMAIN["academic"]
    if any(k in q for k in ("patient", "disease", "treatment", "clinical")):
        return LABELS_BY_DOMAIN["medical"]
    return LABELS_BY_DOMAIN["general"]


# Return (passes_threshold, entities); used to drop low-information pages.
def check_information_density(
    text: str,
    labels: list[str],
    min_entities: int = 2,
    threshold: float = _DR_THRESHOLD,
    max_length: int = 3000,
    device: str = "cuda",
) -> tuple[bool, list[dict]]:
    model = _load_model(device)
    if model is None:
        return True, []

    chunk = text[:max_length]
    try:
        entities = model.predict_entities(chunk, labels, threshold=threshold)
    except Exception as exc:
        logger.warning("GLiNER check_information_density error: %s", exc)
        return True, []

    normalized = _normalize_entities(entities)
    return len(normalized) >= min_entities, normalized


# Lower GLiNER threshold for Cyrillic-heavy text.
def detect_language_and_adjust_threshold(text: str) -> float:
    cyrillic_count = sum(1 for char in text[:500] if "\u0400" <= char <= "\u04ff")
    if cyrillic_count > 50:
        return _DR_THRESHOLD_RU
    return _DR_THRESHOLD
