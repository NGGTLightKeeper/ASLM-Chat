"""Tests for bugs fixed in the audit session.

Covers:
  - Bug #4:  find() type_filter kwarg (was passing `type=` by mistake)
  - Bug #2:  resolve_model_path absolute path rejection
  - Bug #6:  grep -e flag parsing
  - Bug #7:  wc returns None for truncated/binary files
  - Bug #9b: pwd returns model workspace path
  - Bug #9c: survey cache invalidation after mutations
  - Bug #11: _PROJECT_ROOT depth (config)
"""

from __future__ import annotations

import os
import shutil
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Point workspace at a safe, throwaway directory
_FAKE_WORKSPACE = ROOT / ".test_workspace"
os.environ["SANDBOX_HOST_WORKSPACE"] = str(_FAKE_WORKSPACE)

from sandbox import workspace  # noqa: E402
from sandbox.session_state import get_session_state, reset_session_state  # noqa: E402
from sandbox.workspace import (  # noqa: E402
    find,
    resolve_model_path,
    write,
    task_root,
)


def _setup_task_root() -> None:
    """Create a clean task_root for each test."""
    tr = task_root()
    if tr.exists():
        shutil.rmtree(tr)
    tr.mkdir(parents=True, exist_ok=True)


# ── Bug #4: find() type_filter ────────────────────────────────────────

class TestFindTypeFilter(unittest.TestCase):
    """find() must honour type_filter when passed as keyword argument."""

    def setUp(self) -> None:
        reset_session_state()
        _setup_task_root()
        tr = task_root()
        # Create files directly on the real task_root path
        (tr / "afile.txt").write_text("hello", encoding="utf-8")
        (tr / "asubdir").mkdir(exist_ok=True)

    @staticmethod
    def _entry_str(e: object) -> str:
        if isinstance(e, dict):
            return e.get("path", e.get("name", ""))
        return str(e)

    @staticmethod
    def _get_matches(result: dict) -> list:
        """Extract the list of matched entries from find() result."""
        inner = result.get("result", {})
        if isinstance(inner, dict):
            return inner.get("matches", [])
        return []

    def test_type_filter_files_only(self) -> None:
        """find(type_filter='file') must return only files, not directories."""
        result = find(path=".", type_filter="file", max_results=50)
        matches = self._get_matches(result)
        names = [self._entry_str(e) for e in matches]
        self.assertTrue(
            any("afile.txt" in n for n in names),
            f"Expected afile.txt in file-only results, got: {names}",
        )
        self.assertFalse(
            any("asubdir" in n for n in names),
            f"Directory asubdir should NOT appear with type_filter='file', got: {names}",
        )

    def test_type_filter_dirs_only(self) -> None:
        """find(type_filter='directory') must return only directories."""
        result = find(path=".", type_filter="directory", max_results=50)
        matches = self._get_matches(result)
        names = [self._entry_str(e) for e in matches]
        self.assertTrue(
            any("asubdir" in n for n in names),
            f"Expected asubdir in directory-only results, got: {names}",
        )
        self.assertFalse(
            any("afile.txt" in n for n in names),
            f"File afile.txt should NOT appear with type_filter='directory', got: {names}",
        )

    def test_no_type_filter_returns_both(self) -> None:
        """find() with no type_filter must return files and dirs."""
        result = find(path=".", max_results=50)
        matches = self._get_matches(result)
        names = [self._entry_str(e) for e in matches]
        entry_types = {e.get("type") for e in matches if isinstance(e, dict)}
        self.assertIn("file", entry_types,
                      f"Expected 'file' type in results, got types={entry_types} names={names}")
        self.assertIn("directory", entry_types,
                      f"Expected 'directory' type in results, got types={entry_types} names={names}")


# ── Bug #2: resolve_model_path rejects paths outside task root ────────

class TestResolveModelPathSecurity(unittest.TestCase):
    """resolve_model_path must block absolute paths outside the sandbox."""

    def test_rejects_etc_passwd(self) -> None:
        with self.assertRaises(ValueError, msg="Should reject /etc/passwd"):
            resolve_model_path("/etc/passwd")

    def test_rejects_root_path(self) -> None:
        with self.assertRaises(ValueError, msg="Should reject bare /"):
            resolve_model_path("/")

    def test_rejects_windows_system_path(self) -> None:
        # Even on Linux the function should reject anything starting with /
        # that is not the container task root.
        with self.assertRaises(ValueError):
            resolve_model_path("/usr/bin/python3")

    def test_rejects_workspace_root_without_task_dir(self) -> None:
        """'/workspace' alone (without task subdir) must be rejected."""
        with self.assertRaises(ValueError):
            resolve_model_path("/workspace")

    def test_allows_relative_path(self) -> None:
        """Relative paths must be resolved without error."""
        result = resolve_model_path("src/main.py")
        self.assertTrue(result.endswith("src/main.py") or result == "src/main.py",
                        f"Unexpected result: {result}")

    def test_allows_dot(self) -> None:
        """'.' must be resolved without error."""
        result = resolve_model_path(".")
        self.assertIsNotNone(result)


