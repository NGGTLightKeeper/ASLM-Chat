# Copyright NGGT.LightKeeper. All Rights Reserved.

"""Cross-mode sandbox tests: file sync, model context, uploads, browser screenshots."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from Apps.UI import upload_storage
from Apps.UI.tests import ToolRegistryTestMixin
from Apps.UI.upload_storage import resolve_upload_storage_target, resolve_uploaded_file_host_path
from Apps.UI.views import (
    _build_sandbox_mode_switch_notice,
    _load_model_upload_manifests,
    _maybe_inject_sandbox_mode_switch_notice,
    _resolve_shared_file_path,
    _sandbox_default_root,
    _sync_sandbox_roots,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
BROWSER_AGENT_ROOT = REPO_ROOT / "Tools" / "mcp-browser-agent"
if str(BROWSER_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(BROWSER_AGENT_ROOT))

from browser_screenshot import SANDBOX_SCREEN_TARGETS, _sandbox_screens_dir  # noqa: E402


class SandboxSyncApiTests(TestCase):
    """HTTP API and host-path merge for sandbox default roots."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.base = Path(self._tmpdir.name) / "repo"
        self.linux_root = self.base / "tmp" / "linux_sandbox"
        self.oda_root = self.base / "tmp" / "oda_sandbox"
        self.linux_root.mkdir(parents=True)
        self.oda_root.mkdir(parents=True)
        self._roots_patch = patch.dict(
            "Apps.UI.views.SANDBOX_DEFAULT_ROOTS",
            {
                "linux_sandbox": ("tmp", "linux_sandbox"),
                "data_analysis": ("tmp", "oda_sandbox"),
            },
        )
        self._base_patch = patch("Apps.UI.views.settings.BASE_DIR", self.base)
        self._roots_patch.start()
        self._base_patch.start()
        self.client = Client()

    def tearDown(self):
        self._base_patch.stop()
        self._roots_patch.stop()
        self._tmpdir.cleanup()

    def test_sync_api_copies_workspace_files_into_target_mode(self):
        artifact = self.linux_root / "User" / "chat" / "result.csv"
        artifact.parent.mkdir(parents=True)
        artifact.write_text("1,2,3", encoding="utf-8")

        response = self.client.post(
            reverse("sandbox_sync_api"),
            data=json.dumps(
                {"source_mode": "linux_sandbox", "target_mode": "data_analysis"},
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertGreaterEqual(payload["stats"]["copied"], 1)
        copied = self.oda_root / "User" / "chat" / "result.csv"
        self.assertTrue(copied.is_file())
        self.assertEqual(copied.read_text(encoding="utf-8"), "1,2,3")

    def test_sync_api_rejects_unknown_mode(self):
        response = self.client.post(
            reverse("sandbox_sync_api"),
            data=json.dumps({"source_mode": "linux_sandbox", "target_mode": "unknown"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_sync_api_same_mode_reports_zero_copies(self):
        (self.linux_root / "only.txt").write_text("x", encoding="utf-8")
        response = self.client.post(
            reverse("sandbox_sync_api"),
            data=json.dumps(
                {"source_mode": "linux_sandbox", "target_mode": "linux_sandbox"},
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["stats"]["copied"], 0)


class SandboxFileHandoffTests(SimpleTestCase):
    """File visibility after merge-copy between sandbox trees."""

    def test_sync_then_shared_download_resolves_oda_container_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "repo"
            linux = base / "Tools" / "mcp-sandbox" / "_sandbox"
            oda = base / "Tools" / "open_data_analysis" / "tmp" / "_sandbox"
            source_file = linux / "User" / "handoff.txt"
            source_file.parent.mkdir(parents=True)
            source_file.write_text("handoff ok", encoding="utf-8")

            with patch("Apps.UI.views.settings.BASE_DIR", base):
                stats = _sync_sandbox_roots(
                    _sandbox_default_root("linux_sandbox"),
                    _sandbox_default_root("data_analysis"),
                )
                resolved = _resolve_shared_file_path("/mnt/data/_sandbox/User/handoff.txt")

            self.assertGreaterEqual(stats["copied"], 1)
            self.assertTrue(resolved.is_file())
            self.assertEqual(resolved.read_text(encoding="utf-8"), "handoff ok")

    def test_upload_manifest_still_resolves_linux_prefix_after_copy_to_oda(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "repo"
            linux = base / "Tools" / "mcp-sandbox" / "_sandbox" / "User" / "abc123"
            oda = base / "Tools" / "open_data_analysis" / "tmp" / "_sandbox"
            linux.mkdir(parents=True)
            oda.mkdir(parents=True)
            stored = linux / "file-id__notes.txt"
            stored.write_text("notes", encoding="utf-8")

            with patch.object(upload_storage, "SANDBOX_ROOT", base / "Tools" / "mcp-sandbox" / "_sandbox"), patch.object(
                upload_storage,
                "USER_UPLOAD_ROOT",
                base / "Tools" / "mcp-sandbox" / "_sandbox" / "User",
            ), patch.object(upload_storage, "ODA_SANDBOX_ROOT", oda):
                host_path = resolve_uploaded_file_host_path(
                    {"sandbox_path": "/workspace/_sandbox/User/abc123/file-id__notes.txt"},
                )
            self.assertEqual(host_path, stored.resolve())

            with patch.dict(
                "Apps.UI.views.SANDBOX_DEFAULT_ROOTS",
                {
                    "linux_sandbox": ("Tools", "mcp-sandbox", "_sandbox"),
                    "data_analysis": ("Tools", "open_data_analysis", "tmp", "_sandbox"),
                },
            ), patch("Apps.UI.views.settings.BASE_DIR", base):
                _sync_sandbox_roots(
                    _sandbox_default_root("linux_sandbox"),
                    _sandbox_default_root("data_analysis"),
                )
            oda_copy = oda / "User" / "abc123" / "file-id__notes.txt"
            self.assertTrue(oda_copy.is_file())


class SandboxModelContextTests(SimpleTestCase):
    """What the model sees when sandbox mode changes or stays the same."""

    def test_switch_notice_covers_both_directions(self):
        to_oda = _build_sandbox_mode_switch_notice("linux_sandbox", "data_analysis")
        to_linux = _build_sandbox_mode_switch_notice("data_analysis", "linux_sandbox")
        self.assertIn("/mnt/data/_sandbox", to_oda)
        self.assertIn("/workspace/_sandbox", to_linux)
        self.assertIn("Continue the current task seamlessly", to_oda)

    def test_inject_places_notice_after_base_system_prompt(self):
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Continue"},
        ]
        _maybe_inject_sandbox_mode_switch_notice(
            messages,
            data={
                "sandbox_mode_switch": {
                    "source_mode": "linux_sandbox",
                    "target_mode": "data_analysis",
                }
            },
            sandbox_enabled=True,
            sandbox_default_mode="data_analysis",
        )
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("Sandbox default changed", messages[1]["content"])
        self.assertEqual(messages[2]["role"], "user")

    def test_no_notice_without_switch_payload(self):
        messages = [{"role": "system", "content": "base"}, {"role": "user", "content": "hi"}]
        _maybe_inject_sandbox_mode_switch_notice(
            messages,
            data={},
            sandbox_enabled=True,
            sandbox_default_mode="data_analysis",
        )
        self.assertEqual(len(messages), 2)

    def test_no_notice_when_sandbox_tools_disabled(self):
        messages = [{"role": "system", "content": "base"}]
        _maybe_inject_sandbox_mode_switch_notice(
            messages,
            data={
                "sandbox_mode_switch": {
                    "source_mode": "linux_sandbox",
                    "target_mode": "data_analysis",
                }
            },
            sandbox_enabled=False,
            sandbox_default_mode="data_analysis",
        )
        self.assertEqual(len(messages), 1)

    def test_no_notice_when_default_mode_conflicts_with_switch_target(self):
        messages = [{"role": "system", "content": "base"}]
        _maybe_inject_sandbox_mode_switch_notice(
            messages,
            data={
                "sandbox_mode_switch": {
                    "source_mode": "linux_sandbox",
                    "target_mode": "data_analysis",
                }
            },
            sandbox_enabled=True,
            sandbox_default_mode="linux_sandbox",
        )
        self.assertEqual(len(messages), 1)


class SandboxBrowserScreenshotModeTests(SimpleTestCase):
    """Browser agent screenshot directory selection per sandbox default mode."""

    def _module_dir(self) -> str:
        return str(REPO_ROOT)

    def test_explicit_linux_sandbox_mode(self):
        sandbox_dir, prefix = _sandbox_screens_dir(
            {
                "module_dir": self._module_dir(),
                "sandbox_default_mode": "linux_sandbox",
                "sandbox_enabled": True,
            }
        )
        self.assertIsNotNone(sandbox_dir)
        self.assertEqual(prefix, SANDBOX_SCREEN_TARGETS["linux_sandbox"][1])
        self.assertTrue(str(sandbox_dir).replace("\\", "/").endswith("mcp-sandbox/_sandbox/screens"))

    def test_explicit_data_analysis_mode(self):
        sandbox_dir, prefix = _sandbox_screens_dir(
            {
                "module_dir": self._module_dir(),
                "sandbox_default_mode": "data_analysis",
                "sandbox_enabled": True,
            }
        )
        self.assertIsNotNone(sandbox_dir)
        self.assertEqual(prefix, "/mnt/data/_sandbox/screens")
        self.assertTrue(
            str(sandbox_dir).replace("\\", "/").endswith("open_data_analysis/tmp/_sandbox/screens")
        )

    def test_fallback_to_oda_when_oda_selected_without_explicit_mode(self):
        sandbox_dir, prefix = _sandbox_screens_dir(
            {
                "module_dir": self._module_dir(),
                "selected_tool_server_ids": ["browser_agent", "oda"],
                "sandbox_enabled": False,
            }
        )
        self.assertEqual(prefix, "/mnt/data/_sandbox/screens")

    def test_fallback_to_linux_when_sandbox_enabled_without_explicit_mode(self):
        sandbox_dir, prefix = _sandbox_screens_dir(
            {
                "module_dir": self._module_dir(),
                "selected_tool_server_ids": ["browser_agent", "sandbox"],
                "sandbox_enabled": True,
            }
        )
        self.assertEqual(prefix, "screens")

    def test_no_sandbox_dir_without_module_dir(self):
        sandbox_dir, prefix = _sandbox_screens_dir(
            {"sandbox_default_mode": "linux_sandbox", "sandbox_enabled": True}
        )
        self.assertIsNone(sandbox_dir)
        self.assertEqual(prefix, "")

    def test_model_facing_screenshot_path_per_mode(self):
        file_name = "screenshot_test.png"
        for mode, expected_prefix in (
            ("linux_sandbox", "screens"),
            ("data_analysis", "/mnt/data/_sandbox/screens"),
        ):
            _dir, prefix = _sandbox_screens_dir(
                {
                    "module_dir": self._module_dir(),
                    "sandbox_default_mode": mode,
                    "sandbox_enabled": True,
                }
            )
            model_path = f"{prefix}/{file_name}" if prefix else file_name
            self.assertEqual(model_path, f"{expected_prefix}/{file_name}")


class SandboxChatContextApiTests(ToolRegistryTestMixin, TestCase):
    """End-to-end LLM message list for sandbox mode changes."""

    def setUp(self):
        super().setUp()
        self.client = Client()

    def _post_chat(self, payload: dict) -> tuple[int, list[dict]]:
        with patch(
            "Apps.UI.views.llm_api.get_model_settings",
            return_value={
                "capabilities": ["tools"],
                "template": "{{ if .Tools }}{{ end }}{{ if .ToolCalls }}{{ end }}",
            },
        ), patch("Apps.UI.views.llm_api.prepare_runtime"), patch(
            "Apps.UI.views.llm_api.generate",
            return_value=[{"message": {"content": "Done"}}],
        ) as mock_generate, patch(
            "Apps.UI.views._get_active_engine",
            return_value="ollama-service",
        ):
            self.write_server(
                "sandbox",
                '''
                MCP_SERVER = {"id": "sandbox", "name": "Sandbox"}
                TOOLS = [{"id": "write", "name": "Write", "parameters": {"type": "object", "properties": {}}}]
                def call_tool(tool_id, arguments, context=None):
                    return "ok"
                ''',
            )
            response = self.client.post(
                reverse("chat_api"),
                data=json.dumps(payload),
                content_type="application/json",
            )
            if response.status_code == 200:
                b"".join(response.streaming_content)
            messages = (
                mock_generate.call_args.kwargs["messages"]
                if mock_generate.call_args
                else []
            )
        return response.status_code, messages

    def _system_contents(self, messages: list[dict]) -> list[str]:
        return [str(item.get("content") or "") for item in messages if item.get("role") == "system"]

    def test_messages_include_switch_notice_only_when_announced(self):
        status, messages = self._post_chat(
            {
                "message": "Continue analysis",
                "model": "llama3.1",
                "tool_server_ids": ["sandbox"],
                "sandbox_default_mode": "data_analysis",
                "sandbox_mode_switch": {
                    "source_mode": "linux_sandbox",
                    "target_mode": "data_analysis",
                },
            }
        )
        self.assertEqual(status, 200)
        system_texts = self._system_contents(messages)
        self.assertEqual(len(system_texts), 2)
        self.assertIn("Sandbox default changed", system_texts[1])

    def test_messages_omit_switch_notice_on_regular_turn(self):
        status, messages = self._post_chat(
            {
                "message": "Hello",
                "model": "llama3.1",
                "tool_server_ids": ["sandbox"],
                "sandbox_default_mode": "data_analysis",
            }
        )
        self.assertEqual(status, 200)
        switch_notices = [
            text for text in self._system_contents(messages) if "Sandbox default changed" in text
        ]
        self.assertEqual(switch_notices, [])

    def test_tool_context_carries_active_sandbox_default_mode(self):
        _status, _messages, tool_context = self._post_chat_with_tool_context(
            {
                "message": "Run in ODA sandbox",
                "model": "llama3.1",
                "tool_server_ids": ["sandbox"],
                "sandbox_default_mode": "data_analysis",
            }
        )
        self.assertEqual(tool_context["sandbox_default_mode"], "data_analysis")
        self.assertTrue(tool_context["sandbox_enabled"])

    def _post_chat_with_tool_context(self, payload: dict) -> tuple[int, list[dict], dict]:
        with patch(
            "Apps.UI.views.llm_api.get_model_settings",
            return_value={
                "capabilities": ["tools"],
                "template": "{{ if .Tools }}{{ end }}{{ if .ToolCalls }}{{ end }}",
            },
        ), patch("Apps.UI.views.llm_api.prepare_runtime"), patch(
            "Apps.UI.views.llm_api.generate",
            return_value=[{"message": {"content": "Done"}}],
        ) as mock_generate, patch(
            "Apps.UI.views._get_active_engine",
            return_value="ollama-service",
        ):
            self.write_server(
                "sandbox",
                '''
                MCP_SERVER = {"id": "sandbox", "name": "Sandbox"}
                TOOLS = [{"id": "write", "name": "Write", "parameters": {"type": "object", "properties": {}}}]
                def call_tool(tool_id, arguments, context=None):
                    return "ok"
                ''',
            )
            response = self.client.post(
                reverse("chat_api"),
                data=json.dumps(payload),
                content_type="application/json",
            )
            if response.status_code == 200:
                b"".join(response.streaming_content)
            tool_context = mock_generate.call_args.kwargs.get("tool_context", {}) if mock_generate.call_args else {}
            messages = mock_generate.call_args.kwargs.get("messages", []) if mock_generate.call_args else []
        return response.status_code, messages, tool_context


class SandboxUploadRoutingTests(TestCase):
    """Upload storage targets and model-facing manifest exposure."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.base = Path(self._tmpdir.name)
        self.sandbox_user = self.base / "sandbox" / "User"
        self.oda_root = self.base / "oda"
        self.sandbox_user.mkdir(parents=True)
        self.oda_root.mkdir(parents=True)
        self.manifest_root = self.base / "manifests"
        self.manifest_root.mkdir(parents=True)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_resolve_upload_target_routes_by_tool_server(self):
        linux = resolve_upload_storage_target(["sandbox"])
        oda = resolve_upload_storage_target(["oda"])
        self.assertEqual(linux.server_id, "sandbox")
        self.assertEqual(oda.server_id, "oda")
        self.assertIn("mcp-sandbox", str(linux.upload_root).replace("\\", "/"))
        self.assertIn("open_data_analysis", str(oda.upload_root).replace("\\", "/"))

    def test_model_manifest_hides_sandbox_path_when_tool_not_selected(self):
        manifest = {
            "file_id": "f-1",
            "name": "a.txt",
            "mime": "text/plain",
            "size_bytes": 3,
            "sha256": "abc",
            "sandbox_path": "/workspace/_sandbox/User/chat/f-1__a.txt",
            "recommended_tools": ["sandbox"],
        }
        with patch("Apps.UI.views.load_upload_manifest", return_value=manifest):
            hidden = _load_model_upload_manifests(["f-1"], sandbox_enabled=False)[0]
            shown = _load_model_upload_manifests(["f-1"], sandbox_enabled=True)[0]
        self.assertIsNone(hidden["sandbox_path"])
        self.assertEqual(shown["sandbox_path"], manifest["sandbox_path"])
