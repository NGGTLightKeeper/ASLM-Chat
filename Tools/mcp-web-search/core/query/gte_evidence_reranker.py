# Copyright NGGT.LightKeeper. All Rights Reserved.

"""Lazy CPU runtime for the fine-tuned GTE evidence-alignment reranker."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("core.query.gte_evidence_reranker")

DEFAULT_MODEL_DIR = Path(__file__).resolve().parents[2] / "models" / "gte_evidence_reranker_full_ft"
_BASE_MODEL_ID = "Alibaba-NLP/gte-multilingual-reranker-base"


def default_model_dir() -> Path:
    raw = os.getenv("ASLM_GTE_EVIDENCE_RERANKER_DIR", "").strip()
    return Path(raw) if raw else DEFAULT_MODEL_DIR


def _model_files_present(model_dir: Path) -> bool:
    if not model_dir.is_dir():
        return False
    names = {path.name for path in model_dir.iterdir()}
    return bool(
        names.intersection({"config.json", "model.safetensors", "pytorch_model.bin", "modules.json"})
        or (model_dir / "0").is_dir()
    )


def _read_manifest(model_dir: Path) -> dict[str, Any]:
    manifest_path = model_dir / "manifest.json"
    if not manifest_path.is_file():
        return {}
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def resolve_reranker_model_id(model_dir: Path | None = None) -> str:
    directory = model_dir or default_model_dir()
    if _model_files_present(directory):
        return str(directory)
    manifest = _read_manifest(directory)
    base_model = str(manifest.get("base_model") or _BASE_MODEL_ID).strip()
    return base_model or _BASE_MODEL_ID


def _patch_position_ids(cross_encoder: Any) -> None:
    """Workaround for PyTorch 2.10+cu128: torch.arange() sometimes leaves the
    first element of a freshly-registered buffer uninitialized (garbage value).
    Scan every submodule and replace any corrupted position_ids tensor."""
    import torch
    patched = 0
    try:
        for _name, module in cross_encoder.model.named_modules():
            buf = getattr(module, "position_ids", None)
            if buf is None or not isinstance(buf, torch.Tensor) or buf.numel() == 0:
                continue
            expected = torch.arange(buf.numel(), dtype=buf.dtype, device=buf.device)
            if not torch.equal(buf, expected):
                module.register_buffer("position_ids", expected, persistent=False)
                patched += 1
        if patched:
            logger.info("GTE patched %d corrupted position_ids buffer(s)", patched)
    except Exception as exc:
        logger.warning("GTE position_ids patch failed: %s", exc)


class LazyGteEvidenceRerankerRuntime:
    """Score (claim, evidence) pairs with a CrossEncoder-style reranker.

    The model is loaded lazily on first use and kept in RAM for ``ttl_seconds``
    after the last call.  A warm_up() method pre-loads the model in a daemon
    thread so the first real scoring call doesn't pay the load cost.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._model: Any | None = None
        self._model_id = ""
        self._timer: threading.Timer | None = None
        self._load_count = 0

    # ------------------------------------------------------------------ lifecycle

    def unload(self) -> None:
        with self._lock:
            if self._model is not None:
                logger.info("GTE status=UNLOADING model_id=%r (TTL expired)", self._model_id)
            self._model = None
            self._model_id = ""
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
        logger.info("GTE status=UNLOADED")

    def _reset_ttl(self, ttl_seconds: float) -> None:
        """(Re)start the unload timer. Must be called while holding self._lock."""
        if self._timer is not None:
            self._timer.cancel()
        effective = max(60.0, ttl_seconds)
        self._timer = threading.Timer(effective, self.unload)
        self._timer.daemon = True
        self._timer.start()
        logger.info("GTE TTL reset to %.0fs", effective)

    # ------------------------------------------------------------------ loading

    def _load_model(self, model_id: str) -> Any:
        from sentence_transformers import CrossEncoder

        allow_download = os.getenv("ASLM_GTE_EVIDENCE_RERANKER_ALLOW_DOWNLOAD", "").strip().lower() in {
            "1", "true", "yes", "on",
        }
        local_only = Path(model_id).is_dir() or not allow_download
        kwargs: dict[str, Any] = {
            "max_length": int(os.getenv("ASLM_GTE_EVIDENCE_RERANKER_MAX_LENGTH", "512")),
            "device": "cpu",
            "trust_remote_code": True,
        }
        if local_only:
            kwargs["local_files_only"] = True

        t0 = time.perf_counter()
        logger.info("GTE status=LOADING model_id=%r local_only=%s", model_id, local_only)
        try:
            model = CrossEncoder(model_id, **kwargs)
        except Exception:
            if local_only and allow_download:
                logger.info("GTE local load failed, retrying with download allowed")
                kwargs.pop("local_files_only", None)
                model = CrossEncoder(model_id, **kwargs)
            else:
                raise

        logger.info("GTE status=LOADED model_id=%r load_time=%.1fs", model_id, time.perf_counter() - t0)
        # Fix corrupted position_ids buffers (PyTorch 2.10+cu128 arange bug).
        _patch_position_ids(model)
        return model

    # ------------------------------------------------------------------ scoring

    def score_evidence(
        self,
        claim: str,
        evidence_sentences: list[str],
        *,
        model_dir: Path | None = None,
        ttl_seconds: float = 240.0,
    ) -> list[float]:
        claim_text = str(claim or "").strip()
        passages = [str(s or "").strip() for s in evidence_sentences if str(s or "").strip()]
        if not claim_text or not passages:
            return [0.0] * len(evidence_sentences)

        model_id = resolve_reranker_model_id(model_dir)
        t0 = time.perf_counter()

        with self._lock:
            if self._model is None or self._model_id != model_id:
                logger.info("GTE status=LOADING (on-demand, warm-up not ready) model_id=%r", model_id)
                self._model = self._load_model(model_id)
                self._model_id = model_id
                self._load_count += 1
            else:
                logger.debug("GTE status=READY model_id=%r load_count=%d", self._model_id, self._load_count)
            self._reset_ttl(ttl_seconds)

            pairs = [[claim_text, p] for p in passages]
            try:
                raw_scores = self._model.predict(
                    pairs,
                    batch_size=max(1, int(os.getenv("ASLM_GTE_EVIDENCE_RERANKER_BATCH_SIZE", "8"))),
                    show_progress_bar=False,
                )
            except Exception as exc:
                logger.warning("GTE scoring FAILED: %s", exc)
                return [0.0] * len(evidence_sentences)

        scores = [float(v) for v in raw_scores]
        if len(scores) != len(passages):
            return [0.0] * len(evidence_sentences)

        top = max(scores) if scores else 0.0
        logger.info(
            "GTE scored pairs=%d elapsed=%.3fs top_score=%.4f claim_preview=%r",
            len(pairs), time.perf_counter() - t0, top, claim_text[:80],
        )

        out: list[float] = []
        i = 0
        for s in evidence_sentences:
            if str(s or "").strip():
                out.append(scores[i])
                i += 1
            else:
                out.append(0.0)
        return out

    # ------------------------------------------------------------------ warm-up

    def warm_up(self, model_dir: Path | None = None, ttl_seconds: float = 300.0) -> None:
        """Pre-load the model in a daemon thread.  Safe to call repeatedly."""

        def _load() -> None:
            try:
                model_id = resolve_reranker_model_id(model_dir)
                with self._lock:
                    if self._model is not None and self._model_id == model_id:
                        logger.info("GTE warm-up: already loaded, refreshing TTL model_id=%r", model_id)
                        self._reset_ttl(ttl_seconds)
                        return
                # Load OUTSIDE the lock so score_evidence isn't blocked.
                logger.info("GTE warm-up: starting background load model_id=%r", model_id)
                new_model = self._load_model(model_id)
                with self._lock:
                    if self._model is None or self._model_id != model_id:
                        self._model = new_model
                        self._model_id = model_id
                        self._load_count += 1
                    self._reset_ttl(ttl_seconds)
                logger.info("GTE status=READY (warm-up complete) model_id=%r ttl=%.0fs", model_id, ttl_seconds)
            except Exception as exc:
                logger.warning("GTE warm-up FAILED: %s", exc, exc_info=True)

        t = threading.Thread(target=_load, daemon=True, name="gte-warm-up")
        t.start()
        logger.info("GTE warm-up thread started")


# Module-level singleton and convenience wrapper.
runtime = LazyGteEvidenceRerankerRuntime()


def warm_up(model_dir: Path | None = None, ttl_seconds: float = 300.0) -> None:
    """Trigger background GTE model pre-load. Safe to call multiple times."""
    runtime.warm_up(model_dir=model_dir, ttl_seconds=ttl_seconds)
