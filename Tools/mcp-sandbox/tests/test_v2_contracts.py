from __future__ import annotations

import base64
import os
import shutil
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

os.environ.setdefault("SANDBOX_HOST_WORKSPACE", str(ROOT.parent.parent))

from sandbox import workspace  # noqa: E402
from sandbox.api import handle_tool  # noqa: E402


class SandboxV2ContractsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.task_root = workspace.task_root()
        self.task_root.mkdir(parents=True, exist_ok=True)
        for child in list(self.task_root.iterdir()):
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()

    def test_write_and_bash_cat_text(self) -> None:
        write_result = handle_tool("write", {"path": "notes.txt", "content": "alpha\nbeta\n"})
        self.assertTrue(write_result["ok"])
        self.assertEqual(write_result["tool"], "write")
        self.assertIn("bytes_written", write_result["result"])

        # Read via bash cat (routed to internal read)
        cat_result = handle_tool("bash", {"command": "cat notes.txt"})
        self.assertTrue(cat_result["ok"])
        self.assertEqual(cat_result["tool"], "bash")
        self.assertIn("alpha", cat_result["result"]["stdout"])
        self.assertTrue(cat_result["result"].get("routed", False))

    def test_bash_head_routes_correctly(self) -> None:
        handle_tool("write", {"path": "lines.txt", "content": "\n".join(f"line{i}" for i in range(1, 21))})
        result = handle_tool("bash", {"command": "head -n 5 lines.txt"})
        self.assertTrue(result["ok"])
        self.assertIn("line1", result["result"]["stdout"])
        self.assertNotIn("line10", result["result"]["stdout"])
        self.assertTrue(result["result"].get("routed", False))

    def test_bash_grep_routes_correctly(self) -> None:
        handle_tool("write", {"path": "src/main.py", "content": "print('hello')\n"})
        handle_tool("write", {"path": "src/other.txt", "content": "HELLO\n"})

        result = handle_tool("bash", {"command": "grep -ri hello ."})
        self.assertTrue(result["ok"])
        stdout = result["result"]["stdout"]
        self.assertIn("hello", stdout.lower())
        self.assertTrue(result["result"].get("routed", False))

    def test_bash_find_routes_correctly(self) -> None:
        handle_tool("write", {"path": "src/main.py", "content": "print('hello')\n"})

        result = handle_tool("bash", {"command": "find . -name '*.py'"})
        self.assertTrue(result["ok"])
        self.assertIn("main.py", result["result"]["stdout"])
        self.assertTrue(result["result"].get("routed", False))

    def test_bash_mkdir_routes_correctly(self) -> None:
        result = handle_tool("bash", {"command": "mkdir -p deep/nested/dir"})
        self.assertTrue(result["ok"])
        self.assertTrue(result["result"].get("routed", False))

        ls_result = handle_tool("bash", {"command": "ls deep"})
        self.assertTrue(ls_result["ok"])
        self.assertIn("nested", ls_result["result"]["stdout"])

    def test_bash_mv_routes_correctly(self) -> None:
        handle_tool("write", {"path": "old.txt", "content": "data"})
        result = handle_tool("bash", {"command": "mv old.txt new.txt"})
        self.assertTrue(result["ok"])
        self.assertTrue(result["result"].get("routed", False))

        cat_result = handle_tool("bash", {"command": "cat new.txt"})
        self.assertTrue(cat_result["ok"])
        self.assertIn("data", cat_result["result"]["stdout"])

    def test_bash_rm_routes_correctly(self) -> None:
        handle_tool("write", {"path": "temp.txt", "content": "delete me"})
        result = handle_tool("bash", {"command": "rm temp.txt"})
        self.assertTrue(result["ok"])
        self.assertTrue(result["result"].get("routed", False))

        cat_result = handle_tool("bash", {"command": "cat temp.txt"})
        self.assertFalse(cat_result["ok"])

    def test_compound_commands_go_to_real_bash(self) -> None:
        """Pipes, chains, and subshells should NOT be intercepted."""
        # This will go to real bash (which may fail without container) —
        # but the point is it should NOT be routed.
        result = handle_tool("bash", {"command": "echo hello | grep hello"})
        # If real bash is available, result.ok may be True or False depending
        # on container state, but routed should NOT be True.
        self.assertFalse(result.get("result", {}).get("routed", False))

    def test_read_image_returns_inline_preview_metadata(self) -> None:
        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO8Bf5QAAAAASUVORK5CYII="
        )
        image_path = self.task_root / "pixel.png"
        image_path.write_bytes(png_bytes)

        # file command should report image type
        result = handle_tool("bash", {"command": "file pixel.png"})
        self.assertTrue(result["ok"])
        self.assertIn("image", result["result"]["stdout"])

    def test_edit_returns_typed_error_for_ambiguous_match(self) -> None:
        handle_tool("write", {"path": "app.txt", "content": "hello\nhello\n"})

        result = handle_tool(
            "edit",
            {
                "path": "app.txt",
                "old_str": "hello",
                "new_str": "world",
            },
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["tool"], "edit")
        self.assertEqual(result["error"]["type"], "ambiguous_match")
        self.assertEqual(result["result"]["match_count"], 2)

    def test_public_tools_are_bash_write_edit_only(self) -> None:
        from sandbox.api import TOOLS
        tool_ids = {t["id"] for t in TOOLS}
        self.assertEqual(tool_ids, {"bash", "write", "edit"})


if __name__ == "__main__":
    unittest.main()
