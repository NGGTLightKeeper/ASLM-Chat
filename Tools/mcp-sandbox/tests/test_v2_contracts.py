from __future__ import annotations

import base64
import importlib
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

from sandbox import config as sandbox_config  # noqa: E402
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

    def test_write_and_read_text_use_v2_envelope(self) -> None:
        write_result = handle_tool("write", {"path": "notes.txt", "content": "alpha\nbeta\n"})
        self.assertTrue(write_result["ok"])
        self.assertEqual(write_result["tool"], "write")
        self.assertIn("bytes_written", write_result["result"])

        read_result = handle_tool("read", {"path": "notes.txt", "start_line": 1, "end_line": 1})
        self.assertTrue(read_result["ok"])
        self.assertEqual(read_result["tool"], "read")
        self.assertEqual(read_result["result"]["kind"], "text")
        self.assertEqual(read_result["result"]["content"], "alpha")
        self.assertEqual(read_result["warnings"], [])

    def test_read_image_returns_inline_preview_metadata(self) -> None:
        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO8Bf5QAAAAASUVORK5CYII="
        )
        image_path = self.task_root / "pixel.png"
        image_path.write_bytes(png_bytes)

        result = handle_tool("read", {"path": "pixel.png"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["kind"], "image")
        self.assertEqual(result["result"]["mime"], "image/png")
        self.assertIsNotNone(result["result"]["preview"])
        self.assertIn("data_base64", result["result"]["preview"])

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

    def test_find_and_grep_return_structured_matches(self) -> None:
        handle_tool("write", {"path": "src/main.py", "content": "print('hello')\n"})
        handle_tool("write", {"path": "src/other.txt", "content": "HELLO\n"})

        find_result = handle_tool("find", {"path": ".", "name_pattern": "*.py"})
        self.assertTrue(find_result["ok"])
        self.assertEqual(find_result["tool"], "find")
        self.assertEqual(find_result["result"]["matches"][0]["path"], "src/main.py")

        grep_result = handle_tool("grep", {"pattern": "hello", "path": ".", "case_sensitive": False})
        self.assertTrue(grep_result["ok"])
        self.assertEqual(grep_result["tool"], "grep")
        self.assertGreaterEqual(len(grep_result["result"]["matches"]), 2)


class SandboxAdvancedToolDiscoveryTests(unittest.TestCase):
    def test_advanced_tools_flag_adds_optional_tools(self) -> None:
        previous = os.environ.get("SANDBOX_ADVANCED_TOOLS")
        os.environ["SANDBOX_ADVANCED_TOOLS"] = "true"
        try:
            config_module = importlib.reload(sandbox_config)
            api_module = importlib.import_module("sandbox.api")
            api_module = importlib.reload(api_module)
            tool_ids = [tool["id"] for tool in api_module.TOOLS]
            self.assertIn("mkdir", tool_ids)
            self.assertIn("move", tool_ids)
            self.assertIn("delete", tool_ids)
            self.assertTrue(config_module.ADVANCED_TOOLS_ENABLED)
        finally:
            if previous is None:
                os.environ.pop("SANDBOX_ADVANCED_TOOLS", None)
            else:
                os.environ["SANDBOX_ADVANCED_TOOLS"] = previous
            importlib.reload(sandbox_config)
            importlib.reload(importlib.import_module("sandbox.api"))


if __name__ == "__main__":
    unittest.main()
