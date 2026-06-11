# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

# Canonical pipeline mode names: rules (profiles only) and aslm_embedding (optional neural on high effort).
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


# Map config/env aliases to a canonical pipeline mode string.
def normalize_pipeline_mode(value: str | None) -> str:
    raw = (value or "rules").strip().lower()
    if not raw:
        return "rules"
    return PIPELINE_MODE_ALIASES.get(raw, raw)
