# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import reset_task_root  # noqa: E402
from sandbox import workspace  # noqa: E402
from sandbox.responses import SandboxToolError  # noqa: E402


class LineEditAnchorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.task_root = reset_task_root()

    def test_accepts_matching_anchor(self) -> None:
        (self.task_root / "app.py").write_text("def old():\n    return 1\n", encoding="utf-8")

        workspace.edit_lines("app.py", "1:2", "def new():\n    return 2", anchor="def old():")

        self.assertEqual((self.task_root / "app.py").read_text(encoding="utf-8"), "def new():\n    return 2\n")

    def test_anchor_mismatch_suggests_nearby_range(self) -> None:
        (self.task_root / "app.py").write_text("import os\n\ndef target():\n    return 1\n", encoding="utf-8")

        with self.assertRaises(SandboxToolError) as raised:
            workspace.edit_lines("app.py", "1:2", "replacement", anchor="def target():")

        self.assertEqual(raised.exception.error_type, "anchor_mismatch")
        self.assertEqual(raised.exception.result["suggestion"], "Use range 3:4.")
        self.assertEqual(raised.exception.result["actual_line_1"], "import os")

    def test_anchor_mismatch_without_suggestion(self) -> None:
        (self.task_root / "app.py").write_text("import os\nvalue = 1\n", encoding="utf-8")

        with self.assertRaises(SandboxToolError) as raised:
            workspace.edit_lines("app.py", "1:1", "replacement", anchor="def missing():")

        self.assertEqual(raised.exception.error_type, "anchor_mismatch")
        self.assertNotIn("suggestion", raised.exception.result)


if __name__ == "__main__":
    unittest.main()
