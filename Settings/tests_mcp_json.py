# Copyright NGGT.LightKeeper. All Rights Reserved.

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from Settings import mcp_json


class McpJsonValidationTests(unittest.TestCase):
    def test_validate_stdio_minimal(self) -> None:
        mcp_json.validate_mcp_document({"mcpServers": {"x": {"command": "npx", "args": ["-y", "pkg"]}}})

    def test_validate_http_minimal(self) -> None:
        mcp_json.validate_mcp_document(
            {"mcpServers": {"hf": {"url": "https://example.com/mcp", "headers": {"Authorization": "Bearer x"}}}}
        )

    def test_validate_rejects_both_url_and_command(self) -> None:
        with self.assertRaises(ValueError):
            mcp_json.validate_mcp_document(
                {"mcpServers": {"bad": {"command": "x", "url": "https://example.com"}}}
            )

    def test_validate_rejects_neither_url_nor_command(self) -> None:
        with self.assertRaises(ValueError):
            mcp_json.validate_mcp_document({"mcpServers": {"bad": {}}})


class McpJsonFileTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_dir = mcp_json.MCP_DIR
        self._orig_path = mcp_json.MCP_JSON_PATH
        self.tmp = Path(tempfile.mkdtemp())
        mcp_json.MCP_DIR = self.tmp
        mcp_json.MCP_JSON_PATH = self.tmp / "mcp.json"

    def tearDown(self) -> None:
        mcp_json.MCP_DIR = self._orig_dir
        mcp_json.MCP_JSON_PATH = self._orig_path

    def test_save_roundtrip(self) -> None:
        doc = {"mcpServers": {"demo": {"command": "python", "args": ["-m", "demo"]}}}
        mcp_json.save_raw_text(json.dumps(doc))
        loaded = mcp_json.load_parsed()
        self.assertEqual(loaded["mcpServers"]["demo"]["command"], "python")

    def test_iter_collision_with_reserved(self) -> None:
        mcp_json.save_raw_text(
            json.dumps({"mcpServers": {"browser_agent": {"command": "echo", "args": ["hi"]}}})
        )
        entries = mcp_json.iter_user_mcp_entries({"browser_agent"})
        self.assertEqual(len(entries), 1)
        self.assertNotEqual(entries[0].server_id, "browser_agent")
        self.assertTrue(entries[0].server_id.startswith("user_"))


if __name__ == "__main__":
    unittest.main()
