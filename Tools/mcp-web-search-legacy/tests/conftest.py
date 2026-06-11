# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

from pathlib import Path

import pytest


# True when both on-disk ASLM export dirs are complete.

def aslm_embedding_exports_available() -> bool:
    from core.query.aslm_embedding_models import (
        export_is_complete,
        encoder_export_path,
        decoder_export_path,
    )

    return export_is_complete(encoder_export_path()) and export_is_complete(
        decoder_export_path()
    )


requires_aslm_models = pytest.mark.skipif(
    not aslm_embedding_exports_available(),
    reason=(
        "ASLM embedding exports missing under Tools/mcp-web-search/models/"
        " (ASLM-Chat-WS-Embedding-1-97m-encoder / -decoder)"
    ),
)
