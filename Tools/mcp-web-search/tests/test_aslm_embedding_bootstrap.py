# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from pathlib import Path
from unittest.mock import patch

import pytest

from core.query import aslm_embedding_bootstrap as bootstrap
from core.query.aslm_embedding_models import (
    DECODER_DIR_NAME,
    ENCODER_DIR_NAME,
    LEGACY_DECODER_DIR_NAME,
    LEGACY_ENCODER_DIR_NAME,
    export_is_complete,
)


@pytest.mark.unit
def test_maybe_migrate_legacy_dirs_renames_when_target_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bootstrap, "MODELS_DIR", tmp_path)
    legacy = tmp_path / LEGACY_ENCODER_DIR_NAME
    legacy.mkdir()
    (legacy / "labels.json").write_text("[]", encoding="utf-8")

    bootstrap.maybe_migrate_legacy_dirs()

    assert not legacy.exists()
    assert (tmp_path / ENCODER_DIR_NAME).is_dir()
    assert (tmp_path / ENCODER_DIR_NAME / "labels.json").is_file()


@pytest.mark.unit
def test_maybe_migrate_legacy_dirs_skips_when_target_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bootstrap, "MODELS_DIR", tmp_path)
    legacy = tmp_path / LEGACY_DECODER_DIR_NAME
    target = tmp_path / DECODER_DIR_NAME
    legacy.mkdir()
    target.mkdir()
    (legacy / "labels.json").write_text("legacy", encoding="utf-8")
    (target / "labels.json").write_text("new", encoding="utf-8")

    bootstrap.maybe_migrate_legacy_dirs()

    assert legacy.is_dir()
    assert (target / "labels.json").read_text(encoding="utf-8") == "new"


@pytest.mark.unit
def test_ensure_embedding_export_skips_when_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    export_dir = tmp_path / "export"
    export_dir.mkdir()
    (export_dir / "labels.json").write_text("[]", encoding="utf-8")
    (export_dir / "model.pt").write_bytes(b"")
    (export_dir / "encoder").mkdir()

    with patch.object(bootstrap, "_snapshot_download") as download:
        bootstrap.ensure_embedding_export("NEXTGGTECH/example", export_dir)

    download.assert_not_called()


@pytest.mark.unit
def test_ensure_embedding_export_downloads_when_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    export_dir = tmp_path / "export"

    def fake_download(*, repo_id: str, local_dir: str) -> None:
        path = Path(local_dir)
        path.mkdir(parents=True, exist_ok=True)
        (path / "labels.json").write_text("[]", encoding="utf-8")
        (path / "model.pt").write_bytes(b"")
        (path / "encoder").mkdir()

    with patch.object(bootstrap, "_snapshot_download", side_effect=fake_download) as download:
        bootstrap.ensure_embedding_export("NEXTGGTECH/example", export_dir)

    download.assert_called_once_with(repo_id="NEXTGGTECH/example", local_dir=str(export_dir))
    assert export_is_complete(export_dir)


@pytest.mark.unit
def test_ensure_embedding_export_raises_when_still_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    export_dir = tmp_path / "export"

    with patch.object(bootstrap, "_snapshot_download"):
        with pytest.raises(RuntimeError, match="Incomplete ASLM embedding export"):
            bootstrap.ensure_embedding_export("NEXTGGTECH/example", export_dir)


@pytest.mark.unit
def test_ensure_aslm_embedding_models_calls_both_exports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    monkeypatch.setattr(bootstrap, "maybe_migrate_legacy_dirs", lambda: None)

    def fake_ensure(repo_id: str, local_dir: Path) -> None:
        calls.append(repo_id)

    monkeypatch.setattr(bootstrap, "ensure_embedding_export", fake_ensure)

    bootstrap.ensure_aslm_embedding_models()

    assert calls == [
        "NEXTGGTECH/ASLM-Chat-WS-Embedding-1-97m-encoder",
        "NEXTGGTECH/ASLM-Chat-WS-Embedding-1-97m-decoder",
    ]
