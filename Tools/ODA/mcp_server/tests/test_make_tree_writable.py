"""Tests for symlink-safe cleanup chmod."""
from __future__ import annotations

import os
import stat
from pathlib import Path

from sandbox_mcp.files import make_tree_writable

from .conftest import requires_symlinks


@requires_symlinks
def test_make_tree_writable_does_not_chmod_symlink_target(tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    os.chmod(outside, 0o444)

    tree = tmp_path / "tree"
    tree.mkdir()
    link = tree / "link.txt"
    link.symlink_to(outside)

    make_tree_writable(tree)

    assert oct(outside.stat().st_mode & 0o777) == oct(0o444)
