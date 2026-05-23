"""Cleanup tests for tmp roots, archives, and trash handoff."""
from __future__ import annotations

import os
import time
import zipfile
from pathlib import Path

from sandbox_mcp import files
from sandbox_mcp import runner

from .conftest import requires_symlinks


def _uuid_dir(root: Path, char: str = "a") -> Path:
    path = root / (char * 32)
    path.mkdir(parents=True)
    return path


def test_cleanup_run_dir_archives_then_sends_to_trash(bridge_dirs, monkeypatch):
    trashed: list[Path] = []

    def fake_trash(path: Path) -> None:
        trashed.append(path)

    monkeypatch.setenv("SANDBOX_ARCHIVE_RUNS", "1")
    monkeypatch.setattr(runner, "send_to_trash", fake_trash)
    run_dir = _uuid_dir(bridge_dirs["runs"])
    (run_dir / "work").mkdir()
    (run_dir / "work" / "script.py").write_text("print('ok')", encoding="utf-8")
    (run_dir / "output").mkdir()
    (run_dir / "output" / "result.txt").write_text("ok", encoding="utf-8")

    runner._cleanup_run_dir(run_dir)

    assert trashed == [run_dir]
    archives = list((bridge_dirs["archive"] / "runs").glob("*.zip"))
    assert len(archives) == 1
    run_archive = archives[0]
    with zipfile.ZipFile(run_archive) as zf:
        assert sorted(zf.namelist()) == ["output/result.txt", "work/script.py"]


def test_cleanup_run_dir_can_skip_archive(bridge_dirs, monkeypatch):
    trashed: list[Path] = []
    monkeypatch.setenv("SANDBOX_ARCHIVE_RUNS", "0")
    monkeypatch.setattr(runner, "send_to_trash", lambda path: trashed.append(path))
    run_dir = _uuid_dir(bridge_dirs["runs"])
    (run_dir / "work.txt").write_text("debug", encoding="utf-8")

    runner._cleanup_run_dir(run_dir)

    assert trashed == [run_dir]
    assert not list(bridge_dirs["archive"].rglob("*.zip"))


def test_cleanup_old_state_sends_expired_dirs_and_archives_to_trash(bridge_dirs, monkeypatch):
    trashed: list[Path] = []
    monkeypatch.setattr(files, "send_to_trash", lambda path: trashed.append(path))
    monkeypatch.setattr(runner, "send_to_trash", lambda path: trashed.append(path))
    monkeypatch.setenv("SANDBOX_SESSION_IDLE_SECONDS", "60")
    monkeypatch.setenv("SANDBOX_STAGING_TTL_SECONDS", "60")
    monkeypatch.setenv("SANDBOX_ARTIFACTS_TTL_SECONDS", "60")
    monkeypatch.setenv("SANDBOX_ARCHIVE_TTL_SECONDS", "60")

    old_mtime = time.time() - 120
    run_dir = _uuid_dir(bridge_dirs["runs"], "b")
    staging_dir = _uuid_dir(bridge_dirs["staging"], "c")
    artifact_dir = _uuid_dir(bridge_dirs["artifacts"], "d")
    archive_dir = bridge_dirs["archive"] / "runs"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_file = archive_dir / "old.zip"
    archive_file.write_bytes(b"zip-ish")
    for path in (run_dir, staging_dir, artifact_dir, archive_file):
        os.utime(path, (old_mtime, old_mtime))

    runner._cleanup_old_state()

    assert set(trashed) == {run_dir, staging_dir, artifact_dir, archive_file}


def test_active_run_dir_reuses_session_until_idle(bridge_dirs, monkeypatch):
    trashed: list[Path] = []
    monkeypatch.setenv("SANDBOX_SESSION_IDLE_SECONDS", "60")
    monkeypatch.setattr(runner, "send_to_trash", lambda path: trashed.append(path))
    now = [1_000.0]
    monkeypatch.setattr(runner.time, "time", lambda: now[0])
    monkeypatch.setattr(files.time, "time", lambda: now[0])

    first_id, first_dir = runner._get_active_run_dir()
    now[0] += 30
    second_id, second_dir = runner._get_active_run_dir()

    assert second_id == first_id
    assert second_dir == first_dir
    assert trashed == []

    now[0] += 61
    third_id, third_dir = runner._get_active_run_dir()

    assert third_id != first_id
    assert third_dir != first_dir
    assert trashed == [first_dir]
    assert not list((bridge_dirs["archive"] / "runs").glob(f"*-{first_id}.zip"))


@requires_symlinks
def test_archive_tree_skips_symlinks_when_supported(bridge_dirs):
    source = bridge_dirs["runs"] / ("e" * 32)
    source.mkdir()
    (source / "ok.txt").write_text("ok", encoding="utf-8")
    link = source / "link.txt"
    link.symlink_to(source / "ok.txt")

    archive = files.archive_tree(source, "runs")

    assert archive is not None
    with zipfile.ZipFile(archive) as zf:
        names = sorted(zf.namelist())
    assert "ok.txt" in names
    assert "link.txt.skipped.txt" in names
