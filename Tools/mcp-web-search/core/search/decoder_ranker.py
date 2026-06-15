# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""CPU decoder content-stage re-ranker (high effort only).

Ports the legacy ASLM source-relevance model loader (ModernBERT encoder + a scalar
score head, exported as labels.json + model.pt + encoder/) but trimmed to what the
new pipeline needs: a single relevance score per (query, source) pair, CPU-only — there
is no CUDA anywhere in this project. torch/transformers are imported lazily on first
load so the SERP-only / medium paths never pay for them, and every failure (missing
model, missing deps, inference error) degrades to "no decoder scores", leaving the
rules ranking (BM25 + consensus + position) in charge.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger("services.web_search")

# On-disk export must carry these (same contract as the legacy export).
def _export_is_complete(path: Path) -> bool:
    return (
        path.is_dir()
        and (path / "labels.json").is_file()
        and (path / "model.pt").is_file()
        and (path / "encoder").is_dir()
    )


# Fixed template the decoder was trained on — keep byte-for-byte with the legacy export.
def format_source_relevance_input(
    *, query: str, title: str, url: str, snippet: str = "", preview: str = ""
) -> str:
    return (
        f"Query: {query}\n"
        f"Title: {title}\n"
        f"URL: {url}\n"
        f"Snippet: {snippet}\n"
        f"Preview: {preview}"
    )


# Loaded ModernBERT encoder + score head. Built lazily; CPU only.
class _DecoderRuntime:
    def __init__(self, export_dir: Path, *, max_length: int = 512) -> None:
        import torch
        import torch.nn as nn
        from transformers import AutoModel, AutoTokenizer

        self._torch = torch
        self.max_length = max_length
        self.labels = json.loads((export_dir / "labels.json").read_text(encoding="utf-8"))
        self.tokenizer = AutoTokenizer.from_pretrained(export_dir / "encoder", local_files_only=True)
        self.encoder = AutoModel.from_pretrained(
            export_dir / "encoder", local_files_only=True, trust_remote_code=True
        )

        hidden = int(self.encoder.config.hidden_size)
        # Only the scalar relevance head is needed here (the label head is unused).
        self.score_head = nn.Sequential(
            nn.Linear(hidden, hidden // 2), nn.SiLU(), nn.Dropout(0.0), nn.Linear(hidden // 2, 1)
        )

        state = torch.load(export_dir / "model.pt", map_location="cpu")
        encoder_state = {
            k[len("encoder.") :]: v for k, v in state.items() if k.startswith("encoder.")
        }
        self.encoder.load_state_dict(encoder_state, strict=True)
        self.score_head[0].load_state_dict(
            {"weight": state["score_head.0.weight"], "bias": state["score_head.0.bias"]}
        )
        self.score_head[3].load_state_dict(
            {"weight": state["score_head.3.weight"], "bias": state["score_head.3.bias"]}
        )
        self.encoder.eval()
        self.score_head.eval()

    # Scalar relevance in [0,1] per input text.
    def scores(self, texts: list[str]) -> list[float]:
        if not texts:
            return []
        torch = self._torch
        with torch.no_grad():
            batch = self.tokenizer(
                texts, padding=True, truncation=True, max_length=self.max_length, return_tensors="pt"
            )
            encoded = self.encoder(**batch)
            pooled = encoded.last_hidden_state[:, 0].float()
            out = torch.sigmoid(self.score_head(pooled)).squeeze(-1)
        return [float(x) for x in out.tolist()]


# Lazy, fail-soft facade over the decoder runtime.
class DecoderRanker:
    def __init__(self, model_dir: str | Path) -> None:
        self._dir = Path(model_dir) if model_dir else None
        self._runtime: Optional[_DecoderRuntime] = None
        self._tried = False
        self._lock = threading.Lock()

    # True when a complete export is on disk (cheap; no model load).
    def available(self) -> bool:
        return self._dir is not None and _export_is_complete(self._dir)

    # Load the runtime once; None when deps/model are missing or load fails.
    def _ensure(self) -> Optional[_DecoderRuntime]:
        if self._runtime is None and not self._tried:
            with self._lock:
                if self._runtime is None and not self._tried:
                    self._tried = True
                    try:
                        self._runtime = _DecoderRuntime(self._dir)  # type: ignore[arg-type]
                        logger.info("decoder re-ranker loaded path=%s", self._dir)
                    except Exception as exc:  # noqa: BLE001 — model is optional
                        logger.warning("decoder load failed path=%s: %s", self._dir, exc)
        return self._runtime

    # Relevance scores for candidates (dicts with title/url/snippet/preview); [] on any miss.
    def score(self, query: str, candidates: list[dict[str, str]]) -> list[float]:
        if not candidates or not self.available():
            return []
        runtime = self._ensure()
        if runtime is None:
            return []
        texts = [
            format_source_relevance_input(
                query=query,
                title=c.get("title", ""),
                url=c.get("url", ""),
                snippet=c.get("snippet", ""),
                preview=c.get("preview", ""),
            )
            for c in candidates
        ]
        try:
            return runtime.scores(texts)
        except Exception as exc:  # noqa: BLE001 — inference failure must not sink the search
            logger.warning("decoder scoring failed: %s", exc)
            return []


_ranker: Optional[DecoderRanker] = None
_ranker_lock = threading.Lock()

# Default export location inside this project (large model; usually pointed elsewhere
# via models.decoder_model_dir). Mirrors the legacy export layout.
_DEFAULT_DIR = Path(__file__).resolve().parents[2] / "models" / "aslm_embedding_decoder"


# Process-wide DecoderRanker, configured from models.decoder_model_dir (or the default).
def get_decoder_ranker() -> DecoderRanker:
    global _ranker
    if _ranker is None:
        with _ranker_lock:
            if _ranker is None:
                from core.config import load_search_config

                configured = (load_search_config().models.decoder_model_dir or "").strip()
                _ranker = DecoderRanker(configured or str(_DEFAULT_DIR))
    return _ranker
