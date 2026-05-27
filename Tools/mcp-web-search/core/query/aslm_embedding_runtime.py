"""Optional runtime loader for local ASLM embedding search model exports.

The exports in ``models/`` contain a ModernBERT encoder plus two small heads:

* ``label_head`` for taxonomy label probabilities.
* ``score_head`` for a scalar confidence/relevance score.

This module is intentionally dependency-light at import time. Torch and
Transformers are imported only when a model is loaded so normal search tests do
not need the neural stack.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable

logger = logging.getLogger("core.query.aslm_embedding_runtime")


DEFAULT_MODELS_DIR = Path(__file__).resolve().parents[2] / "models"


def _env_component_enabled(name: str, *, default: bool = True) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off", "disabled"}


@dataclass(frozen=True)
class AslmEmbeddingPrediction:
    labels: dict[str, float]
    score: float

    def top(self, limit: int = 5) -> list[tuple[str, float]]:
        return sorted(self.labels.items(), key=lambda item: item[1], reverse=True)[:limit]


class AslmEmbeddingRuntime:
    """Run one local ASLM embedding export on CPU/GPU through Transformers."""

    def __init__(self, export_dir: str | Path, *, device: str = "cpu", max_length: int = 512) -> None:
        self.export_dir = Path(export_dir)
        self.device = device
        self.max_length = max_length

        try:
            import torch
            import torch.nn as nn
            from transformers import AutoModel, AutoTokenizer
        except Exception as exc:  # pragma: no cover - exercised by optional eval only
            raise RuntimeError(
                "ASLM embedding runtime requires torch and transformers to be installed"
            ) from exc

        self._torch = torch
        self.labels = json.loads((self.export_dir / "labels.json").read_text(encoding="utf-8"))
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.export_dir / "encoder",
            local_files_only=True,
        )
        self.encoder = AutoModel.from_pretrained(
            self.export_dir / "encoder",
            local_files_only=True,
            trust_remote_code=True,
        )

        hidden = int(self.encoder.config.hidden_size)
        self.label_head = nn.Linear(hidden, len(self.labels))
        self.score_head = nn.Sequential(
            nn.Linear(hidden, hidden // 2),
            nn.SiLU(),
            nn.Dropout(0.0),
            nn.Linear(hidden // 2, 1),
        )

        state = torch.load(self.export_dir / "model.pt", map_location="cpu")
        encoder_state = {
            key[len("encoder.") :]: value
            for key, value in state.items()
            if key.startswith("encoder.")
        }
        self.encoder.load_state_dict(encoder_state, strict=True)
        self.label_head.load_state_dict(
            {"weight": state["label_head.weight"], "bias": state["label_head.bias"]}
        )
        self.score_head[0].load_state_dict(
            {"weight": state["score_head.0.weight"], "bias": state["score_head.0.bias"]}
        )
        self.score_head[3].load_state_dict(
            {"weight": state["score_head.3.weight"], "bias": state["score_head.3.bias"]}
        )

        self.encoder.to(device)
        self.label_head.to(device)
        self.score_head.to(device)
        self.encoder.eval()
        self.label_head.eval()
        self.score_head.eval()

    def predict(self, texts: Iterable[str]) -> list[AslmEmbeddingPrediction]:
        torch = self._torch
        items = list(texts)
        if not items:
            return []

        with torch.no_grad():
            batch = self.tokenizer(
                items,
                padding=True,
                truncation=True,
                max_length=self.max_length,
                return_tensors="pt",
            )
            batch = {key: value.to(self.device) for key, value in batch.items()}
            encoded = self.encoder(**batch)
            pooled = encoded.last_hidden_state[:, 0].float()
            label_probs = torch.sigmoid(self.label_head(pooled)).cpu()
            scalar_scores = torch.sigmoid(self.score_head(pooled)).squeeze(-1).cpu()

        return [
            AslmEmbeddingPrediction(
                labels={
                    label: float(prob)
                    for label, prob in zip(self.labels, row.tolist(), strict=True)
                },
                score=float(score),
            )
            for row, score in zip(label_probs, scalar_scores.tolist(), strict=True)
        ]

    def close(self) -> None:
        """Release heavyweight model references and clear CPU/CUDA caches."""
        torch = self._torch
        self.encoder = None
        self.label_head = None
        self.score_head = None
        self.tokenizer = None
        try:
            import gc

            gc.collect()
        except Exception:
            pass
        try:
            if hasattr(torch, "cuda") and torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass


@lru_cache(maxsize=4)
def load_aslm_embedding_export(export_dir: str, *, device: str = "cpu") -> AslmEmbeddingRuntime:
    return AslmEmbeddingRuntime(export_dir, device=device)


class SearchModelSession:
    """Model lifecycle for one search cycle or one batch."""

    def __init__(
        self,
        *,
        load: bool = True,
        device: str = "cpu",
        load_encoder: bool | None = None,
        load_decoder: bool | None = None,
    ) -> None:
        self.load = load
        self.device = _resolve_device(device)
        self.load_encoder = (
            load_encoder
            if load_encoder is not None
            else _env_component_enabled("ASLM_WEB_SEARCH_NEURAL_ENCODER", default=False)
        )
        self.load_decoder = (
            load_decoder
            if load_decoder is not None
            else _env_component_enabled("ASLM_WEB_SEARCH_NEURAL_DECODER", default=False)
        )
        self.encoder: AslmEmbeddingRuntime | None = None
        self.decoder: AslmEmbeddingRuntime | None = None
        self.encoder_load_error: str | None = None
        self.decoder_load_error: str | None = None
        self.encoder_path: Path | None = None
        self.decoder_path: Path | None = None

    def __enter__(self) -> "SearchModelSession":
        if self.load:
            # Deliberately bypass the lru-cached helper so production search
            # cycles can unload models at cycle end.
            if self.load_encoder:
                self.encoder_path = default_query_classifier_path()
                try:
                    self.encoder = AslmEmbeddingRuntime(self.encoder_path, device=self.device)
                    logger.info(
                        "ASLM encoder loaded path=%s device=%s labels=%d",
                        self.encoder_path,
                        self.device,
                        len(self.encoder.labels),
                    )
                except Exception as exc:
                    self.encoder_load_error = f"{type(exc).__name__}: {exc}"
                    logger.error(
                        "ASLM encoder failed to load path=%s device=%s: %s",
                        self.encoder_path,
                        self.device,
                        exc,
                        exc_info=True,
                    )
            if self.load_decoder:
                self.decoder_path = default_source_relevance_path()
                try:
                    self.decoder = AslmEmbeddingRuntime(self.decoder_path, device=self.device)
                    logger.info(
                        "ASLM decoder loaded path=%s device=%s labels=%d",
                        self.decoder_path,
                        self.device,
                        len(self.decoder.labels),
                    )
                except Exception as exc:
                    self.decoder_load_error = f"{type(exc).__name__}: {exc}"
                    logger.error(
                        "ASLM decoder failed to load path=%s device=%s: %s",
                        self.decoder_path,
                        self.device,
                        exc,
                        exc_info=True,
                    )
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @property
    def ready(self) -> bool:
        return self.encoder is not None or self.decoder is not None

    def close(self) -> None:
        if self.encoder is not None:
            self.encoder.close()
        if self.decoder is not None:
            self.decoder.close()
        self.encoder = None
        self.decoder = None

    def classify_query(self, query: str) -> AslmEmbeddingPrediction | None:
        if self.encoder is None:
            return None
        return self.encoder.predict([query])[0]

    def score_snippet_candidates(
        self, query: str, candidates: Iterable[dict[str, str]]
    ) -> list[AslmEmbeddingPrediction]:
        if self.decoder is None:
            return []
        texts = [
            format_source_relevance_input(
                query=query,
                title=str(item.get("title", "")),
                url=str(item.get("url", "")),
                snippet=str(item.get("snippet", "")),
                preview="",
            )
            for item in candidates
        ]
        return self.decoder.predict(texts)

    def score_parsed_candidates(
        self, query: str, candidates: Iterable[dict[str, str]]
    ) -> list[AslmEmbeddingPrediction]:
        if self.decoder is None:
            return []
        texts = [
            format_source_relevance_input(
                query=query,
                title=str(item.get("title", "")),
                url=str(item.get("url", "")),
                snippet=str(item.get("snippet", "")),
                preview=str(item.get("preview", "")),
            )
            for item in candidates
        ]
        return self.decoder.predict(texts)


def _resolve_device(device: str) -> str:
    requested = (device or "cpu").strip().lower()
    if requested in {"gpu", "cuda:0"}:
        requested = "cuda"
    if requested == "auto":
        try:
            import torch

            return "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            return "cpu"
    if requested == "cuda":
        try:
            import torch

            if torch.cuda.is_available():
                return "cuda"
        except Exception:
            pass
        return "cpu"
    return "cpu"


def default_query_classifier_path(root: str | Path | None = None) -> Path:
    base = Path(root) if root is not None else DEFAULT_MODELS_DIR
    return base / "aslm_embedding_encoder"


def default_source_relevance_path(root: str | Path | None = None) -> Path:
    base = Path(root) if root is not None else DEFAULT_MODELS_DIR
    return base / "aslm_embedding_decoder"


def format_source_relevance_input(
    *,
    query: str,
    title: str,
    url: str,
    snippet: str = "",
    preview: str = "",
) -> str:
    return (
        f"Query: {query}\n"
        f"Title: {title}\n"
        f"URL: {url}\n"
        f"Snippet: {snippet}\n"
        f"Preview: {preview}"
    )
