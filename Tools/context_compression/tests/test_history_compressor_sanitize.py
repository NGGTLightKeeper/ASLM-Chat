from __future__ import annotations

import unittest

from context_compression.history_compressor import (
    _is_assistant_navigation,
    _looks_like_valid_path,
    _passes_semantic_threshold,
    _raw_context_payload,
    _sanitize_semantic_items,
)


class HistoryCompressorSanitizeTests(unittest.TestCase):
    def test_looks_like_valid_path_rejects_json_escaped_code(self) -> None:
        self.assertFalse(_looks_like_valid_path(r"f:\n lines = f.readlines()"))
        self.assertFalse(_looks_like_valid_path("line.strip"))
        self.assertFalse(_looks_like_valid_path("re.match"))
        self.assertTrue(_looks_like_valid_path(r"C:\Projects\app\main.py"))
        self.assertTrue(_looks_like_valid_path("SettingsView.xaml.cs"))
        self.assertTrue(_looks_like_valid_path("archive.tar.gz"))
        self.assertFalse(_looks_like_valid_path("re.MULTILINE"))

    def test_sanitize_semantic_items_drops_navigation(self) -> None:
        items = [
            "assistant: Now let me do a deeper structural analysis of the repo.",
            "assistant: Let me first analyze the file for systematic issues before making changes.",
            "assistant: [Fixed import in history_compressor.py]",
        ]
        cleaned = _sanitize_semantic_items(items, limit=10, max_chars=500, allow_tool_memory=True)
        self.assertEqual(len(cleaned), 1)
        self.assertIn("Fixed import", cleaned[0])

    def test_sanitize_semantic_items_drops_bare_headings(self) -> None:
        items = ["Изменения:", "The compressor now filters escaped newline paths in artifacts."]
        cleaned = _sanitize_semantic_items(items, limit=10, max_chars=500, apply_semantic_threshold=True)
        self.assertEqual(len(cleaned), 1)
        self.assertIn("compressor", cleaned[0])

    def test_passes_semantic_threshold(self) -> None:
        self.assertFalse(_passes_semantic_threshold("Изменения:"))
        self.assertTrue(_passes_semantic_threshold("YouTube URL was provided."))

    def test_raw_context_payload_skips_false_windows_paths(self) -> None:
        payload = _raw_context_payload(
            [
                {
                    "role": "assistant",
                    "content": "Saved to C:\\repo\\src\\module.py\nf:\\n lines = f.readlines()",
                }
            ],
            [],
        )
        files = payload["artifacts"]["files"]
        self.assertIn(r"C:\repo\src\module.py", files)
        self.assertFalse(any("readlines" in name or "\\n" in name for name in files))


if __name__ == "__main__":
    unittest.main(verbosity=2)
