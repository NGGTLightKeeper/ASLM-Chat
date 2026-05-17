# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import base64
import json
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
from sandbox import api as sandbox_api  # noqa: E402
from sandbox.api import handle_tool  # noqa: E402
from sandbox.config import DEFAULT_TASK_DIR, MAX_CAT_FILE_BYTES  # noqa: E402


class SandboxV2ContractsTests(unittest.TestCase):
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

    def test_write_and_bash_cat_text(self) -> None:
        write_result = handle_tool("write", {"path": "notes.txt", "content": "alpha\nbeta\n"})
        self.assertTrue(write_result["ok"])

        cat_result = handle_tool("bash", {"command": "cat notes.txt"})
        self.assertTrue(cat_result["ok"])
        self.assertEqual(cat_result["tool"], "bash")
        self.assertEqual(cat_result["result"]["stdout"], "alpha\nbeta\n")
        self.assertTrue(cat_result["result"].get("routed", False))

    def test_head_uses_real_bash(self) -> None:
        handle_tool("write", {"path": "lines.txt", "content": "\n".join(f"line{i}" for i in range(1, 21))})
        with patch(
            "sandbox.api.exec_bash",
            return_value={
                "exit_code": 0,
                "stdout": "line1\nline2\nline3\nline4\nline5\n",
                "stderr": "",
                "error": None,
                "elapsed_ms": 5,
                "truncated": False,
                "cwd": ".",
            },
        ):
            result = handle_tool("bash", {"command": "head -n 5 lines.txt"})
        self.assertTrue(result["ok"])
        self.assertIn("line1", result["result"]["stdout"])
        self.assertNotIn("line10", result["result"]["stdout"])
        self.assertFalse(result["result"].get("routed", False))

    def test_bash_cat_accepts_container_absolute_task_path(self) -> None:
        handle_tool("write", {"path": "notes.txt", "content": "alpha\nbeta\n"})

        result = handle_tool("bash", {"command": f"cat /workspace/{DEFAULT_TASK_DIR}/notes.txt"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["stdout"], "alpha\nbeta\n")
        self.assertTrue(result["result"].get("routed", False))

    def test_bash_cat_accepts_legacy_upload_absolute_path(self) -> None:
        handle_tool("write", {"path": "User/chat/notes.txt", "content": "alpha\nbeta\n"})

        result = handle_tool("bash", {"command": "cat /mnt/data/User/chat/notes.txt"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["stdout"], "alpha\nbeta\n")
        self.assertTrue(result["result"].get("routed", False))

    def test_bash_cat_accepts_legacy_task_alias(self) -> None:
        handle_tool("write", {"path": "notes.txt", "content": "alpha\nbeta\n"})

        result = handle_tool("bash", {"command": "cat task/notes.txt"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["stdout"], "alpha\nbeta\n")
        self.assertTrue(result["result"].get("routed", False))

    def test_supervised_cat_respects_cwd(self) -> None:
        handle_tool("write", {"path": "repo/README.md", "content": "hello from repo\n"})

        result = handle_tool("bash", {"command": "cat README.md", "cwd": "repo"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["stdout"], "hello from repo\n")
        self.assertEqual(result["result"]["cwd"], "repo")
        self.assertTrue(result["result"].get("routed", False))

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
        oversized = "x" * (MAX_CAT_FILE_BYTES + 256)
        handle_tool("write", {"path": "big.log", "content": oversized})

        result = handle_tool("bash", {"command": "cat big.log"})
        self.assertTrue(result["ok"], f"Expected ok=True, got: {result.get('error')}")
        stdout = result["result"]["stdout"]
        self.assertIn("-- big.log", stdout)
        self.assertIn("[head:", stdout)
        self.assertTrue(result["result"].get("routed", False))

        with patch(
            "sandbox.api.exec_bash",
            return_value={
                "exit_code": 0,
                "stdout": oversized + "\n",
                "stderr": "",
                "error": None,
                "elapsed_ms": 5,
                "truncated": False,
                "cwd": ".",
            },
        ):
            head_result = handle_tool("bash", {"command": "head -n 1 big.log"})
        self.assertTrue(head_result["ok"])
        self.assertFalse(head_result["result"].get("routed", False))

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

    def test_search_find_and_mutations_use_real_bash(self) -> None:
        cases = ("grep -ri hello .", "find . -name '*.py'", "mkdir -p deep/nested/dir")
        for command in cases:
            with patch(
                "sandbox.api.exec_bash",
                return_value={
                    "exit_code": 0,
                    "stdout": "real bash\n",
                    "stderr": "",
                    "error": None,
                    "elapsed_ms": 1,
                    "truncated": False,
                    "cwd": ".",
                },
            ) as exec_mock:
                result = handle_tool("bash", {"command": command})
            self.assertTrue(result["ok"])
            self.assertFalse(result["result"].get("routed", False), command)
            exec_mock.assert_called_once()

    def test_compound_commands_go_to_real_bash(self) -> None:
        for command in ("echo hello && cat notes.txt", "cat notes.txt | head -n 1"):
            with patch(
                "sandbox.api.exec_bash",
                return_value={
                    "exit_code": 0,
                    "stdout": "mocked real bash\n",
                    "stderr": "",
                    "error": None,
                    "elapsed_ms": 1,
                    "truncated": False,
                    "cwd": ".",
                },
            ) as exec_mock:
                result = handle_tool("bash", {"command": command})
            self.assertFalse(result.get("result", {}).get("routed", False), command)
            exec_mock.assert_called_once()

    def test_read_image_reports_metadata_for_cat(self) -> None:
        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO8Bf5QAAAAASUVORK5CYII="
        )
        (self.task_root / "pixel.png").write_bytes(png_bytes)

        result = handle_tool("bash", {"command": "cat pixel.png"})
        self.assertTrue(result["ok"])
        self.assertIn("[image file:", result["result"]["stdout"])

    def test_view_image_returns_metadata_and_preview(self) -> None:
        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO8Bf5QAAAAASUVORK5CYII="
        )
        (self.task_root / "pixel.png").write_bytes(png_bytes)
        metadata_path = self.task_root / "model_runtime_metadata.json"
        metadata_path.write_text(
            json.dumps(
                {
                    "active": {"engine": "test-engine", "model": "vision-model"},
                    "models": {
                        "test-engine:vision-model": {
                            "engine": "test-engine",
                            "model": "vision-model",
                            "capabilities": {"vision": True},
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        with patch.object(sandbox_api, "MODEL_RUNTIME_METADATA_PATH", metadata_path):
            result = handle_tool(
                "view_image",
                {"path": "pixel.png"},
                {"engine": "test-engine", "model_name": "vision-model"},
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["tool"], "view_image")
        self.assertEqual(result["result"]["kind"], "image")
        self.assertEqual(result["result"]["mime"], "image/png")
        self.assertEqual(result["result"]["width"], 1)
        self.assertEqual(result["result"]["height"], 1)
        self.assertEqual(result["result"]["preview"]["type"], "inline_base64")
        self.assertEqual(result["result"]["preview"]["data_base64"], base64.b64encode(png_bytes).decode("utf-8"))

    def test_view_image_withholds_preview_when_active_model_lacks_vision(self) -> None:
        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO8Bf5QAAAAASUVORK5CYII="
        )
        (self.task_root / "pixel.png").write_bytes(png_bytes)
        metadata_path = self.task_root / "model_runtime_metadata.json"
        metadata_path.write_text(
            json.dumps(
                {
                    "active": {"engine": "test-engine", "model": "text-only"},
                    "models": {
                        "test-engine:text-only": {
                            "engine": "test-engine",
                            "model": "text-only",
                            "capabilities": {"vision": False},
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        with patch.object(sandbox_api, "MODEL_RUNTIME_METADATA_PATH", metadata_path):
            result = handle_tool(
                "view_image",
                {"path": "pixel.png"},
                {"engine": "test-engine", "model_name": "text-only"},
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["kind"], "image")
        self.assertEqual(result["result"]["preview"]["type"], "text_placeholder")
        self.assertNotIn("data_base64", result["result"]["preview"])
        self.assertFalse(result["result"]["vision_gate"]["allowed"])

    def test_view_image_rejects_non_image(self) -> None:
        handle_tool("write", {"path": "notes.txt", "content": "hello\n"})

        result = handle_tool("view_image", {"path": "notes.txt"})

        self.assertFalse(result["ok"])
        self.assertEqual(result["tool"], "view_image")
        self.assertEqual(result["error"]["type"], "not_image")

    def test_share_file_includes_image_render_preview(self) -> None:
        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO8Bf5QAAAAASUVORK5CYII="
        )
        (self.task_root / "pixel.png").write_bytes(png_bytes)
        result = handle_tool("share_file", {"path": "pixel.png"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["tool"], "share_file")
        self.assertEqual(result["result"]["kind"], "shared_file")
        self.assertEqual(result["result"]["render"]["type"], "image")
        self.assertEqual(result["result"]["render"]["mime_type"], "image/png")
        self.assertEqual(result["result"]["render"]["preview"]["type"], "inline_base64")

    def test_share_file_includes_table_render_preview_for_csv(self) -> None:
        handle_tool("write", {"path": "report.csv", "content": "name,score\nalice,10\nbob,20\n"})
        result = handle_tool("share_file", {"path": "report.csv"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["tool"], "share_file")
        self.assertEqual(result["result"]["render"]["type"], "table")
        self.assertEqual(result["result"]["render"]["format"], "csv")
        self.assertEqual(result["result"]["render"]["columns"], ["name", "score"])
        self.assertEqual(result["result"]["render"]["sample_rows"][0], ["alice", "10"])

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

    def test_public_tools_are_bash_write_edit_view_image_share_file(self) -> None:
        from sandbox.api import TOOLS

        tool_ids = {tool["id"] for tool in TOOLS}
        self.assertEqual(tool_ids, {"bash", "write", "edit", "view_image", "share_file"})


if __name__ == "__main__":
    unittest.main()