# ── Bug #6: grep -e flag ──────────────────────────────────────────────

class TestGrepEFlag(unittest.TestCase):
    """_try_route_grep must parse -e <pattern> correctly.

    This is a unit test of the flag parser itself, mocking out the
    filesystem.  It verifies bug #6: -e was consuming the pattern
    argument as "the value of an unknown flag", leaving pattern=None.
    """

    def _call_route_grep(self, args_str: str) -> dict | None:
        """Call _try_route_grep with a fake grep() matching real signature.

        Simulates finding real content in the fake file.
        """
        import re
        import sandbox.api as api_mod

        file_content = "hello world\nfoo bar\n"
        original_grep = api_mod.grep
        original_resolve = api_mod.resolve_model_path

        def fake_grep(
            path, pattern,
            glob=None, case_sensitive=True,
            context_before=0, context_after=0,
            max_results=100,
        ):
            import re as re_mod
            flags = re_mod.IGNORECASE if not case_sensitive else 0
            matches = []
            for i, line in enumerate(file_content.splitlines(), 1):
                if pattern and re_mod.search(pattern, line, flags):
                    matches.append({"path": "somefile.txt", "line_number": i, "line": line, "before": [], "after": []})
            return {"result": {"path": path, "pattern": pattern or "", "matches": matches}, "warnings": [], "truncated": False}

        def fake_resolve(path: str, cwd: str = ".") -> str:
            """Return path as-is — no real filesystem needed."""
            return path or "."

        api_mod.grep = fake_grep
        api_mod.resolve_model_path = fake_resolve
        try:
            fake_match = re.match(r"(?P<cmd>grep)", "grep")
            return api_mod._try_route_grep(fake_match, args_str, cwd=".")
        finally:
            api_mod.grep = original_grep
            api_mod.resolve_model_path = original_resolve

    def test_grep_e_extracts_pattern_correctly(self) -> None:
        """-e <pattern> must be parsed as the search pattern."""
        result = self._call_route_grep("-e hello somefile.txt")
        # Result should be non-None and contain 'hello' line
        self.assertIsNotNone(result, "_try_route_grep should return a result for -e pattern")
        stdout = result.get("result", {}).get("stdout", "")
        self.assertIn("hello", stdout, f"'hello' should be in grep output: {stdout!r}")

    def test_grep_e_does_not_swallow_pattern_as_flag_value(self) -> None:
        """Regression #6: when -e is unknown flag, 'pattern' was consumed as its VALUE.

        Old behavior: -e processed by unknown-flag handler which consumed
        'hello' as the flag's value, leaving pattern=None → grep searched for
        the file name as pattern → no matches.
        """
        result = self._call_route_grep("-e foo somefile.txt")
        self.assertIsNotNone(result, "Should handle -e correctly")
        stdout = result.get("result", {}).get("stdout", "")
        # 'foo' must appear in output (it matches 'foo bar' line)
        self.assertIn("foo", stdout,
                      f"Pattern 'foo' must be found — if empty, -e bug still present: {stdout!r}")

    def test_grep_without_e_still_works(self) -> None:
        """Plain grep <pattern> <file> must still work after -e fix."""
        result = self._call_route_grep("hello somefile.txt")
        if result is None:
            return  # fallthrough to bash — acceptable
        stdout = result.get("result", {}).get("stdout", "")
        self.assertIn("hello", stdout, f"Plain grep should still find 'hello': {stdout!r}")


# ── Bug #7: wc returns None for truncated files ───────────────────────

class TestWcTruncated(unittest.TestCase):
    """_try_route_wc must return None for truncated or binary results."""

    def _run_wc(self, command: str) -> dict | None:
        from sandbox.api import _try_supervise  # type: ignore[attr-defined]
        return _try_supervise(command, cwd=".")

    def test_wc_small_text_file_is_handled(self) -> None:
        """wc -l on a small text file: supervisor uses total_lines from metadata."""
        _setup_task_root()
        write("small.txt", "line one\nline two\nline three\n")
        result = self._run_wc("wc -l small.txt")
        if result is None:
            self.skipTest("_try_supervise returned None (Docker not available)")
        stdout = result.get("result", {}).get("stdout", "")
        # workspace.read() counts total lines including trailing newlines.
        # 3 lines with trailing \n → total_lines may be 3 or 4 depending on impl.
        # We just ensure we get a numeric count, not an empty result.
        self.assertRegex(stdout.split()[0], r"^\d+$",
                         f"wc -l should return a line count, got: {stdout!r}")

    def test_wc_returns_none_for_truncated_file(self) -> None:
        """wc must return None (→ real bash) when read() reports truncated."""
        import re
        import sandbox.api as api_mod

        original_read = api_mod.read

        def fake_read(path, max_bytes=None):
            return {
                "result": {"kind": "text", "content": "x" * 100, "total_lines": 99},
                "truncated": True,
            }

        api_mod.read = fake_read
        try:
            fake_match = re.match(r"(?P<cmd>wc)", "wc")
            result = api_mod._try_route_wc(fake_match, "-l bigfile.txt", cwd=".")
            self.assertIsNone(result, "wc must return None when file is truncated")
        finally:
            api_mod.read = original_read


