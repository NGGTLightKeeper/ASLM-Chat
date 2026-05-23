"""Shared fixtures: isolated staging/runs/artifacts dirs."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def symlinks_supported() -> bool:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        target = root / "target.txt"
        target.write_text("ok", encoding="utf-8")
        link = root / "link.txt"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            return False
        return link.is_symlink()


requires_symlinks = pytest.mark.skipif(
    not symlinks_supported(),
    reason="OS user cannot create symlinks (enable Developer Mode on Windows)",
)


@pytest.fixture
def bridge_dirs(tmp_path, monkeypatch):
    """Point file bridge + runner roots at a temp directory."""
    root = tmp_path / "sandbox-data"
    tmp_root = root / "tmp"
    runs = root / "runs"
    staging = root / "staging"
    artifacts = root / "artifacts"
    archive = root / "archive"
    shared = root / "_sandbox"
    for p in (tmp_root, runs, staging, artifacts, archive, shared):
        p.mkdir(parents=True)

    monkeypatch.setenv("SANDBOX_TMP_ROOT", str(tmp_root))
    monkeypatch.setenv("SANDBOX_RUNS_ROOT", str(runs))
    monkeypatch.setenv("SANDBOX_STAGING_ROOT", str(staging))
    monkeypatch.setenv("SANDBOX_ARTIFACTS_ROOT", str(artifacts))
    monkeypatch.setenv("SANDBOX_ARCHIVE_ROOT", str(archive))
    monkeypatch.setenv("SANDBOX_SHARED_ROOT", str(shared))
    monkeypatch.setenv("SANDBOX_MAX_FILE_BYTES", "1048576")
    monkeypatch.setenv("SANDBOX_MAX_OUTPUT_TOTAL_BYTES", "1048576")
    monkeypatch.setenv("SANDBOX_MAX_FILES_PER_LIST", "5")
    monkeypatch.delenv("SANDBOX_KEEP_RUN_DIR", raising=False)
    monkeypatch.delenv("SANDBOX_ARCHIVE_RUNS", raising=False)

    from sandbox_mcp import runner

    with runner._SESSION_LOCK:
        runner._ACTIVE_RUN_ID = None
        runner._ACTIVE_RUN_DIR = None
        runner._LAST_ACTIVITY = 0.0

    yield {
        "root": root,
        "tmp": tmp_root,
        "runs": runs,
        "staging": staging,
        "artifacts": artifacts,
        "archive": archive,
        "shared": shared,
    }

    runner._end_active_session()
    with runner._SESSION_LOCK:
        runner._ACTIVE_RUN_ID = None
        runner._ACTIVE_RUN_DIR = None
        runner._LAST_ACTIVITY = 0.0
    shutil.rmtree(root, ignore_errors=True)


def docker_available() -> bool:
    try:
        r = subprocess.run(
            ["docker", "version"],
            capture_output=True,
            timeout=15,
        )
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def image_available(tag: str = "sandbox:latest") -> bool:
    if not docker_available():
        return False
    r = subprocess.run(
        ["docker", "image", "inspect", tag],
        capture_output=True,
        timeout=15,
    )
    return r.returncode == 0


@pytest.fixture(scope="session")
def sandbox_image():
    return os.environ.get("SANDBOX_IMAGE", "sandbox:latest")
