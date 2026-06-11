# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from pathlib import Path

import pytest

from core.query.aslm_embedding_models import (
    DECODER_DIR_NAME,
    DECODER_REPO_ID,
    ENCODER_DIR_NAME,
    ENCODER_REPO_ID,
    MODELS_DIR,
    decoder_export_path,
    encoder_export_path,
    export_is_complete,
)


@pytest.mark.unit
def test_embedding_model_constants() -> None:
    assert ENCODER_REPO_ID == "NEXTGGTECH/ASLM-Chat-WS-Embedding-1-97m-encoder"
    assert DECODER_REPO_ID == "NEXTGGTECH/ASLM-Chat-WS-Embedding-1-97m-decoder"
    assert ENCODER_DIR_NAME == "ASLM-Chat-WS-Embedding-1-97m-encoder"
    assert DECODER_DIR_NAME == "ASLM-Chat-WS-Embedding-1-97m-decoder"


@pytest.mark.unit
def test_export_paths_under_models_dir() -> None:
    assert encoder_export_path().parent == MODELS_DIR
    assert decoder_export_path().parent == MODELS_DIR
    assert encoder_export_path().name == ENCODER_DIR_NAME
    assert decoder_export_path().name == DECODER_DIR_NAME


@pytest.mark.unit
def test_export_is_complete_requires_artifacts(tmp_path: Path) -> None:
    assert not export_is_complete(tmp_path)

    (tmp_path / "labels.json").write_text("[]", encoding="utf-8")
    assert not export_is_complete(tmp_path)

    (tmp_path / "model.pt").write_bytes(b"")
    assert not export_is_complete(tmp_path)

    (tmp_path / "encoder").mkdir()
    assert export_is_complete(tmp_path)
