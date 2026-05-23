"""Unit tests for file bridge validation and I/O."""
from __future__ import annotations

import base64
import json

import pytest

from .conftest import requires_symlinks
from sandbox_mcp.files import (
    FileBridgeError,
    cleanup_artifacts,
    collect_output_files,
    describe_shared_file,
    format_shared_file_changes,
    list_shared_files,
    normalize_shared_path,
    prepare_run_layout,
    read_output_file,
    safe_filename,
    save_artifacts,
    shared_file_snapshot,
    shared_root,
    stage_input_files,
    upload_file,
    validate_filename_list,
    validate_run_id,
    validate_session_id,
)


def test_safe_filename_rejects_traversal(bridge_dirs):
    with pytest.raises(FileBridgeError):
        safe_filename("../../etc/passwd")
    with pytest.raises(FileBridgeError):
        safe_filename("noext")
    with pytest.raises(FileBridgeError):
        safe_filename("/tmp/foo.json")
    assert safe_filename("data.csv") == "data.csv"


def test_validate_session_id(bridge_dirs):
    sid = validate_session_id(None)
    assert len(sid) == 32
    with pytest.raises(FileBridgeError):
        validate_session_id("not-hex")


def test_upload_and_stage(bridge_dirs):
    body = b"col1,col2\n1,2\n"
    meta = upload_file(None, "data.csv", base64.b64encode(body).decode())
    sid = meta["session_id"]

    run_dir = bridge_dirs["runs"] / "testrun01"
    run_dir.mkdir()
    prepare_run_layout(run_dir)
    staged = stage_input_files(run_dir, sid, ["data.csv"])
    assert staged == ["data.csv"]
    assert (run_dir / "input" / "data.csv").read_bytes() == body


def test_collect_output_and_artifacts(bridge_dirs):
    run_dir = bridge_dirs["runs"] / "outrun"
    prepare_run_layout(run_dir)
    (run_dir / "output" / "result.txt").write_text("ok", encoding="utf-8")

    data = collect_output_files(run_dir, ["result.txt"])
    assert data["result.txt"] == b"ok"

    run_id = "a" * 32
    save_artifacts(
        run_id,
        exit_code=0,
        session_id=None,
        inputs=[],
        outputs=data,
        stdout="hi",
        stderr="",
        timed_out=False,
    )

    payload, manifest = read_output_file(run_id, "result.txt")
    assert payload == b"ok"
    assert manifest["output_files"] == ["result.txt"]

    cleanup_artifacts(run_id)
    with pytest.raises(FileBridgeError):
        read_output_file(run_id, "result.txt")


def test_read_output_rejects_undeclared(bridge_dirs):
    run_id = "b" * 32
    save_artifacts(
        run_id,
        exit_code=0,
        session_id=None,
        inputs=[],
        outputs={"a.txt": b"x"},
        stdout="",
        stderr="",
        timed_out=False,
    )
    with pytest.raises(FileBridgeError):
        read_output_file(run_id, "other.txt")


def test_upload_size_limit(bridge_dirs, monkeypatch):
    monkeypatch.setenv("SANDBOX_MAX_FILE_BYTES", "10")
    big = base64.b64encode(b"x" * 20).decode()
    with pytest.raises(FileBridgeError, match="too large"):
        upload_file(None, "big.csv", big)


def test_input_files_require_session(bridge_dirs):
    from sandbox_mcp.runner import parse_run_request

    with pytest.raises(FileBridgeError):
        parse_run_request(
            {"cmd": ["echo", "hi"], "input_files": ["data.csv"]},
        )


def test_validate_filename_list_cap(bridge_dirs, monkeypatch):
    monkeypatch.setenv("SANDBOX_MAX_FILES_PER_LIST", "2")
    with pytest.raises(FileBridgeError):
        validate_filename_list(["a.csv", "b.csv", "c.csv"], label="input_files")


def test_validate_run_id():
    validate_run_id("c" * 32)
    with pytest.raises(FileBridgeError):
        validate_run_id("short")


def test_shared_file_description_stays_inside_sandbox(bridge_dirs):
    target = bridge_dirs["shared"] / "report.csv"
    target.write_text("a,b\n1,2\n", encoding="utf-8")

    meta = describe_shared_file("/mnt/data/_sandbox/report.csv")

    assert meta["kind"] == "shared_file"
    assert meta["path"] == "report.csv"
    assert meta["container_path"] == "/mnt/data/_sandbox/report.csv"
    assert meta["host_path"] == str(target.resolve())
    assert meta["mime_type"] == "text/csv"
    assert meta["size_bytes"] == target.stat().st_size


def test_shared_file_rejects_traversal_and_absolute_host_paths(bridge_dirs):
    with pytest.raises(FileBridgeError):
        normalize_shared_path("../secret.txt")
    with pytest.raises(FileBridgeError):
        normalize_shared_path("/etc/passwd")
    with pytest.raises(FileBridgeError):
        normalize_shared_path("C:/Users/dimap/secret.txt")


def test_list_shared_files_skips_symlink_without_following(bridge_dirs):
    root = shared_root()
    (root / "ok.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    link = root / "bad-link.txt"
    try:
        link.symlink_to(root / "ok.csv")
    except (OSError, NotImplementedError):
        link = None

    listing = list_shared_files()

    assert [item["path"] for item in listing["files"]] == ["ok.csv"]
    if link is not None:
        assert any(item["path"] == "bad-link.txt" for item in listing["skipped"])


def test_shared_file_changes_summary(bridge_dirs):
    root = shared_root()
    (root / "old.txt").write_text("old", encoding="utf-8")
    before = shared_file_snapshot()
    (root / "new.json").write_text("{}", encoding="utf-8")

    summary = format_shared_file_changes(before, list_shared_files())

    assert "shared_files_changed: new.json" in summary
    assert "share_hint:" in summary


@requires_symlinks
def test_shared_file_rejects_symlink_when_supported(bridge_dirs):
    real = bridge_dirs["shared"] / "real.txt"
    real.write_text("ok", encoding="utf-8")
    link = bridge_dirs["shared"] / "link.txt"
    link.symlink_to(real)

    with pytest.raises(FileBridgeError, match="symlink"):
        describe_shared_file("link.txt")
