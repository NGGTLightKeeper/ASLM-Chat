# Copyright NEXTGGTECH. Elastic License 2.0.

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import reset_task_root  # noqa: E402
from sandbox.api import TOOLS, handle_tool  # noqa: E402


class LineEditApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.task_root = reset_task_root()

    def test_handle_tool_edit_lines(self) -> None:
        handle_tool("write", {"path": "app.py", "content": "a\nb\nc\n"})

        result = handle_tool(
            "edit",
            {
                "path": "app.py",
                "mode": "lines",
                "range": "2:2",
                "content": "B",
                "anchor": "b",
            },
        )

        self.assertTrue(result["ok"], result.get("error"))
        self.assertEqual((self.task_root / "app.py").read_text(encoding="utf-8"), "a\nB\nc\n")
        self.assertEqual(result["result"]["r"], "2:2")

    def test_line_mode_array_range(self) -> None:
        handle_tool("write", {"path": "app.py", "content": "a\nb\nc\nd\n"})

        result = handle_tool(
            "edit",
            {
                "path": "app.py",
                "mode": "lines",
                "range": [2, 3],
                "content": "B\nC",
            },
        )

        self.assertTrue(result["ok"], result.get("error"))
        self.assertEqual((self.task_root / "app.py").read_text(encoding="utf-8"), "a\nB\nC\nd\n")
        self.assertNotIn("None", "\n".join(result["result"]["cx"]))

    def test_legacy_match_mode_still_works(self) -> None:
        handle_tool("write", {"path": "app.txt", "content": "hello\n"})

        result = handle_tool(
            "edit",
            {
                "path": "app.txt",
                "old_str": "hello",
                "new_str": "world",
            },
        )

        self.assertTrue(result["ok"], result.get("error"))
        self.assertIn("m", result["result"])
        self.assertIn("cx", result["result"])
        self.assertEqual((self.task_root / "app.txt").read_text(encoding="utf-8"), "world\n")

    def test_match_mode_ignores_empty_range(self) -> None:
        handle_tool("write", {"path": "app.txt", "content": "hello\n"})

        result = handle_tool(
            "edit",
            {
                "path": "app.txt",
                "old_str": "hello",
                "new_str": "world",
                "range": "",
            },
        )

        self.assertTrue(result["ok"], result.get("error"))
        self.assertIn("m", result["result"])
        self.assertIn("cx", result["result"])
        self.assertEqual((self.task_root / "app.txt").read_text(encoding="utf-8"), "world\n")

    def test_line_mode_requires_range(self) -> None:
        handle_tool("write", {"path": "app.py", "content": "a\nb\nc\nd\n"})

        result = handle_tool(
            "edit",
            {
                "path": "app.py",
                "mode": "lines",
                "content": "B\nC",
            },
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["type"], "invalid_arguments")

    def test_match_mode_requires_old_and_new_strings(self) -> None:
        handle_tool("write", {"path": "app.txt", "content": "hello\n"})

        result = handle_tool("edit", {"path": "app.txt"})

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["type"], "invalid_arguments")
        self.assertIn("old_str", result["error"]["message"])

    def test_line_mode_requires_range_and_content(self) -> None:
        handle_tool("write", {"path": "app.txt", "content": "hello\n"})

        result = handle_tool("edit", {"path": "app.txt", "mode": "lines", "range": "1:1"})

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["type"], "invalid_arguments")
        self.assertIn("content", result["error"]["message"])

    def test_edit_description_documents_lines_contract(self) -> None:
        edit_tool = next(tool for tool in TOOLS if tool["id"] == "edit")
        description = edit_tool["description"]

        self.assertIn("range", description)
        self.assertIn("1-based", description)
        self.assertIn("/workspace/_sandbox", description)
        self.assertIn("Linux paths", description)

    def test_write_description_documents_workspace_relative_paths(self) -> None:
        write_tool = next(tool for tool in TOOLS if tool["id"] == "write")
        description = write_tool["description"]

        self.assertIn("/workspace/_sandbox", description)
        self.assertIn("Linux paths", description)
        self.assertIn("Windows-style paths are rejected", description)


if __name__ == "__main__":
    unittest.main()
