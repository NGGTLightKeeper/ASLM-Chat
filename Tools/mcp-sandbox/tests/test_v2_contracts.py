from __future__ import annotations

import base64
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

os.environ.setdefault("SANDBOX_HOST_WORKSPACE", str(ROOT.parent.parent))

from sandbox import workspace  # noqa: E402
from sandbox.api import handle_tool  # noqa: E402
from sandbox.config import DEFAULT_TASK_DIR, MAX_CAT_FILE_BYTES  # noqa: E402
from sandbox.session_state import reset_session_state  # noqa: E402


class SandboxV2ContractsTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_session_state()
        self.task_root = workspace.task_root()
        self.task_root.mkdir(parents=True, exist_ok=True)
        for child in list(self.task_root.iterdir()):
            try:
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
            except PermissionError:
                # Skip read-only system dirs (e.g. .git/objects/pack on Windows)
                pass

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

    def test_bash_cat_accepts_container_absolute_task_path(self) -> None:
        handle_tool("write", {"path": "notes.txt", "content": "alpha\nbeta\n"})

        result = handle_tool("bash", {"command": f"cat /workspace/{DEFAULT_TASK_DIR}/notes.txt"})
        self.assertTrue(result["ok"])
        self.assertIn("alpha", result["result"]["stdout"])
        self.assertTrue(result["result"].get("routed", False))

    def test_bash_cat_accepts_legacy_task_alias(self) -> None:
        handle_tool("write", {"path": "notes.txt", "content": "alpha\nbeta\n"})

        result = handle_tool("bash", {"command": "cat task/notes.txt"})
        self.assertTrue(result["ok"])
        self.assertIn("alpha", result["result"]["stdout"])
        self.assertTrue(result["result"].get("routed", False))

    def test_routed_commands_respect_cwd(self) -> None:
        handle_tool("write", {"path": "repo/README.md", "content": "hello from repo\n"})

        result = handle_tool("bash", {"command": "head -n 1 README.md", "cwd": "repo"})
        self.assertTrue(result["ok"])
        self.assertIn("hello from repo", result["result"]["stdout"])
        self.assertEqual(result["result"]["cwd"], "repo")
        self.assertTrue(result["result"].get("routed", False))

    def test_pwd_reports_model_workspace_and_cwd(self) -> None:
        result = handle_tool("bash", {"command": "pwd", "cwd": "repo"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["stdout"], f"/workspace/{DEFAULT_TASK_DIR}/repo")
        self.assertEqual(result["result"]["cwd"], "repo")

    def test_null_cwd_defaults_to_root_for_real_bash(self) -> None:
        with patch(
            "sandbox.api.exec_bash",
            return_value={
                "exit_code": 0,
                "stdout": "hello\n",
                "stderr": "",
                "error": None,
                "elapsed_ms": 5,
                "truncated": False,
                "cwd": ".",
            },
        ) as exec_mock:
            result = handle_tool("bash", {"command": "echo hello | cat", "cwd": None})

        self.assertTrue(result["ok"])
        exec_mock.assert_called_once()
        self.assertEqual(exec_mock.call_args.kwargs["cwd"], ".")

    def test_bash_cat_large_file_returns_auto_preview(self) -> None:
        """Large file cat returns a structured preview, not a dead-end refusal."""
        oversized = "x" * (MAX_CAT_FILE_BYTES + 256)
        handle_tool("write", {"path": "big.log", "content": oversized})

        result = handle_tool("bash", {"command": "cat big.log"})
        # Must succeed — no more dead-end refusal
        self.assertTrue(result["ok"], f"Expected ok=True, got: {result.get('error')}")
        self.assertEqual(result["tool"], "bash")
        stdout = result["result"]["stdout"]
        # Must contain navigation aids
        self.assertIn("big.log", stdout)
        self.assertIn("──", stdout)
        self.assertTrue(result["result"].get("routed", False))

        # stat still works
        stat_result = handle_tool("bash", {"command": "stat big.log"})
        self.assertTrue(stat_result["ok"])
        self.assertIn(str(MAX_CAT_FILE_BYTES + 256), stat_result["result"]["stdout"])

        # head still works and returns only requested lines
        head_result = handle_tool("bash", {"command": "head -n 1 big.log"})
        self.assertTrue(head_result["ok"])
        self.assertTrue(head_result["result"].get("routed", False))

    def test_supervisor_falls_back_to_real_bash_on_path_mismatch(self) -> None:
        with patch("sandbox.api.read", side_effect=FileNotFoundError("File not found: repo/README.md")):
            with patch(
                "sandbox.api.exec_bash",
                return_value={
                    "exit_code": 0,
                    "stdout": "fallback worked\n",
                    "stderr": "",
                    "error": None,
                    "elapsed_ms": 7,
                    "truncated": False,
                    "cwd": ".",
                },
            ) as exec_mock:
                result = handle_tool("bash", {"command": "cat repo/README.md"})

        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["stdout"], "fallback worked\n")
        self.assertFalse(result["result"].get("routed", False))
        exec_mock.assert_called_once()

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
        """&&, ||, ; chains are NOT intercepted and go to real bash.

        Note: plain pipe `|` between read-only commands (cat|head, cat|grep)
        IS now intercepted by the intent controller — that is the desired
        behaviour.  Only chains with side effects bypass the controller.
        """
        chain_cases = [
            "echo hello && cat notes.txt",
            "cat notes.txt || echo failed",
        ]
        for cmd in chain_cases:
            result = handle_tool("bash", {"command": cmd})
            self.assertFalse(
                result.get("result", {}).get("routed", False),
                f"Chain command should not be routed: {cmd}",
            )

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
