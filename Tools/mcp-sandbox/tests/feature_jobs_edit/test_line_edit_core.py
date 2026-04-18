from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import reset_task_root  # noqa: E402
from sandbox import workspace  # noqa: E402


class LineEditCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.task_root = reset_task_root()

    def test_replaces_line_range(self) -> None:
        (self.task_root / "app.py").write_text("a\nb\nc\nd\n", encoding="utf-8")

        result = workspace.edit_lines("app.py", "2:3", "B\nC")

        self.assertEqual((self.task_root / "app.py").read_text(encoding="utf-8"), "a\nB\nC\nd\n")
        self.assertEqual(result["result"]["r"], "2:3")
        self.assertEqual(result["result"]["rm"], 2)
        self.assertEqual(result["result"]["add"], 2)
        self.assertEqual(result["result"]["d"], 0)
        self.assertIn("+L2 B", result["result"]["cx"])

    def test_replaces_single_line(self) -> None:
        (self.task_root / "notes.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")

        workspace.edit_lines("notes.txt", "2", "TWO")

        self.assertEqual((self.task_root / "notes.txt").read_text(encoding="utf-8"), "one\nTWO\nthree\n")

    def test_inserts_when_end_is_before_start(self) -> None:
        (self.task_root / "notes.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")

        result = workspace.edit_lines("notes.txt", "3:2", "inserted")

        self.assertEqual(
            (self.task_root / "notes.txt").read_text(encoding="utf-8"),
            "one\ntwo\ninserted\nthree\n",
        )
        self.assertEqual(result["result"]["rm"], 0)
        self.assertEqual(result["result"]["add"], 1)
        self.assertEqual(result["result"]["d"], 1)

    def test_deletes_range_with_empty_content(self) -> None:
        (self.task_root / "notes.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")

        workspace.edit_lines("notes.txt", "2:2", "")

        self.assertEqual((self.task_root / "notes.txt").read_text(encoding="utf-8"), "one\nthree\n")

    def test_preserves_crlf_newlines(self) -> None:
        (self.task_root / "win.txt").write_text("one\r\ntwo\r\nthree\r\n", encoding="utf-8", newline="")

        workspace.edit_lines("win.txt", "2", "TWO")

        self.assertEqual(
            (self.task_root / "win.txt").read_text(encoding="utf-8", newline=""),
            "one\r\nTWO\r\nthree\r\n",
        )


if __name__ == "__main__":
    unittest.main()
