# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

from pathlib import Path

MODELS_DIR = Path(__file__).resolve().parents[2] / "models"

ENCODER_DIR_NAME = "ASLM-Chat-WS-Embedding-1-97m-encoder"
DECODER_DIR_NAME = "ASLM-Chat-WS-Embedding-1-97m-decoder"

ENCODER_REPO_ID = "NEXTGGTECH/ASLM-Chat-WS-Embedding-1-97m-encoder"
DECODER_REPO_ID = "NEXTGGTECH/ASLM-Chat-WS-Embedding-1-97m-decoder"

LEGACY_ENCODER_DIR_NAME = "aslm_embedding_encoder"
LEGACY_DECODER_DIR_NAME = "aslm_embedding_decoder"


# True when an on-disk ASLM embedding export has required artifacts.
def export_is_complete(path: Path) -> bool:
    if not path.is_dir():
        return False
    return (
        (path / "labels.json").is_file()
        and (path / "model.pt").is_file()
        and (path / "encoder").is_dir()
    )


# Default on-disk path for query classifier (encoder) export.
def encoder_export_path(root: str | Path | None = None) -> Path:
    base = Path(root) if root is not None else MODELS_DIR
    return base / ENCODER_DIR_NAME


# Default on-disk path for source relevance (decoder) export.
def decoder_export_path(root: str | Path | None = None) -> Path:
    base = Path(root) if root is not None else MODELS_DIR
    return base / DECODER_DIR_NAME