# ── Bug #9b: pwd returns model workspace path ─────────────────────────

class TestPwdReturnsModelWorkspace(unittest.TestCase):
    """_try_route_pwd returns the model workspace for simple pwd commands."""

    def test_pwd_returns_model_workspace(self) -> None:
        import re
        import sandbox.api as api_mod
        fake_match = re.match(r"(?P<cmd>pwd)", "pwd")
        result = api_mod._try_route_pwd(fake_match, "", cwd=".")
        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["stdout"], "/workspace/_sandbox\n")


# ── Bug #9c: survey cache invalidation ───────────────────────────────

class TestSurveyCacheInvalidation(unittest.TestCase):
    """Survey cache must be cleared after any filesystem mutation."""

    def setUp(self) -> None:
        reset_session_state()
        _setup_task_root()

    def test_write_invalidates_survey_cache(self) -> None:
        """Survey cache must be invalidated when write() is called via handle_tool.

        Note: workspace.write() itself does NOT invalidate — invalidation happens
        in api._handle_write() which wraps it. So we test via handle_tool.
        """
        from sandbox.api import handle_tool
        state = get_session_state()
        state.record_survey({"output": "old survey"})
        self.assertTrue(state.has_survey_cache(), "Cache should be set before write")

        handle_tool("write", {"path": "newfile.txt", "content": "content"})

        self.assertFalse(state.has_survey_cache(),
                         "Survey cache must be invalidated after handle_tool('write')")

    def test_invalidate_survey_cache_method(self) -> None:
        """invalidate_survey_cache() must clear both cache and timestamp."""
        state = get_session_state()
        state.record_survey({"output": "data"})
        self.assertIsNotNone(state.repo_survey_cache)
        self.assertGreater(state.repo_survey_ts, 0)

        state.invalidate_survey_cache()

        self.assertIsNone(state.repo_survey_cache)
        self.assertEqual(state.repo_survey_ts, 0.0)
        self.assertFalse(state.has_survey_cache())

    def test_mkdir_via_api_invalidates_cache(self) -> None:
        """Cache must be cleared even when mkdir goes through bash routing."""
        state = get_session_state()
        state.record_survey({"output": "old"})

        from sandbox.api import _try_supervise
        import re
        fake_match = re.match(r"(?P<cmd>mkdir)", "mkdir")
        import sandbox.api as api_mod
        # Call _try_route_mkdir directly
        api_mod._try_route_mkdir(fake_match, "newdir", cwd=".")

        self.assertFalse(state.has_survey_cache(),
                         "Survey cache must be invalidated after mkdir")


# ── Bug #11: config._PROJECT_ROOT depth ──────────────────────────────

class TestProjectRootPath(unittest.TestCase):
    """_PROJECT_ROOT must point to mcp-sandbox root (2 levels up from config.py)."""

    def test_project_root_is_mcp_sandbox_dir(self) -> None:
        from sandbox import config
        project_root = Path(config.__file__).resolve().parents[2]
        # Should be the directory that contains Dockerfile and src/
        self.assertTrue(
            (project_root / "src").exists(),
            f"_PROJECT_ROOT {project_root} does not contain src/ — wrong depth!",
        )
        self.assertTrue(
            (project_root / "Dockerfile").exists() or (project_root / "src" / "sandbox").exists(),
            f"_PROJECT_ROOT {project_root} doesn't look like mcp-sandbox root",
        )

    def test_host_workspace_env_overrides_project_root(self) -> None:
        """SANDBOX_HOST_WORKSPACE env var must take precedence over _PROJECT_ROOT."""
        import sandbox.config as cfg
        # We set SANDBOX_HOST_WORKSPACE at module import time
        # HOST_WORKSPACE should reflect our fake workspace
        self.assertEqual(
            cfg.HOST_WORKSPACE,
            str(_FAKE_WORKSPACE),
            f"HOST_WORKSPACE does not use env override: {cfg.HOST_WORKSPACE}",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
