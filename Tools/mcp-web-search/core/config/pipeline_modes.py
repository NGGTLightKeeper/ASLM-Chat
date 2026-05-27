"""Canonical search pipeline mode names and backward-compatible aliases.

``rules`` — rules/class_profiles routing only; ASLM embedding models are not loaded.

``aslm_embedding`` — same search stack, but on ``effort=high`` encoder/decoder may run
when enabled in config or via ``ASLM_WEB_SEARCH_NEURAL_*`` env vars.
"""

from __future__ import annotations

PIPELINE_MODE_ALIASES: dict[str, str] = {
    "legacy": "rules",
    "rules": "rules",
    "algorithmic": "rules",
    "neural_v2": "aslm_embedding",
    "neural": "aslm_embedding",
    "aslm_embedding": "aslm_embedding",
    "embedding": "aslm_embedding",
}

CANONICAL_PIPELINE_MODES = frozenset({"rules", "aslm_embedding"})

PIPELINE_MODE_CHOICES = tuple(sorted(PIPELINE_MODE_ALIASES))


def normalize_pipeline_mode(value: str | None) -> str:
    raw = (value or "rules").strip().lower()
    if not raw:
        return "rules"
    return PIPELINE_MODE_ALIASES.get(raw, raw)
