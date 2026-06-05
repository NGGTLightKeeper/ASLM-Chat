# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SUPERVISOR = ROOT / "supervisor"
for path in (SUPERVISOR, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

os.environ.setdefault("SANDBOX_HOST_WORKSPACE", str(ROOT / ".test_workspace_config"))

import sandbox.config as config_mod  # noqa: E402


class ConfigValidationTests(unittest.TestCase):
    # Reject generic home paths when DEFAULT_TASK_DIR is '.'.
    def test_dot_task_dir_rejects_generic_home_workspace(self) -> None:
        with patch.object(config_mod, "DEFAULT_TASK_DIR", "."):
            self.assertFalse(config_mod._validate_workspace_path("/home/dima"))

    # Allow dedicated sandbox workspace paths when DEFAULT_TASK_DIR is '.'.
    def test_dot_task_dir_allows_dedicated_sandbox_workspace(self) -> None:
        with patch.object(config_mod, "DEFAULT_TASK_DIR", "."):
            self.assertTrue(config_mod._validate_workspace_path("/home/dima/mcp-sandbox"))

    # Subdir task dir keeps existing workspace validation rules.
    def test_subdir_task_dir_keeps_existing_workspace_validation(self) -> None:
        with patch.object(config_mod, "DEFAULT_TASK_DIR", "_sandbox"):
            self.assertTrue(config_mod._validate_workspace_path("/home/dima/project"))


if __name__ == "__main__":
    unittest.main()
