# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from core.query.aslm_embedding_models import (
    DECODER_DIR_NAME,
    DECODER_REPO_ID,
    ENCODER_DIR_NAME,
    ENCODER_REPO_ID,
    LEGACY_DECODER_DIR_NAME,
    LEGACY_ENCODER_DIR_NAME,
    MODELS_DIR,
    decoder_export_path,
    encoder_export_path,
    export_is_complete,
)

logger = logging.getLogger("core.query.aslm_embedding_bootstrap")


# Download HF snapshot (separate helper for tests).
def _snapshot_download(repo_id: str, local_dir: str) -> None:
    from huggingface_hub import snapshot_download

    snapshot_download(repo_id=repo_id, local_dir=local_dir)


# Rename legacy export dirs when the new names are not present yet.
def maybe_migrate_legacy_dirs() -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    migrations = (
        (LEGACY_ENCODER_DIR_NAME, ENCODER_DIR_NAME),
        (LEGACY_DECODER_DIR_NAME, DECODER_DIR_NAME),
    )
    for legacy_name, new_name in migrations:
        legacy = MODELS_DIR / legacy_name
        target = MODELS_DIR / new_name
        if legacy.is_dir() and not target.exists():
            logger.info("Migrating legacy ASLM embedding export %s -> %s", legacy, target)
            legacy.rename(target)


# Download one HF repo into local_dir when the export is incomplete.
def ensure_embedding_export(repo_id: str, local_dir: Path) -> None:
    if export_is_complete(local_dir):
        logger.info("ASLM embedding export already present: %s", local_dir)
        return

    local_dir.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Downloading ASLM embedding export from Hugging Face: %s -> %s", repo_id, local_dir)

    _snapshot_download(repo_id=repo_id, local_dir=str(local_dir))

    if not export_is_complete(local_dir):
        raise RuntimeError(f"Incomplete ASLM embedding export at {local_dir}")


# Ensure encoder and decoder exports exist under Tools/mcp-web-search/models/.
def ensure_aslm_embedding_models() -> None:
    maybe_migrate_legacy_dirs()
    with ThreadPoolExecutor(max_workers=2) as executor:
        encoder_future = executor.submit(
            ensure_embedding_export, ENCODER_REPO_ID, encoder_export_path()
        )
        decoder_future = executor.submit(
            ensure_embedding_export, DECODER_REPO_ID, decoder_export_path()
        )
        encoder_future.result()
        decoder_future.result()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ensure_aslm_embedding_models()
