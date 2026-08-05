# Copyright NEXTGGTECH. Elastic License 2.0.

from __future__ import annotations

import os
import shutil
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

os.environ.setdefault("SANDBOX_HOST_WORKSPACE", str(ROOT))

from sandbox import workspace  # noqa: E402
import sandbox.workspace as workspace_mod  # noqa: E402
from sandbox.workspace import (  # noqa: E402
    read,
    read_image,
    grep,
    ls,
    write,
    edit,
    describe,
    get_secure_task_path,
    validate_model_path,
)


class WorkspaceBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.task_root = workspace.task_root()
        self.task_root.mkdir(parents=True, exist_ok=True)
        for child in list(self.task_root.iterdir()):
            try:
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
            except PermissionError:
                pass

    # Path traversal.

    def test_read_traversal_blocked(self) -> None:
        with self.assertRaises((ValueError, FileNotFoundError)):
            read("../../etc/passwd")

    def test_read_deep_traversal_blocked(self) -> None:
        with self.assertRaises((ValueError, FileNotFoundError)):
            read("../../../Windows/System32/cmd.exe")

    def test_read_nested_traversal_blocked(self) -> None:
        with self.assertRaises((ValueError, FileNotFoundError)):
            read("sub/../../etc/passwd")

    def test_write_absolute_unix_path_blocked(self) -> None:
        with patch.object(workspace_mod, "IN_CONTAINER", False):
            with self.assertRaises((ValueError, FileNotFoundError)):
                write("/etc/passwd", "pwned")

    def test_write_absolute_windows_path_blocked(self) -> None:
        with self.assertRaises((ValueError, FileNotFoundError)):
            write("C:/Windows/System32/evil.txt", "pwned")

    def test_write_traversal_blocked(self) -> None:
        with self.assertRaises((ValueError, FileNotFoundError)):
            write("../escape.txt", "pwned")

    def test_write_deep_traversal_blocked(self) -> None:
        with self.assertRaises((ValueError, FileNotFoundError)):
            write("../../escape.txt", "pwned")

    def test_edit_traversal_blocked(self) -> None:
        with self.assertRaises((ValueError, FileNotFoundError)):
            edit("../escape.txt", "old", "new")

    def test_describe_traversal_blocked(self) -> None:
        with self.assertRaises((ValueError, FileNotFoundError)):
            describe("../../etc/passwd")

    def test_null_byte_in_path_blocked(self) -> None:
        with self.assertRaises((ValueError, OSError)):
            get_secure_task_path("file\x00../etc/passwd")

    # Absolute path rejection.

    def test_validate_rejects_unix_absolute(self) -> None:
        with patch.object(workspace_mod, "IN_CONTAINER", False):
            with self.assertRaises(ValueError):
                validate_model_path("/etc/passwd")

    def test_validate_rejects_windows_absolute(self) -> None:
        with self.assertRaises(ValueError):
            validate_model_path("C:/Users/dimap")

    def test_validate_rejects_workspace_root(self) -> None:
        with patch.object(workspace_mod, "IN_CONTAINER", False):
            with self.assertRaises(ValueError):
                validate_model_path("/workspace")

    # Symlink escape.

    @unittest.skipIf(
        sys.platform == "win32",
        "Symlink creation requires elevated privileges on Windows",
    )
    # read() must reject a symlink inside workspace pointing outside.
    def test_read_symlink_escape_blocked(self) -> None:
        sym = self.task_root / "__sym_escape"
        target = Path("/etc/passwd")
        if not target.exists():
            self.skipTest("/etc/passwd not available on this platform")
        sym.symlink_to(target)
        try:
            with self.assertRaises(ValueError, msg="Symlink escape via read() should raise ValueError"):
                read("__sym_escape")
        finally:
            sym.unlink(missing_ok=True)

    @unittest.skipIf(
        sys.platform == "win32",
        "Symlink creation requires elevated privileges on Windows",
    )
    # write() must reject writing through a symlink pointing outside.
    def test_write_symlink_escape_blocked(self) -> None:
        sym = self.task_root / "__sym_write"
        target = Path("/tmp/sym_write_test")
        sym.symlink_to(target)
        try:
            with self.assertRaises(ValueError, msg="Symlink escape via write() should raise ValueError"):
                write("__sym_write", "pwned")
        finally:
            sym.unlink(missing_ok=True)
            target.unlink(missing_ok=True)

    @unittest.skipIf(
        sys.platform == "win32",
        "Symlink creation requires elevated privileges on Windows",
    )
    # describe() must reject a symlink pointing outside.
    def test_describe_symlink_escape_blocked(self) -> None:
        sym = self.task_root / "__sym_describe"
        target = Path("/etc/passwd")
        if not target.exists():
            self.skipTest("/etc/passwd not available on this platform")
        sym.symlink_to(target)
        try:
            with self.assertRaises(ValueError, msg="Symlink escape via describe() should raise ValueError"):
                describe("__sym_describe")
        finally:
            sym.unlink(missing_ok=True)

    @unittest.skipIf(
        sys.platform == "win32",
        "Symlink creation requires elevated privileges on Windows",
    )
    # Symlinks pointing inside task_root should be allowed.
    def test_symlink_within_workspace_is_allowed(self) -> None:
        real = self.task_root / "real.txt"
        real.write_text("content", encoding="utf-8")
        sym = self.task_root / "__sym_internal"
        sym.symlink_to(real)
        try:
            result = read("__sym_internal")
            self.assertEqual(result["result"]["content"], "content")
        finally:
            sym.unlink(missing_ok=True)
            real.unlink(missing_ok=True)

    @unittest.skipIf(
        sys.platform == "win32",
        "Symlink creation requires elevated privileges on Windows",
    )
    # ls() may report a symlink but must not walk through it.
    def test_ls_does_not_recurse_into_symlink_directory(self) -> None:
        outside = self.task_root.parent / "__outside_ls_target"
        outside.mkdir(exist_ok=True)
        (outside / "secret.txt").write_text("SECRET", encoding="utf-8")
        link = self.task_root / "__ls_link"
        link.symlink_to(outside, target_is_directory=True)
        try:
            result = ls(".", depth=2, include_hidden=True)
            paths = {entry["path"] for entry in result["result"]["entries"]}
            self.assertIn("__ls_link", paths)
            self.assertNotIn("__ls_link/secret.txt", paths)
        finally:
            link.unlink(missing_ok=True)
            shutil.rmtree(outside, ignore_errors=True)

    @unittest.skipIf(
        sys.platform == "win32",
        "Symlink creation requires elevated privileges on Windows",
    )
    # grep() must not read through symlink files that escape task_root.
    def test_grep_symlink_file_escape_blocked(self) -> None:
        outside = self.task_root.parent / "__outside_grep_secret.txt"
        outside.write_text("SECRET", encoding="utf-8")
        link = self.task_root / "__grep_link.txt"
        link.symlink_to(outside)
        try:
            with self.assertRaises(ValueError):
                grep("SECRET", ".")
        finally:
            link.unlink(missing_ok=True)
            outside.unlink(missing_ok=True)

    # In-container absolute path access.

    def test_read_rejects_oversized_file_before_loading(self) -> None:
        big = self.task_root / "big.txt"
        big.write_text("1234567890", encoding="utf-8")
        with patch.object(workspace_mod, "MAX_FILE_READ_BYTES", 4):
            with self.assertRaises(workspace_mod.SandboxToolError) as ctx:
                read("big.txt")
        self.assertEqual(ctx.exception.error_type, "file_too_large")

    def test_grep_skips_oversized_file_before_loading(self) -> None:
        big = self.task_root / "big-grep.txt"
        big.write_text("SECRET-LONG\n", encoding="utf-8")
        small = self.task_root / "small-grep.txt"
        small.write_text("needle\n", encoding="utf-8")

        with patch.object(workspace_mod, "MAX_FILE_READ_BYTES", 8):
            result = grep("needle", ".")

        paths = {match["path"] for match in result["result"]["matches"]}
        self.assertIn("small-grep.txt", paths)
        self.assertTrue(any("big-grep.txt" in warning for warning in result["warnings"]))

    def test_read_image_rejects_non_workspace_absolute_path(self) -> None:
        with patch.object(workspace_mod, "IN_CONTAINER", True):
            with self.assertRaises(ValueError):
                read_image("/etc/passwd")

    def test_validate_allows_absolute_in_container(self) -> None:
        with patch.object(workspace_mod, "IN_CONTAINER", True):
            validate_model_path("/opt/app/config.py")  # must not raise

    def test_validate_allows_slash_tmp_in_container(self) -> None:
        with patch.object(workspace_mod, "IN_CONTAINER", True):
            validate_model_path("/tmp/work/file.txt")  # must not raise

    def test_validate_still_rejects_windows_paths_in_container(self) -> None:
        with patch.object(workspace_mod, "IN_CONTAINER", True):
            with self.assertRaises(ValueError):
                validate_model_path("C:/Users/dimap/evil.txt")

    def test_get_secure_task_path_returns_absolute_in_container(self) -> None:
        with patch.object(workspace_mod, "IN_CONTAINER", True):
            p = get_secure_task_path("/opt/app/config.py")
        self.assertEqual(p, Path("/opt/app/config.py"))

    def test_get_secure_task_path_normalizes_absolute_in_container(self) -> None:
        with patch.object(workspace_mod, "IN_CONTAINER", True):
            p = get_secure_task_path("/opt/../opt/app/config.py")
        self.assertEqual(p, Path("/opt/app/config.py"))

    # Relative paths still resolve under task_root even in-container.
    def test_get_secure_task_path_relative_unchanged_in_container(self) -> None:
        with patch.object(workspace_mod, "IN_CONTAINER", True):
            p = get_secure_task_path("script.py")
        self.assertEqual(p, workspace.task_root() / "script.py")

    def test_get_secure_task_path_accepts_legacy_upload_path_on_host(self) -> None:
        with patch.object(workspace_mod, "IN_CONTAINER", False):
            p = get_secure_task_path("/mnt/data/User/chat/file.zip")
        self.assertEqual(p, workspace.task_root() / "User" / "chat" / "file.zip")

    def test_validate_rejects_absolute_on_host(self) -> None:
        with patch.object(workspace_mod, "IN_CONTAINER", False):
            with self.assertRaises(ValueError):
                validate_model_path("/opt/app/config.py")

    # clear_workspace targets task_root.

    # clear_workspace() must only clear task_root(), not workspace_root().
    def test_clear_workspace_does_not_touch_project_root(self) -> None:
        from sandbox.workspace import clear_workspace, workspace_root, task_root

        # Write a sentinel into project root (workspace_root parent level)
        sentinel = workspace_root() / "__sentinel_clear_test.txt"
        sentinel.write_text("do not delete", encoding="utf-8")

        # Write something into task_root
        (task_root() / "task_file.txt").write_text("task content", encoding="utf-8")

        try:
            result = clear_workspace()
            self.assertTrue(result["ok"])
            self.assertIn("task_file.txt", result["cleared"])
            # Sentinel in project root must survive
            self.assertTrue(
                sentinel.exists(),
                "clear_workspace() deleted files outside task_root — BUG",
            )
        finally:
            sentinel.unlink(missing_ok=True)

    # Legitimate paths still work.

    def test_write_and_read_normal_path(self) -> None:
        write("hello.txt", "world")
        result = read("hello.txt")
        self.assertEqual(result["result"]["content"], "world")

    def test_write_and_read_nested_path(self) -> None:
        write("sub/dir/file.txt", "nested")
        result = read("sub/dir/file.txt")
        self.assertEqual(result["result"]["content"], "nested")

    # workspace read() with traversal path raises before reaching FS.
    def test_handle_tool_read_traversal_via_workspace_api_blocked(self) -> None:
        from sandbox.workspace import read as ws_read
        with self.assertRaises((ValueError, FileNotFoundError)):
            ws_read("../../etc/passwd")


if __name__ == "__main__":
    unittest.main()
