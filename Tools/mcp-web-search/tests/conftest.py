# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

from pathlib import Path

import pytest


def aslm_embedding_exports_available() -> bool:
    """True when both on-disk ASLM export dirs contain labels.json."""
    from core.query.aslm_embedding_runtime import (
        default_query_classifier_path,
        default_source_relevance_path,
    )

    enc = default_query_classifier_path()
    dec = default_source_relevance_path()
    return (enc / "labels.json").is_file() and (dec / "labels.json").is_file()


requires_aslm_models = pytest.mark.skipif(
    not aslm_embedding_exports_available(),
    reason="ASLM embedding exports missing under Tools/mcp-web-search/models/",
)
