# Copyright NGGT.LightKeeper. All Rights Reserved.

from __future__ import annotations

import json
import io
import os
import tempfile
import textwrap
import zipfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from API import google_genai as google_genai_api
from API import llm_api
from API import mcp as tool_registry
from API.google_genai import (
    generate as generate_google_genai,
    get_model_settings as get_google_genai_model_settings,
    get_models as get_google_genai_models,
)
from API.lms import (
    _prepare_openai_prediction_options,
    _serialize_model_info,
    get_model_settings as get_lms_model_settings,
)
from API.ollama import _prepare_chat_kwargs, prepare_runtime as prepare_ollama_runtime
from API.openai import (
    _build_openai_request_options,
    generate as generate_openai,
    get_model_settings as get_openai_model_settings,
)
from Settings import settings as project_settings
from Settings import skills as skills_config
from Apps.Data.models import (
    Chat,
    LmsPreset,
    Message,
    MessageAttachment,
    MessageAttachmentKind,
    MessageImage,
    OllamaPreset,
)
from Apps.UI import upload_storage
from Apps.UI.file_manifests import (
    TEXT_PREVIEW_CHAR_LIMIT,
    build_uploaded_file_manifest,
    normalize_upload_name,
)
from Apps.UI.upload_storage import display_kind_for_upload
from Apps.UI.views import (
    _build_activity_segments,
    _build_chat_history,
    _build_chat_title,
    _build_model_info_payload,
    _build_uploaded_file_context_entry,
    _build_uploaded_file_prompt_block,
    _clear_model_metadata_caches,
    _compose_system_prompt,
    _extract_attachment_text,
    _extract_uploaded_file_ids_from_message,
    _extract_ollama_model_info,
    _extract_model_name,
    _format_runtime_error,
    _is_active_browser_portal_state,
    _load_model_upload_manifests,
    _normalize_request_attachments,
    _normalize_uploaded_file_ids,
    _parse_active_tool_slugs,
    _resolve_history_char_budget,
    _serialize_attachment_record,
    _selected_tools_include_sandbox,
    _stream_chat_response,
    _strip_llm_control_tokens,
)


# Small structured error helper for Google GenAI adapter tests.
class FakeGoogleError(Exception):
    """Small structured error helper for Google GenAI adapter tests."""

    # Initialize the instance.
    def __init__(
        self,
        code: int,
        status: str,
        message: str,
        *,
        details: list[dict[str, object]] | None = None,
    ) -> None:
        self.code = code
        self.status = status
        self.message = message
        self.details = {
            "error": {
                "code": code,
                "status": status,
                "message": message,
                "details": details or [],
            }
        }
        super().__init__(f"{code} {status}. {self.details}")


# Shared test helpers.

# Patch the local tools directory for endpoint tests.
class ToolRegistryTestMixin:
    """Patch the local tools directory for endpoint tests."""

    # Create an isolated tools directory.
    def setUp(self):
        super().setUp()
        self._tools_dir_context = tempfile.TemporaryDirectory()
        self.tools_dir = Path(self._tools_dir_context.name)
        self.tools_patch = patch.object(tool_registry, "TOOLS_DIR", self.tools_dir)
        self.tools_patch.start()
        tool_registry.reset_cache()
        _clear_model_metadata_caches()

    # Restore the original registry state.
    def tearDown(self):
        tool_registry.reset_cache()
        _clear_model_metadata_caches()
        self.tools_patch.stop()
        self._tools_dir_context.cleanup()
        super().tearDown()

    # Write a temporary MCP server.
    def write_server(self, folder: str, body: str) -> None:
        server_dir = self.tools_dir / folder
        server_dir.mkdir(parents=True, exist_ok=True)
        (server_dir / "mcp-server.py").write_text(
            textwrap.dedent(body).strip() + "\n",
            encoding="utf-8",
        )
        tool_registry.reset_cache()

# Model and adapter parsing tests.


class SkillsApiTests(TestCase):
    """Cover project skill file management APIs."""

    def setUp(self):
        super().setUp()
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.skills_dir = self.root / "Skills"
        self.sandbox_skills_dir = self.root / "Tools" / "mcp-sandbox" / "_sandbox" / "Skills"
        self._patches = [
            patch.object(skills_config, "BASE_DIR", self.root),
            patch.object(skills_config, "SKILLS_DIR", self.skills_dir),
            patch.object(skills_config, "SANDBOX_SKILLS_DIR", self.sandbox_skills_dir),
        ]
        for patcher in self._patches:
            patcher.start()
        self.client = Client()

    def tearDown(self):
        for patcher in reversed(self._patches):
            patcher.stop()
        self._tmp.cleanup()
        super().tearDown()

    def test_skills_root_created_and_crud_validates_paths(self):
        response = self.client.get(reverse("skills_api"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.skills_dir.is_dir())

        created = self.client.post(
            reverse("skills_api"),
            data=json.dumps({"name": "skill-creator"}),
            content_type="application/json",
        )
        self.assertEqual(created.status_code, 200)
        self.assertTrue((self.skills_dir / "skill-creator" / "SKILL.md").is_file())

        saved = self.client.put(
            reverse("skills_file_api"),
            data=json.dumps({
                "folder": "skill-creator",
                "file": "agents/grader.md",
                "content": "---\nname: skill-creator\ndescription: Make skills\nenabled: true\n---\n\n# Skill\n",
            }),
            content_type="application/json",
        )
        self.assertEqual(saved.status_code, 200)
        self.assertTrue((self.skills_dir / "skill-creator" / "agents" / "grader.md").is_file())

        renamed = self.client.patch(
            reverse("skills_folder_api"),
            data=json.dumps({"old_name": "skill-creator", "new_name": "renamed-skill"}),
            content_type="application/json",
        )
        self.assertEqual(renamed.status_code, 200)
        self.assertTrue((self.skills_dir / "renamed-skill" / "SKILL.md").is_file())
        self.assertEqual(renamed.json()["folders"][0]["title"], "renamed-skill")

        rejected = self.client.put(
            reverse("skills_file_api"),
            data=json.dumps({"folder": "renamed-skill", "file": "../bad.md", "content": "x"}),
            content_type="application/json",
        )
        self.assertEqual(rejected.status_code, 400)

    def test_front_matter_summary_and_prompt_inventory(self):
        skill_root = self.skills_dir / "skill-creator"
        skill_root.mkdir(parents=True)
        (skill_root / "SKILL.md").write_text(
            "---\n"
            "name: skill-creator\n"
            "description: Create and improve skills.\n"
            "trigger: Slash command + auto\n"
            "added_by: Anthropic\n"
            "enabled: true\n"
            "---\n\n# Skill Creator\n",
            encoding="utf-8",
        )
        agents_dir = skill_root / "agents"
        agents_dir.mkdir()
        (agents_dir / "grader.md").write_text("# Grader\n", encoding="utf-8")

        payload = self.client.get(reverse("skills_api")).json()
        folder = payload["folders"][0]
        self.assertEqual(folder["title"], "skill-creator")
        self.assertEqual(folder["description"], "Create and improve skills.")
        self.assertEqual(folder["source"], "download")
        self.assertIsInstance(folder["created_at"], float)
        self.assertGreater(folder["created_at"], 0)

        prompt = _compose_system_prompt("")
        self.assertIn("Your skills:", prompt)
        self.assertIn("Sandbox path: /workspace/_sandbox/Skills", prompt)
        self.assertIn(str(self.skills_dir), prompt)
        self.assertIn("/workspace/_sandbox/Skills/skill-creator", prompt)
        self.assertIn("SKILL.md", prompt)
        self.assertIn("agents/grader.md", prompt)
        self.assertNotIn("# Skill Creator", prompt)
        self.assertNotIn("# Grader", prompt)

        disabled_root = self.skills_dir / "disabled-skill"
        disabled_root.mkdir()
        (disabled_root / "SKILL.md").write_text(
            "---\nname: disabled\ndescription: Off\nenabled: false\n---\n",
            encoding="utf-8",
        )
        prompt_with_disabled = _compose_system_prompt("")
        self.assertNotIn("disabled-skill", prompt_with_disabled)

    def test_sync_mirrors_skills_and_overrides_sandbox(self):
        skill_root = self.skills_dir / "writer"
        skill_root.mkdir(parents=True)
        (skill_root / "SKILL.md").write_text("# Writer\n", encoding="utf-8")
        stale_root = self.sandbox_skills_dir / "writer"
        stale_root.mkdir(parents=True)
        (stale_root / "SKILL.md").write_text("stale\n", encoding="utf-8")
        (self.sandbox_skills_dir / "extra.txt").write_text("remove\n", encoding="utf-8")

        result = skills_config.sync_skills_to_sandbox()

        self.assertGreaterEqual(result["copied"], 1)
        self.assertEqual((self.sandbox_skills_dir / "writer" / "SKILL.md").read_text(encoding="utf-8"), "# Writer\n")
        self.assertFalse((self.sandbox_skills_dir / "extra.txt").exists())

    def test_create_skill_subdirectory(self):
        skill_root = self.skills_dir / "my-skill"
        skill_root.mkdir(parents=True)
        (skill_root / "SKILL.md").write_text("# My Skill\n", encoding="utf-8")

        response = self.client.post(
            reverse("skills_directory_api"),
            data=json.dumps({"folder": "my-skill", "path": "agents"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue((skill_root / "agents").is_dir())

        nested_response = self.client.post(
            reverse("skills_directory_api"),
            data=json.dumps({"folder": "my-skill", "path": "agents/tools"}),
            content_type="application/json",
        )
        self.assertEqual(nested_response.status_code, 200)
        self.assertTrue((skill_root / "agents" / "tools").is_dir())

    def test_create_skill_subdirectory_rejects_duplicate(self):
        skill_root = self.skills_dir / "my-skill"
        skill_root.mkdir(parents=True)
        (skill_root / "agents").mkdir()

        response = self.client.post(
            reverse("skills_directory_api"),
            data=json.dumps({"folder": "my-skill", "path": "agents"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_create_skill_subdirectory_rejects_traversal(self):
        skill_root = self.skills_dir / "my-skill"
        skill_root.mkdir(parents=True)

        response = self.client.post(
            reverse("skills_directory_api"),
            data=json.dumps({"folder": "my-skill", "path": "../escape"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_create_skill_subdirectory_rejects_file_extension(self):
        skill_root = self.skills_dir / "my-skill"
        skill_root.mkdir(parents=True)

        response = self.client.post(
            reverse("skills_directory_api"),
            data=json.dumps({"folder": "my-skill", "path": "agents.md"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_rename_and_delete_skill_subdirectory(self):
        skill_root = self.skills_dir / "my-skill"
        skill_root.mkdir(parents=True)
        (skill_root / "agents").mkdir()
        (skill_root / "agents" / "grader.md").write_text("# Grader\n", encoding="utf-8")

        renamed = self.client.patch(
            reverse("skills_path_api"),
            data=json.dumps({
                "folder": "my-skill",
                "old_path": "agents",
                "new_path": "reviewers",
                "kind": "directory",
            }),
            content_type="application/json",
        )
        self.assertEqual(renamed.status_code, 200)
        self.assertTrue((skill_root / "reviewers" / "grader.md").is_file())
        self.assertFalse((skill_root / "agents").exists())

        deleted = self.client.delete(
            reverse("skills_directory_api"),
            data=json.dumps({"folder": "my-skill", "path": "reviewers"}),
            content_type="application/json",
        )
        self.assertEqual(deleted.status_code, 200)
        self.assertFalse((skill_root / "reviewers").exists())

    def test_rename_skill_file(self):
        skill_root = self.skills_dir / "my-skill"
        skill_root.mkdir(parents=True)
        (skill_root / "notes.md").write_text("# Notes\n", encoding="utf-8")

        renamed = self.client.patch(
            reverse("skills_path_api"),
            data=json.dumps({
                "folder": "my-skill",
                "old_path": "notes.md",
                "new_path": "journal.md",
                "kind": "file",
            }),
            content_type="application/json",
        )
        self.assertEqual(renamed.status_code, 200)
        self.assertTrue((skill_root / "journal.md").is_file())
        self.assertFalse((skill_root / "notes.md").exists())

    def test_import_skill_creates_folder_and_files(self):
        files = [
            {"path": "SKILL.md", "content": "---\nname: imported\ndescription: Test import\nenabled: true\n---\n\n# Imported\n"},
            {"path": "agents/grader.md", "content": "# Grader\n"},
            {"path": "../escape.md", "content": "bad"},   # should be silently skipped
            {"path": "binary\x00.md", "content": "bad"},  # should be skipped
        ]
        response = self.client.post(
            reverse("skills_import_api"),
            data=json.dumps({"name": "imported-skill", "files": files}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        skill_root = self.skills_dir / "imported-skill"
        self.assertTrue((skill_root / "SKILL.md").is_file())
        self.assertTrue((skill_root / "agents" / "grader.md").is_file())
        self.assertFalse((self.skills_dir / "escape.md").exists())
        payload = response.json()
        folder_names = [f["name"] for f in payload["folders"]]
        self.assertIn("imported-skill", folder_names)
        imported = next(f for f in payload["folders"] if f["name"] == "imported-skill")
        self.assertEqual(imported["description"], "Test import")

    def test_import_skill_merges_into_existing_folder(self):
        skill_root = self.skills_dir / "duplicate-skill"
        skill_root.mkdir(parents=True)
        (skill_root / "SKILL.md").write_text("# Duplicate\n", encoding="utf-8")

        response = self.client.post(
            reverse("skills_import_api"),
            data=json.dumps({
                "name": "duplicate-skill",
                "files": [{"path": "notes.md", "content": "# Notes\n"}],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue((skill_root / "notes.md").is_file())
        payload = response.json()
        folder_names = [f["name"] for f in payload["folders"]]
        self.assertIn("duplicate-skill", folder_names)


class SkillsSandboxDispatchTests(SimpleTestCase):
    """Ensure sandbox dispatch refreshes Skills before executing a tool."""

    def test_sandbox_tool_dispatch_syncs_skills_first(self):
        server = {
            "id": "sandbox",
            "name": "Sandbox",
            "description": "",
            "tools": [{"id": "write", "alias": "sandbox__write", "name": "Write", "description": ""}],
            "module": None,
            "supports": None,
            "server_callable": None,
            "tool_handlers": {"write": lambda arguments, context=None: {"ok": True, "result": arguments}},
            "server_file": Path("Tools/mcp-sandbox/mcp-server.py"),
            "external": False,
        }
        lookup = {"sandbox__write": {"server": server, "tool": server["tools"][0]}}

        with patch.object(skills_config, "sync_skills_to_sandbox") as sync_mock:
            result = tool_registry.call_ollama_tool(lookup, "sandbox__write", {"path": "x.txt"})

        sync_mock.assert_called_once()
        self.assertIn("x.txt", str(result))


# Cover per-response tool quota guardrails.
class ToolQuotaTests(SimpleTestCase):
    """Cover search-effort quotas used by the shared tool bridge."""

    # High-effort web search is expensive, so keep it bounded per response.
    def test_high_effort_web_search_limits_to_three_calls(self):
        tool_event = {"tool_id": "web_search", "tool_name": "Web search"}
        counters: dict[str, int] = {}
        arguments = {"query": "cheap coding model", "effort": "high"}

        self.assertIsNone(tool_registry.consume_tool_quota(tool_event, counters, arguments=arguments))
        self.assertIsNone(tool_registry.consume_tool_quota(tool_event, counters, arguments=arguments))
        self.assertIsNone(tool_registry.consume_tool_quota(tool_event, counters, arguments=arguments))

        error = tool_registry.consume_tool_quota(tool_event, counters, arguments=arguments)
        self.assertIsNotNone(error)
        self.assertIn("high mode is unavailable", str(error))
        self.assertIn("use medium or low", str(error))

    # Lower-effort searches keep the existing broader budget.
    def test_normal_web_search_keeps_default_quota(self):
        tool_event = {"tool_id": "web_search", "tool_name": "Web search"}
        counters: dict[str, int] = {}
        arguments = {"query": "cheap coding model", "effort": "medium"}

        for _index in range(4):
            self.assertIsNone(tool_registry.consume_tool_quota(tool_event, counters, arguments=arguments))

# Cover adapter-specific model list formats.
class ModelNameExtractionTests(SimpleTestCase):
    """Cover adapter-specific model list formats."""

    # Test extracts name from string.
    def test_extracts_name_from_string(self):
        self.assertEqual(_extract_model_name("llama3"), "llama3")

    # Test extracts name from mapping.
    def test_extracts_name_from_mapping(self):
        self.assertEqual(_extract_model_name({"model": "qwen"}), "qwen")
        self.assertEqual(_extract_model_name({"name": "gpt-oss"}), "gpt-oss")
        self.assertEqual(_extract_model_name({"model_key": "mistral-nemo"}), "mistral-nemo")

    # Test prefers id over friendly name.
    def test_prefers_id_over_friendly_name(self):
        self.assertEqual(
            _extract_model_name({"id": "openai/gpt-oss-20b", "name": "OpenAI: GPT OSS 20B"}),
            "openai/gpt-oss-20b",
        )


# Attachment normalization tests.

# Cover fast attachment validation helpers.
class AttachmentNormalizationTests(SimpleTestCase):
    """Cover fast attachment validation helpers."""

    # Test invalid base64 attachments are ignored before persistence.
    def test_invalid_base64_attachments_are_ignored(self):
        self.assertEqual(
            _normalize_request_attachments({
                "attachments": [{"name": "bad.txt", "mime_type": "text/plain", "data": "not valid !!!"}],
            }),
            [],
        )

    # Test data URL attachments keep MIME, filename and decoded size.
    def test_data_url_attachments_are_normalized_for_storage(self):
        attachments = _normalize_request_attachments({
            "attachments": [
                {
                    "name": "note.txt",
                    "data_url": "data:text/plain;base64,SGVsbG8=",
                },
            ],
        })

        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0]["kind"], MessageAttachmentKind.FILE)
        self.assertEqual(attachments[0]["name"], "note.txt")
        self.assertEqual(attachments[0]["mime_type"], "text/plain")
        self.assertEqual(attachments[0]["data"], "SGVsbG8=")
        self.assertEqual(attachments[0]["size_bytes"], 5)
        self.assertEqual(attachments[0]["order"], 0)

    # Test legacy image payloads are detected and named.
    def test_legacy_image_payloads_are_normalized_with_detected_mime(self):
        attachments = _normalize_request_attachments({
            "images": ["iVBORw0KGgo="],
        })

        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0]["kind"], MessageAttachmentKind.IMAGE)
        self.assertEqual(attachments[0]["name"], "image-1")
        self.assertEqual(attachments[0]["mime_type"], "image/png")
        self.assertEqual(attachments[0]["order"], 0)

    # Test empty entries are skipped without breaking later order values.
    def test_attachment_order_uses_surviving_items_only(self):
        attachments = _normalize_request_attachments({
            "attachments": [
                {"name": "bad.txt", "mime_type": "text/plain", "data": ""},
                {"name": "ok.txt", "mime_type": "text/plain", "data": "T0s="},
            ],
        })

        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0]["name"], "ok.txt")
        self.assertEqual(attachments[0]["order"], 0)


# Attachment extraction tests.
# Cover prompt text extraction and database caching for stored files.
class AttachmentExtractionTests(TestCase):
    """Cover file extraction helpers used before model generation."""

    # Cache extracted text back onto the attachment record.
    def test_text_attachment_extraction_is_cached_on_record(self):
        chat = Chat.objects.create(title="Chat")
        message = Message.objects.create(chat=chat, role="user", content="See file")
        attachment = MessageAttachment.objects.create(
            message=message,
            kind=MessageAttachmentKind.FILE,
            name="note.txt",
            mime_type="text/plain",
            data="SGVsbG8gZnJvbSBmaWxl",
            size_bytes=15,
        )
        payload = _serialize_attachment_record(attachment)

        extracted_text = _extract_attachment_text(payload)

        attachment.refresh_from_db()
        self.assertEqual(extracted_text, "Hello from file")
        self.assertTrue(attachment.extracted_text_ready)
        self.assertEqual(attachment.extracted_text, "Hello from file")

    # Reuse cached text without trying to decode a broken payload.
    def test_cached_attachment_text_is_reused(self):
        chat = Chat.objects.create(title="Chat")
        message = Message.objects.create(chat=chat, role="user", content="See file")
        attachment = MessageAttachment.objects.create(
            message=message,
            kind=MessageAttachmentKind.FILE,
            name="note.txt",
            mime_type="text/plain",
            data="not valid !!!",
            extracted_text="Cached text",
            extracted_text_ready=True,
        )
        payload = _serialize_attachment_record(attachment)

        self.assertEqual(_extract_attachment_text(payload), "Cached text")


# Uploaded file manifest tests.

# Cover the standalone manifest builder used by the upload layer.
class UploadedFileManifestTests(SimpleTestCase):
    """Cover safe file manifest generation."""

    # Test text files expose bounded previews instead of unbounded content.
    def test_text_manifest_uses_bounded_preview(self):
        content = ("hello\n" * (TEXT_PREVIEW_CHAR_LIMIT // 6 + 100)).encode("utf-8")

        manifest = build_uploaded_file_manifest(
            content,
            name="notes.md",
            mime="text/markdown",
            sandbox_path="/workspace/_sandbox/User/chat/file__notes.md",
            file_id="file-1",
        )

        self.assertEqual(manifest.file_id, "file-1")
        self.assertEqual(manifest.name, "notes.md")
        self.assertEqual(manifest.mime, "text/markdown")
        self.assertTrue(manifest.text_available)
        self.assertTrue(manifest.text_truncated)
        self.assertLessEqual(len(manifest.text_preview or ""), TEXT_PREVIEW_CHAR_LIMIT + 20)
        self.assertEqual(manifest.sandbox_path, "/workspace/_sandbox/User/chat/file__notes.md")
        self.assertIn("sandbox", manifest.recommended_tools)
        self.assertIn("file_search", manifest.recommended_tools)

    # Test binary-looking files do not get decoded through permissive encodings.
    def test_binary_manifest_does_not_expose_text_preview(self):
        payload = b"MZ\x00\x00\x03\x00" + bytes(range(32)) * 8

        manifest = build_uploaded_file_manifest(
            payload,
            name="tool.exe",
            mime="application/octet-stream",
            sandbox_path="/workspace/_sandbox/User/chat/file__tool.exe",
        )

        self.assertFalse(manifest.text_available)
        self.assertIsNone(manifest.text_preview)
        self.assertIsNone(manifest.text_total_chars)
        self.assertEqual(manifest.archive_tree, None)
        self.assertEqual(manifest.recommended_tools, ["sandbox"])

    # Test uploaded names are reduced to safe basenames.
    def test_upload_name_is_normalized_to_basename(self):
        self.assertEqual(normalize_upload_name("../secrets/.env"), ".env")
        self.assertEqual(normalize_upload_name(r"..\..\report.pdf"), "report.pdf")

    # Test zip files include a bounded archive tree without unpacking.
    def test_zip_manifest_includes_archive_tree(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("docs/readme.txt", "hello")
            archive.writestr("src/app.py", "print('ok')")

        manifest = build_uploaded_file_manifest(
            buffer.getvalue(),
            name="bundle.zip",
            mime="application/zip",
            sandbox_path="/workspace/_sandbox/User/chat/file__bundle.zip",
        )

        self.assertEqual(manifest.archive_tree, ["docs/readme.txt", "src/app.py"])
        self.assertIn("archive", manifest.recommended_tools)

    # Test PDF files with a text layer expose a model-readable preview.
    def test_pdf_manifest_extracts_text_layer(self):
        import fitz

        document = fitz.open()
        page = document.new_page()
        page.insert_text((72, 72), "PDF upload text layer")
        payload = document.tobytes()
        document.close()

        manifest = build_uploaded_file_manifest(
            payload,
            name="statement.pdf",
            mime="application/pdf",
        )

        self.assertTrue(manifest.text_available)
        self.assertIn("PDF upload text layer", manifest.text_preview or "")

    # Test docx files expose text from their document XML.
    def test_docx_manifest_extracts_document_xml_text(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr(
                "word/document.xml",
                """
                <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
                  <w:body><w:p><w:r><w:t>Word upload text</w:t></w:r></w:p></w:body>
                </w:document>
                """,
            )

        manifest = build_uploaded_file_manifest(
            buffer.getvalue(),
            name="report.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

        self.assertTrue(manifest.text_available)
        self.assertIn("Word upload text", manifest.text_preview or "")

    # Test pptx files expose slide text from their slide XML.
    def test_pptx_manifest_extracts_slide_text(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr(
                "ppt/slides/slide1.xml",
                """
                <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
                       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
                  <p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>Slide upload text</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld>
                </p:sld>
                """,
            )

        manifest = build_uploaded_file_manifest(
            buffer.getvalue(),
            name="slides.pptx",
            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )

        self.assertTrue(manifest.text_available)
        self.assertIn("Slide 1: Slide upload text", manifest.text_preview or "")

    # Test xlsx files expose a small table preview from worksheet XML.
    def test_xlsx_manifest_extracts_sheet_text(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr(
                "xl/sharedStrings.xml",
                """
                <sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
                  <si><t>Name</t></si><si><t>Alice</t></si>
                </sst>
                """,
            )
            archive.writestr(
                "xl/worksheets/sheet1.xml",
                """
                <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
                  <sheetData>
                    <row><c t="s"><v>0</v></c><c><v>42</v></c></row>
                    <row><c t="s"><v>1</v></c><c><v>7</v></c></row>
                  </sheetData>
                </worksheet>
                """,
            )

        manifest = build_uploaded_file_manifest(
            buffer.getvalue(),
            name="sheet.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        self.assertTrue(manifest.text_available)
        self.assertIn("Name | 42", manifest.text_preview or "")
        self.assertIn("Alice | 7", manifest.table_preview or "")

    # Test non-vision image uploads keep metadata and sandbox access only.
    def test_non_vision_image_manifest_keeps_sandbox_without_text(self):
        manifest = build_uploaded_file_manifest(
            b"\x89PNG\r\n\x1a\n",
            name="photo.png",
            mime="image/png",
            sandbox_path="/workspace/_sandbox/User/chat/file__photo.png",
            model_supports_vision=False,
        )

        self.assertFalse(manifest.vision_available)
        self.assertFalse(manifest.text_available)
        self.assertEqual(manifest.sandbox_path, "/workspace/_sandbox/User/chat/file__photo.png")
        self.assertEqual(manifest.recommended_tools, ["sandbox"])


# Upload API tests.

# Cover the public upload contract without exposing model-only manifests.
class UploadFilesApiTests(SimpleTestCase):
    """Cover the user-facing upload API payload."""

    # Isolate sandbox writes in a temporary directory.
    def setUp(self):
        super().setUp()
        self._upload_root_context = tempfile.TemporaryDirectory()
        self._manifest_root_context = tempfile.TemporaryDirectory()
        self.upload_root = Path(self._upload_root_context.name)
        self.manifest_root = Path(self._manifest_root_context.name)
        self.upload_root_patch = patch.object(upload_storage, "USER_UPLOAD_ROOT", self.upload_root)
        self.manifest_root_patch = patch.object(upload_storage, "USER_FILE_MANIFEST_ROOT", self.manifest_root)
        self.upload_root_patch.start()
        self.manifest_root_patch.start()

    # Clean up the temporary sandbox.
    def tearDown(self):
        self.manifest_root_patch.stop()
        self.upload_root_patch.stop()
        self._manifest_root_context.cleanup()
        self._upload_root_context.cleanup()
        super().tearDown()

    # Test the upload API returns only card-safe fields while storing a private manifest.
    def test_upload_api_returns_public_file_card_payload_only(self):
        upload = SimpleUploadedFile("notes.txt", b"Hello from upload", content_type="text/plain")

        response = self.client.post(reverse("uploads_api"), {"files": [upload], "scope": "chat-1"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["files"]), 1)
        public_file = payload["files"][0]
        self.assertEqual(public_file["name"], "notes.txt")
        self.assertEqual(public_file["status"], "ready")
        self.assertEqual(public_file["display_kind"], "text")
        self.assertEqual(public_file["type_label"], "Text file")
        self.assertNotIn("sha256", public_file)
        self.assertNotIn("sandbox_path", public_file)
        self.assertNotIn("text_preview", public_file)

        self.assertEqual(list(self.upload_root.glob("chat-1/*.manifest.json")), [])
        self.assertEqual(list(self.upload_root.glob("pending/*.manifest.json")), [])
        manifests = list(self.manifest_root.glob("*/*.manifest.json"))
        self.assertEqual(len(manifests), 1)
        private_manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
        self.assertEqual(manifests[0].name, f"{public_file['file_id']}.manifest.json")
        self.assertEqual(private_manifest["text_preview"], "Hello from upload")
        self.assertEqual(manifests[0].parent.name, private_manifest["sha256"])
        self.assertTrue(private_manifest["sandbox_path"].startswith(f"/workspace/_sandbox/User/{private_manifest['sha256']}/"))

    # Test archive uploads get a simple English card label.
    def test_upload_api_labels_zip_archive_for_card(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("readme.txt", "hello")
        upload = SimpleUploadedFile("bundle.zip", buffer.getvalue(), content_type="application/zip")

        response = self.client.post(reverse("uploads_api"), {"files": [upload]})

        self.assertEqual(response.status_code, 200)
        public_file = response.json()["files"][0]
        self.assertEqual(public_file["display_kind"], "archive")
        self.assertEqual(public_file["type_label"], "ZIP archive")

    # Test unusual extensions are accepted and routed as generic files.
    def test_upload_api_accepts_unknown_extension_as_generic_file(self):
        upload = SimpleUploadedFile(
            "sample.abc",
            b"custom binary-ish payload",
            content_type="application/x-abc",
        )

        response = self.client.post(reverse("uploads_api"), {"files": [upload], "scope": "chat-abc"})

        self.assertEqual(response.status_code, 200)
        public_file = response.json()["files"][0]
        self.assertEqual(public_file["name"], "sample.abc")
        self.assertEqual(public_file["status"], "ready")
        self.assertEqual(public_file["display_kind"], "file")
        self.assertEqual(public_file["type_label"], "File")

        self.assertEqual(list(self.upload_root.glob("chat-abc/*.manifest.json")), [])
        self.assertEqual(list(self.upload_root.glob("pending/*.manifest.json")), [])
        manifests = list(self.manifest_root.glob("*/*.manifest.json"))
        self.assertEqual(len(manifests), 1)
        private_manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
        self.assertEqual(manifests[0].parent.name, private_manifest["sha256"])
        self.assertEqual(private_manifest["name"], "sample.abc")
        self.assertEqual(private_manifest["mime"], "application/x-abc")
        self.assertFalse(private_manifest["text_available"])
        self.assertTrue(private_manifest["sandbox_path"].startswith(f"/workspace/_sandbox/User/{private_manifest['sha256']}/"))

    # Test the configured upload ceiling matches the advertised large-video contract.
    def test_upload_limit_is_16_gb(self):
        self.assertEqual(upload_storage.MAX_UPLOAD_BYTES, 16 * 1024 * 1024 * 1024)

    # Test uploads beyond the inline manifest threshold are stored without full in-memory extraction.
    def test_upload_api_uses_lightweight_manifest_after_inline_threshold(self):
        upload = SimpleUploadedFile("clip.mp4", b"12345", content_type="video/mp4")

        with patch.object(upload_storage, "INLINE_MANIFEST_MAX_BYTES", 4):
            response = self.client.post(reverse("uploads_api"), {"files": [upload], "scope": "chat-video"})

        self.assertEqual(response.status_code, 200)
        public_file = response.json()["files"][0]
        self.assertEqual(public_file["status"], "ready")
        self.assertEqual(public_file["display_kind"], "video")
        self.assertEqual(public_file["type_label"], "Video")

        manifests = list(self.manifest_root.glob("*/*.manifest.json"))
        self.assertEqual(len(manifests), 1)
        private_manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
        self.assertEqual(private_manifest["name"], "clip.mp4")
        self.assertEqual(private_manifest["mime"], "video/mp4")
        self.assertEqual(private_manifest["size_bytes"], 5)
        self.assertFalse(private_manifest["text_available"])
        self.assertIsNone(private_manifest["text_preview"])
        stored_files = [path for path in self.upload_root.glob("*/*") if path.is_file()]
        self.assertEqual(len(stored_files), 1)
        self.assertEqual(stored_files[0].read_bytes(), b"12345")

    # Test oversize uploads are rejected before being stored.
    def test_upload_api_reports_oversized_files(self):
        upload = SimpleUploadedFile("too-big.mp4", b"12345", content_type="video/mp4")

        with patch.object(upload_storage, "MAX_UPLOAD_BYTES", 4):
            response = self.client.post(reverse("uploads_api"), {"files": [upload]})

        self.assertEqual(response.status_code, 200)
        public_file = response.json()["files"][0]
        self.assertEqual(public_file["status"], "error")
        self.assertIn("File is too large", public_file["error"])
        self.assertEqual(list(self.manifest_root.glob("*/*.manifest.json")), [])

    # Test media content endpoint supports suffix ranges needed by MP4 metadata reads.
    def test_uploaded_file_content_supports_suffix_byte_range(self):
        upload = SimpleUploadedFile("clip.mp4", b"0123456789", content_type="video/mp4")
        upload_response = self.client.post(reverse("uploads_api"), {"files": [upload]})
        content_url = upload_response.json()["files"][0]["content_url"]
        stored_file = next(path for path in self.upload_root.glob("*/*") if path.is_file())

        with patch("Apps.UI.views._resolve_uploaded_file_content_path", return_value=stored_file):
            response = self.client.get(content_url, HTTP_RANGE="bytes=-4")

        self.assertEqual(response.status_code, 206)
        self.assertEqual(response["Content-Range"], "bytes 6-9/10")
        self.assertEqual(b"".join(response.streaming_content), b"6789")

    # Test open-ended media ranges are chunked so playback can start without reading the rest of a large file.
    def test_uploaded_file_content_chunks_open_ended_range(self):
        upload = SimpleUploadedFile("clip.mp4", b"0123456789", content_type="video/mp4")
        upload_response = self.client.post(reverse("uploads_api"), {"files": [upload]})
        content_url = upload_response.json()["files"][0]["content_url"]
        stored_file = next(path for path in self.upload_root.glob("*/*") if path.is_file())

        with (
            patch("Apps.UI.views.MEDIA_RANGE_CHUNK_BYTES", 4),
            patch("Apps.UI.views._resolve_uploaded_file_content_path", return_value=stored_file),
        ):
            response = self.client.get(content_url, HTTP_RANGE="bytes=2-")

        self.assertEqual(response.status_code, 206)
        self.assertEqual(response["Content-Range"], "bytes 2-5/10")
        self.assertEqual(b"".join(response.streaming_content), b"2345")

    # Test model-shared files use the same range streaming path as uploaded files.
    def test_shared_file_download_supports_byte_range(self):
        with tempfile.NamedTemporaryFile(delete=False) as handle:
            handle.write(b"abcdefghij")
            temp_path = Path(handle.name)
        try:
            with patch("Apps.UI.views._resolve_shared_file_path", return_value=temp_path):
                response = self.client.get(
                    reverse("shared_file_download_api"),
                    {"path": str(temp_path), "preview": "1"},
                    HTTP_RANGE="bytes=-3",
                )

            self.assertEqual(response.status_code, 206)
            self.assertEqual(response["Content-Range"], "bytes 7-9/10")
            self.assertEqual(b"".join(response.streaming_content), b"hij")
        finally:
            temp_path.unlink(missing_ok=True)

    # Test shared-file downloads are limited to the sandbox workspace.
    def test_shared_file_download_rejects_project_absolute_path(self):
        response = self.client.get(
            reverse("shared_file_download_api"),
            {"path": str(Path(__file__).resolve())},
        )

        self.assertEqual(response.status_code, 404)

    # Test container-style sandbox paths are still mapped to the host sandbox.
    def test_shared_file_download_allows_container_sandbox_path(self):
        sandbox_file = Path("Tools/mcp-sandbox/_sandbox/User/shared-test.txt")
        sandbox_file.parent.mkdir(parents=True, exist_ok=True)
        sandbox_file.write_text("shared ok", encoding="utf-8")
        try:
            response = self.client.get(
                reverse("shared_file_download_api"),
                {"path": "/workspace/_sandbox/User/shared-test.txt"},
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(b"".join(response.streaming_content), b"shared ok")
        finally:
            sandbox_file.unlink(missing_ok=True)

    # Test empty upload requests fail before returning a card payload.
    def test_upload_api_requires_files(self):
        response = self.client.post(reverse("uploads_api"), {})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "No files uploaded")

    # Test model-facing upload manifests do not expose sandbox paths unless selected.
    def test_model_upload_manifest_respects_sandbox_selection(self):
        upload = SimpleUploadedFile("notes.txt", b"Hello from upload", content_type="text/plain")
        response = self.client.post(reverse("uploads_api"), {"files": [upload], "scope": "chat-1"})
        file_id = response.json()["files"][0]["file_id"]

        without_sandbox = _load_model_upload_manifests([file_id], sandbox_enabled=False)[0]
        with_sandbox = _load_model_upload_manifests([file_id], sandbox_enabled=True)[0]

        self.assertIsNone(without_sandbox["sandbox_path"])
        self.assertNotIn("sandbox", without_sandbox["recommended_tools"])
        self.assertTrue(with_sandbox["sandbox_path"].startswith(f"/workspace/_sandbox/User/{with_sandbox['sha256']}/"))
        self.assertIn("sandbox", with_sandbox["recommended_tools"])

    # Test the private prompt block only includes sandbox path when allowed.
    def test_uploaded_file_prompt_block_hides_disabled_sandbox_path(self):
        manifest = {
            "file_id": "file-1",
            "name": "notes.txt",
            "mime": "text/plain",
            "size_bytes": 5,
            "sandbox_path": None,
            "text_preview": "Hello",
            "archive_tree": None,
            "table_preview": None,
        }

        block = _build_uploaded_file_prompt_block(manifest)

        self.assertIn("[Uploaded file: notes.txt]", block)
        self.assertIn("Text preview:\nHello", block)
        self.assertNotIn("Sandbox path:", block)

    def test_uploaded_archive_prompt_block_says_preview_not_extracted(self):
        manifest = {
            "file_id": "file-zip",
            "name": "bundle.zip",
            "mime": "application/zip",
            "size_bytes": 123,
            "sandbox_path": "/workspace/_sandbox/User/chat/file__bundle.zip",
            "text_preview": None,
            "archive_tree": ["bundle/", "bundle/manage.py"],
            "table_preview": None,
        }

        block = _build_uploaded_file_prompt_block(manifest)

        self.assertIn("Archive preview", block)
        self.assertIn("has not been extracted", block)
        self.assertNotIn("Archive tree:", block)
        self.assertIn("- bundle/manage.py", block)

    # Test upload file ids can be read from current and future request shapes.
    def test_uploaded_file_ids_are_normalized_from_request_shapes(self):
        self.assertEqual(
            _normalize_uploaded_file_ids({
                "uploaded_file_ids": ["a", "b", "a"],
                "attachments": [{"file_id": "c"}, {"name": "legacy.txt"}],
            }),
            ["a", "b", "c"],
        )

    # Test upload ids can be persisted on a user message for regenerate/history replay.
    def test_uploaded_file_context_entry_round_trips_file_ids(self):
        entry = _build_uploaded_file_context_entry(["file-1", "file-2", "file-1"])
        message = Message(role="user", content="read this", llm_transcript=[entry])

        self.assertEqual(entry["type"], "uploaded_file_context")
        self.assertEqual(_extract_uploaded_file_ids_from_message(message), ["file-1", "file-2"])

    # Test sandbox state is derived only from resolved tool servers.
    def test_selected_tools_include_sandbox_only_when_resolved(self):
        self.assertTrue(_selected_tools_include_sandbox([{"id": "sandbox"}]))
        self.assertFalse(_selected_tools_include_sandbox([{"id": "other"}]))
        self.assertFalse(_selected_tools_include_sandbox([]))


# Upload routing tests.

# Cover file type classification used by public upload cards.
class UploadRoutingTests(SimpleTestCase):
    """Cover upload display routing for common and unusual files."""

    # Test routing common file types to stable card labels.
    def test_display_kind_routes_known_file_types(self):
        cases = [
            ("photo.png", "image/png", ("image", "Image")),
            ("notes.md", "text/markdown", ("text", "Text file")),
            ("script.py", "text/x-python", ("code", "Code file")),
            ("report.pdf", "application/pdf", ("document", "PDF document")),
            ("sheet.csv", "text/csv", ("table", "CSV table")),
            ("bundle.zip", "application/zip", ("archive", "ZIP archive")),
            ("voice_note.mp3", "audio/mpeg", ("audio", "Audio")),
            ("demo_clip.mp4", "video/mp4", ("video", "Video")),
            ("slides.pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation", ("presentation", "PowerPoint presentation")),
        ]

        for name, mime, expected in cases:
            with self.subTest(name=name):
                self.assertEqual(display_kind_for_upload(name, mime), expected)

    # Test unknown extensions fall back to generic File, not rejection.
    def test_display_kind_routes_unknown_extension_to_file(self):
        self.assertEqual(display_kind_for_upload("mystery.abc", "application/x-abc"), ("file", "File"))
        self.assertEqual(display_kind_for_upload("no-extension", "application/octet-stream"), ("file", "File"))


# View and runtime mapping tests.

# Verify that the main page uses the configured engine and local server helpers.
class MainViewTests(ToolRegistryTestMixin, TestCase):
    """Verify that the main page uses the configured engine and local server helpers."""

    # Test main view includes runtime settings and local servers.
    @patch("Apps.UI.views._get_active_engine", return_value="ollama-service")
    def test_main_view_includes_runtime_settings_and_local_servers(self, _mock_engine):
        self.write_server(
            'time_suite',
            '''
            MCP_SERVER = {"id": "time_suite", "name": "Time Suite", "description": "Time helpers"}
            TOOLS = [{"id": "time_now", "name": "Current Time", "parameters": {"type": "object", "properties": {}}}]
            def call_tool(tool_id, arguments, context=None):
                return "ok"
            ''',
        )

        response = self.client.get(reverse("main"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["models"], [])
        self.assertEqual(response.context["llm_engine"], "ollama-service")
        self.assertIn("runtime_settings", response.context)
        self.assertEqual(
            response.context["available_tool_servers"],
            [{
                "id": "time_suite",
                "name": "Time Suite",
                "description": "Time helpers",
                "tool_count": 1,
                "tools": [{"id": "time_now", "name": "Current Time", "description": ""}],
            }],
        )
        self.assertContains(response, 'id="group-load"')


# Ensure Ollama-only thinking parameters are normalized before request dispatch.
class OllamaOptionMappingTests(SimpleTestCase):
    """Ensure Ollama-only thinking parameters are normalized before request dispatch."""

    # Test prepare chat kwargs maps think level into think.
    def test_prepare_chat_kwargs_maps_think_level_into_think(self):
        payload = _prepare_chat_kwargs(
            {
                "stream": True,
                "think": True,
                "think_level": "high",
                "options": {"temperature": 0.7},
            }
        )

        self.assertNotIn("think_level", payload)
        self.assertEqual(payload["think"], "high")
        self.assertEqual(payload["options"]["temperature"], 0.7)

    # Test prepare chat kwargs drops runtime options unsupported by current Ollama.
    def test_prepare_chat_kwargs_drops_runtime_options_unsupported_by_current_ollama(self):
        payload = _prepare_chat_kwargs(
            {
                "options": {
                    "temperature": 0.7,
                    "num_ctx": 32768,
                    "mirostat": 2,
                    "numa": False,
                    "tfs_z": 1.0,
                }
            }
        )

        self.assertEqual(payload["options"]["temperature"], 0.7)
        self.assertEqual(payload["options"]["num_ctx"], 32768)
        self.assertNotIn("mirostat", payload["options"])
        self.assertNotIn("numa", payload["options"])
        self.assertNotIn("tfs_z", payload["options"])

    # Test prepare chat kwargs ignores LM Studio only internal keys.
    def test_prepare_chat_kwargs_ignores_lms_only_internal_keys(self):
        payload = _prepare_chat_kwargs(
            {
                "stream": True,
                "think": True,
                "think_param_name": "ext.virtualModel.customField.qwen.enableThinking",
                "think_level_param_name": "ext.virtualModel.customField.openai.reasoningEffort",
                "load_config": {"contextLength": 32768},
                "sync_operation_defaults": {"ext.virtualModel.customField.qwen.enableThinking": False},
                "options": {"temperature": 0.7},
            }
        )

        self.assertNotIn("think_param_name", payload)
        self.assertNotIn("think_level_param_name", payload)
        self.assertNotIn("load_config", payload)
        self.assertNotIn("sync_operation_defaults", payload)
        self.assertEqual(payload["think"], True)
        self.assertEqual(payload["options"]["temperature"], 0.7)

    # Test prepare runtime passes requested engine to managed service.
    @patch("API.ollama._get_ollama_service_module")
    def test_prepare_runtime_passes_requested_engine_to_managed_service(self, mock_get_service):
        mock_service = Mock()
        mock_get_service.return_value = mock_service

        prepare_ollama_runtime("ollama-service")

        mock_service.start_ollama.assert_called_once_with(engine="ollama-service")


# Ensure Ollama tool support follows Ollama model metadata.
class OllamaModelInfoTests(SimpleTestCase):
    """Ensure Ollama model metadata maps tool support without model-name hardcoding."""

    # Test an explicit Ollama capabilities list without tools disables tool support.
    def test_ollama_capabilities_without_tools_disable_tool_support(self):
        payload = _extract_ollama_model_info({
            "capabilities": ["completion"],
            "template": "{{ if .Tools }}tools{{ end }}{{ if .ToolCalls }}calls{{ end }}",
        })

        self.assertFalse(payload["supports_tool_calling"])

    # Test Ollama's tools capability enables support without template markers.
    def test_ollama_tools_capability_enables_tool_support(self):
        payload = _extract_ollama_model_info({
            "capabilities": ["completion", "tools"],
            "template": "{{ if .Messages }}{{ end }}",
        })

        self.assertTrue(payload["supports_tool_calling"])

    # Test old/custom Ollama responses can still infer tools from the template.
    def test_ollama_tool_template_fallback_when_capabilities_are_missing(self):
        payload = _extract_ollama_model_info({
            "template": "{{ if .Messages }}{{ end }}",
        })

        self.assertFalse(payload["supports_tool_calling"])

        payload = _extract_ollama_model_info({
            "template": "{{ if .Tools }}tools{{ end }}{{ if .ToolCalls }}calls{{ end }}",
        })

        self.assertTrue(payload["supports_tool_calling"])


# Ensure generic runtime options are safely mapped for OpenAI-compatible APIs.
class OpenAiOptionMappingTests(SimpleTestCase):
    """Ensure generic runtime options are safely mapped for OpenAI-compatible APIs."""

    # Test maps supported options and keeps custom values in extra body.
    def test_maps_supported_options_and_keeps_custom_values_in_extra_body(self):
        payload = _build_openai_request_options(
            {
                "temperature": 0.7,
                "num_predict": 256,
                "num_ctx": 4096,
                "top_k": 40,
            },
            think_level="high",
        )

        self.assertEqual(payload["temperature"], 0.7)
        self.assertEqual(payload["max_tokens"], 256)
        self.assertEqual(payload["reasoning_effort"], "high")
        self.assertEqual(payload["extra_body"]["num_ctx"], 4096)
        self.assertEqual(payload["extra_body"]["top_k"], 40)

    # Test OpenAI client uses placeholder API key when not configured.
    @patch("openai.OpenAI")
    @patch("API.openai.settings.get_engine_url", return_value="http://127.0.0.1:1234/v1")
    @patch("API.openai.settings.get_openai_api_key", return_value="")
    def test_openai_client_uses_placeholder_api_key_when_not_configured(
        self,
        _mock_api_key,
        _mock_engine_url,
        mock_openai_client,
    ):
        from API.openai import _get_client

        mock_openai_client.return_value = Mock()
        _get_client()

        self.assertEqual(mock_openai_client.call_args.kwargs["api_key"], "not-needed")


# Cover extended OpenAI-compatible capability parsing and reasoning output.
class OpenAiAdapterTests(SimpleTestCase):
    """Cover extended OpenAI-compatible capability parsing and reasoning output."""

    # Test get model settings reads OpenAI capabilities and reasoning.
    @patch("API.openai._get_client")
    def test_get_model_settings_reads_openai_capabilities_and_reasoning(self, mock_get_client):
        client = Mock()
        client.models.list.return_value = Mock(
            data=[
                {
                    "id": "gpt-test",
                    "capabilities": {"tools": True, "vision": True},
                    "reasoning": {
                        "enabled": True,
                        "effort": {
                            "default": "high",
                            "options": ["low", "medium", "high"],
                        },
                    },
                    "context_length": 65536,
                }
            ]
        )
        client.models.retrieve.return_value = {
            "id": "gpt-test",
            "supported_parameters": {
                "tools": {"type": "array"},
                "tool_choice": {"type": "string"},
                "reasoning_effort": {"enum": ["low", "medium", "high"]},
            },
            "defaults": {"temperature": 0.2},
        }
        mock_get_client.return_value = client

        payload = get_openai_model_settings("gpt-test")

        self.assertTrue(payload["supports_tool_calling"])
        self.assertTrue(payload["supports_vision"])
        self.assertTrue(payload["supports_thinking"])
        self.assertTrue(payload["supports_think_toggle"])
        self.assertTrue(payload["supports_think_level"])
        self.assertTrue(payload["supports_files"])
        self.assertEqual(payload["think_level_param_name"], "reasoning_effort")
        self.assertEqual(payload["defaults"]["temperature"], 0.2)
        self.assertEqual(payload["defaults"]["reasoning_effort"], "high")
        self.assertEqual(payload["think_level_options"], ["low", "medium", "high"])
        self.assertEqual(payload["context_length"], 65536)
        self.assertIn("tool_choice", payload["supported_parameters"])

    # Test get model settings reads direct feature flags and scalar supported parameters.
    @patch("API.openai._get_client")
    def test_get_model_settings_reads_direct_feature_flags_and_scalar_supported_parameters(self, mock_get_client):
        client = Mock()
        client.models.list.return_value = Mock(
            data=[
                {
                    "id": "gpt-test",
                    "vision": True,
                    "tool_calling": True,
                    "reasoning": True,
                    "input_modalities": ["text", "image"],
                }
            ]
        )
        client.models.retrieve.return_value = {
            "id": "gpt-test",
            "supported_parameters": ["temperature", "tools", "tool_choice", "reasoning_effort"],
        }
        mock_get_client.return_value = client

        payload = get_openai_model_settings("gpt-test")

        self.assertTrue(payload["supports_tool_calling"])
        self.assertTrue(payload["supports_vision"])
        self.assertTrue(payload["supports_thinking"])
        self.assertTrue(payload["supports_think_level"])
        self.assertFalse(payload["supports_think_toggle"])
        self.assertIn("reasoning_effort", payload["supported_parameters"])

    # Test generate stream parses reasoning and visible content.
    @patch("API.openai._get_client")
    def test_generate_stream_parses_reasoning_and_visible_content(self, mock_get_client):
        client = Mock()
        client.chat.completions.create.return_value = [
            {"choices": [{"delta": {"reasoning_content": "Plan first."}}]},
            {"choices": [{"delta": {"content": "Final answer"}}]},
        ]
        mock_get_client.return_value = client

        chunks = list(
            generate_openai(
                "gpt-test",
                [{"role": "user", "content": "Hi"}],
                stream=True,
            )
        )

        self.assertEqual(chunks[0]["message"]["thinking"], "Plan first.")
        self.assertEqual(chunks[0]["message"]["content"], "")
        self.assertEqual(chunks[1]["message"]["content"], "Final answer")

    # Test generate stream does not duplicate plain content into thinking.
    @patch("API.openai._get_client")
    def test_generate_stream_does_not_duplicate_plain_content_into_thinking(self, mock_get_client):
        client = Mock()
        client.chat.completions.create.return_value = [
            {"choices": [{"delta": {"content": "Hello"}}]},
            {"choices": [{"delta": {"content": " world"}}]},
        ]
        mock_get_client.return_value = client

        chunks = list(
            generate_openai(
                "gpt-test",
                [{"role": "user", "content": "Hi"}],
                stream=True,
            )
        )

        self.assertEqual([chunk["message"]["content"] for chunk in chunks], ["Hello", " world"])
        self.assertTrue(all("thinking" not in chunk["message"] for chunk in chunks))

    # Test get model settings reads companion metadata without generation.
    @patch("API.openai._get_companion_model_payload")
    @patch("API.openai._get_client")
    def test_get_model_settings_reads_companion_metadata_without_generation(
        self,
        mock_get_client,
        mock_get_companion_payload,
    ):
        client = Mock()
        client.models.list.return_value = Mock(data=[{"id": "gpt-probe", "object": "model", "owned_by": "org"}])
        client.models.retrieve.return_value = {"id": "gpt-probe", "object": "model", "owned_by": "org"}
        mock_get_companion_payload.return_value = {
            "key": "gpt-probe",
            "type": "llm",
            "max_context_length": 131072,
            "capabilities": {
                "vision": True,
                "trained_for_tool_use": True,
                "reasoning": {
                    "allowed_options": ["off", "on"],
                    "default": "on",
                },
            },
        }
        mock_get_client.return_value = client

        payload = get_openai_model_settings("gpt-probe")

        self.assertTrue(payload["supports_tool_calling"])
        self.assertTrue(payload["supports_thinking"])
        self.assertTrue(payload["supports_vision"])
        self.assertFalse(payload["supports_think_level"])
        self.assertTrue(payload["supports_think_toggle"])
        self.assertEqual(payload["think_level_options"], [])
        self.assertEqual(payload["defaults"]["think"], True)
        self.assertIn("tool_choice", payload["supported_parameters"])
        self.assertIn("tools", payload["supported_parameters"])
        client.chat.completions.create.assert_not_called()


# Cover Google GenAI filtering, capability learning, and thinking fallback.
class GoogleGenAiAdapterTests(SimpleTestCase):
    """Cover Google GenAI filtering, capability learning, and thinking fallback."""

    # Set up the test fixture.
    def setUp(self):
        super().setUp()
        google_genai_api._reset_runtime_caches()

    # Tear down the test fixture.
    def tearDown(self):
        google_genai_api._reset_runtime_caches()
        super().tearDown()

    # Test Gemini function-call replay preserves thought signatures.
    def test_function_call_history_preserves_thought_signature(self):
        raw_part = {
            "thought_signature": b"signature-bytes",
            "function_call": {
                "name": "web_search",
                "args": {"query": "latest ai news"},
            },
        }

        history_part = google_genai_api._build_google_history_part(raw_part, include_text=False)
        replay_parts = google_genai_api._normalize_google_request_parts([history_part])

        self.assertEqual(history_part["function_call"]["name"], "web_search")
        self.assertIn("thought_signature", history_part)
        self.assertEqual(replay_parts[0]["thought_signature"], b"signature-bytes")
        self.assertEqual(replay_parts[0]["function_call"]["name"], "web_search")
        self.assertEqual(replay_parts[0]["function_call"]["args"], {"query": "latest ai news"})

    # Test fallback function-call reconstruction is skipped for preserved Gemini parts.
    def test_preserved_function_call_parts_avoid_unsigned_duplicate(self):
        preserved_parts = [
            {
                "thought_signature": "c2lnbmF0dXJlLWJ5dGVz",
                "function_call": {
                    "name": "web_search",
                    "args": {"query": "latest ai news"},
                },
            }
        ]

        self.assertTrue(google_genai_api._history_parts_have_function_call(preserved_parts))
        content = google_genai_api._assistant_message_to_content(
            {
                "role": "assistant",
                "content": "",
                "google_parts": preserved_parts,
                "tool_calls": [
                    {
                        "id": "call_1_web_search",
                        "type": "function",
                        "function": {
                            "name": "web_search",
                            "arguments": json.dumps({"query": "latest ai news"}),
                        },
                    }
                ],
            }
        )

        function_call_parts = [
            part for part in content["parts"] if isinstance(part.get("function_call"), dict)
        ]
        self.assertEqual(len(function_call_parts), 1)
        self.assertEqual(function_call_parts[0]["thought_signature"], b"signature-bytes")

    # Test legacy unsigned Gemini tool-call transcript is not replayed.
    def test_unsigned_legacy_function_call_history_is_skipped(self):
        _system_instruction, contents = google_genai_api._build_google_contents(
            [
                {"role": "user", "content": "Search this"},
                {
                    "role": "assistant",
                    "content": "",
                    "google_parts": [
                        {
                            "function_call": {
                                "name": "web_search",
                                "args": {"query": "latest ai news"},
                            }
                        }
                    ],
                    "tool_calls": [
                        {
                            "type": "function",
                            "function": {
                                "name": "web_search",
                                "arguments": json.dumps({"query": "latest ai news"}),
                            },
                        }
                    ],
                },
                {"role": "tool", "name": "web_search", "content": "{\"result\": \"ok\"}"},
                {"role": "user", "content": "Continue"},
            ]
        )

        self.assertEqual(contents[0], {"role": "user", "parts": [{"text": "Search this"}]})
        self.assertEqual(contents[-1], {"role": "user", "parts": [{"text": "Continue"}]})
        self.assertFalse(
            any(
                isinstance(part.get("function_call"), dict)
                for content in contents
                for part in content.get("parts", [])
            )
        )
        self.assertFalse(
            any(
                isinstance(part.get("function_response"), dict)
                for content in contents
                for part in content.get("parts", [])
            )
        )

    # Test get models filters out non generate content models.
    @patch("API.google_genai._close_client")
    @patch("API.google_genai._get_client")
    def test_get_models_filters_out_non_generate_content_models(self, mock_get_client, _mock_close_client):
        client = Mock()
        payloads = [
            {"name": "models/gemini-2.5-flash", "supported_actions": ["generateContent"]},
            {"name": "models/veo-3.0-generate-001", "supported_actions": ["generateVideos"]},
        ]
        client.models.list.side_effect = lambda config=None: payloads
        mock_get_client.return_value = client

        models = get_google_genai_models()

        self.assertEqual([entry["model"] for entry in models], ["gemini-2.5-flash"])
        client.models.generate_content.assert_not_called()

    # Test get models hides zero quota models for current key after runtime learning.
    @patch("API.google_genai._close_client")
    @patch("API.google_genai._get_client")
    @patch("API.google_genai.settings.get_engine_url", return_value="https://generativelanguage.googleapis.com")
    @patch("API.google_genai.settings.get_google_genai_api_key", return_value="key-a")
    def test_get_models_hides_zero_quota_models_for_current_key_after_runtime_learning(
        self,
        _mock_api_key,
        _mock_engine_url,
        mock_get_client,
        _mock_close_client,
    ):
        client = Mock()
        payloads = [{"name": "models/gemini-3.1-pro", "supported_actions": ["generateContent"]}]
        client.models.list.side_effect = lambda config=None: payloads
        client.models.generate_content.side_effect = FakeGoogleError(
            429,
            "RESOURCE_EXHAUSTED",
            "Quota exceeded for model gemini-3.1-pro. limit: 0.",
            details=[{"violations": [{"quotaDimensions": {"model": "gemini-3.1-pro"}}]}],
        )
        mock_get_client.return_value = client

        with self.assertRaises(FakeGoogleError):
            list(
                generate_google_genai(
                    "gemini-3.1-pro",
                    [{"role": "user", "content": "Hi"}],
                    stream=False,
                )
            )

        self.assertEqual(get_google_genai_models(), [])
        self.assertEqual(client.models.generate_content.call_count, 1)

    # Test get models keeps temporarily rate limited models visible.
    @patch("API.google_genai._close_client")
    @patch("API.google_genai._get_client")
    @patch("API.google_genai.settings.get_engine_url", return_value="https://generativelanguage.googleapis.com")
    @patch("API.google_genai.settings.get_google_genai_api_key", return_value="key-a")
    def test_get_models_keeps_temporarily_rate_limited_models_visible(
        self,
        _mock_api_key,
        _mock_engine_url,
        mock_get_client,
        _mock_close_client,
    ):
        client = Mock()
        payloads = [{"name": "models/gemini-2.5-pro", "supported_actions": ["generateContent"]}]
        client.models.list.side_effect = lambda config=None: payloads
        client.models.generate_content.side_effect = FakeGoogleError(
            429,
            "RESOURCE_EXHAUSTED",
            "Quota exceeded for model gemini-2.5-pro. limit: 8. Please retry later.",
            details=[{"violations": [{"quotaDimensions": {"model": "gemini-2.5-pro"}}]}],
        )
        mock_get_client.return_value = client

        with self.assertRaises(FakeGoogleError):
            list(
                generate_google_genai(
                    "gemini-2.5-pro",
                    [{"role": "user", "content": "Hi"}],
                    stream=False,
                )
            )

        models = get_google_genai_models()
        cached_models = get_google_genai_models()

        self.assertEqual([entry["model"] for entry in models], ["gemini-2.5-pro"])
        self.assertEqual([entry["model"] for entry in cached_models], ["gemini-2.5-pro"])
        self.assertEqual(client.models.generate_content.call_count, 1)

    # Test get model settings returns toggle when thinking level is unsupported.
    @patch("API.google_genai._close_client")
    @patch("API.google_genai._get_client")
    def test_get_model_settings_returns_toggle_when_thinking_level_is_unsupported(
        self,
        mock_get_client,
        _mock_close_client,
    ):
        client = Mock()
        client.models.get.return_value = {
            "name": "models/gemini-2.5-flash",
            "supported_actions": ["generateContent"],
            "thinking": True,
            "tools": True,
            "output_token_limit": 65536,
        }

        # Simulate the Gemini generation endpoint.
        def generate_content(*, model, contents, config):
            thinking_config = config.get("thinking_config", {})
            if thinking_config.get("thinking_level") is not None:
                raise FakeGoogleError(
                    400,
                    "INVALID_ARGUMENT",
                    "Thinking level is not supported for this model.",
                )
            return {"candidates": [{"content": {"parts": [{"text": "OK"}]}}]}

        client.models.generate_content.side_effect = generate_content
        mock_get_client.return_value = client

        payload = get_google_genai_model_settings("gemini-2.5-flash")

        self.assertTrue(payload["supports_thinking"])
        self.assertTrue(payload["supports_think_toggle"])
        self.assertFalse(payload["supports_think_level"])
        self.assertEqual(payload["think_level_options"], [])
        self.assertTrue(payload["defaults"]["include_thoughts"])
        self.assertEqual(payload["defaults"]["max_output_tokens"], 8192)
        self.assertEqual(payload["runtime_limits"]["output_token_limit"], 65536)
        self.assertNotIn("thinking_level", payload["supported_parameters"])

    # Test generate retries without thinking level when model rejects it.
    @patch("API.google_genai._close_client")
    @patch("API.google_genai._get_client")
    def test_generate_retries_without_thinking_level_when_model_rejects_it(
        self,
        mock_get_client,
        _mock_close_client,
    ):
        client = Mock()
        captured_configs: list[dict[str, object]] = []

        # Simulate a retry flow that rejects thinking_level once.
        def generate_content(*, model, contents, config):
            captured_configs.append(config)
            thinking_config = dict(config.get("thinking_config", {}) or {})
            if thinking_config.get("thinking_level") is not None:
                raise FakeGoogleError(
                    400,
                    "INVALID_ARGUMENT",
                    "Thinking level is not supported for this model.",
                )
            return {"candidates": [{"content": {"parts": [{"text": "Final answer"}]}}]}

        client.models.generate_content.side_effect = generate_content
        mock_get_client.return_value = client

        chunks = list(
            generate_google_genai(
                "gemini-2.5-flash",
                [{"role": "user", "content": "Hi"}],
                stream=False,
                think_level="high",
            )
        )

        self.assertTrue(any(chunk.get("message", {}).get("content") == "Final answer" for chunk in chunks))
        self.assertEqual(len(captured_configs), 2)
        self.assertEqual(
            captured_configs[0]["thinking_config"]["thinking_level"],
            "HIGH",
        )
        self.assertNotIn("thinking_level", captured_configs[1]["thinking_config"])
        cached_capabilities = google_genai_api._get_cached_model_capabilities("gemini-2.5-flash")
        self.assertFalse(cached_capabilities["supports_think_level"])

    # Test learned availability is scoped to API key.
    @patch("API.google_genai._close_client")
    @patch("API.google_genai._get_client")
    @patch("API.google_genai.settings.get_engine_url", return_value="https://generativelanguage.googleapis.com")
    def test_learned_availability_is_scoped_to_api_key(
        self,
        _mock_engine_url,
        mock_get_client,
        _mock_close_client,
    ):
        client_blocked = Mock()
        client_allowed = Mock()
        payloads = [{"name": "models/gemini-3.1-pro", "supported_actions": ["generateContent"]}]
        client_blocked.models.list.side_effect = lambda config=None: payloads
        client_allowed.models.list.side_effect = lambda config=None: payloads
        client_blocked.models.generate_content.side_effect = FakeGoogleError(
            429,
            "RESOURCE_EXHAUSTED",
            "Quota exceeded for model gemini-3.1-pro. limit: 0.",
            details=[{"violations": [{"quotaDimensions": {"model": "gemini-3.1-pro"}}]}],
        )
        client_allowed.models.generate_content.return_value = {
            "candidates": [{"content": {"parts": [{"text": "OK"}]}}]
        }
        key_state = {"value": "key-a"}

        # Get API key.
        def get_api_key():
            return key_state["value"]

        # Get client for key.
        def get_client_for_key():
            return client_blocked if key_state["value"] == "key-a" else client_allowed

        mock_get_client.side_effect = get_client_for_key

        with patch("API.google_genai.settings.get_google_genai_api_key", side_effect=get_api_key):
            with self.assertRaises(FakeGoogleError):
                list(
                    generate_google_genai(
                        "gemini-3.1-pro",
                        [{"role": "user", "content": "Hi"}],
                        stream=False,
                    )
                )
            self.assertEqual(get_google_genai_models(), [])
            key_state["value"] = "key-b"
            models = get_google_genai_models()

        self.assertEqual([entry["model"] for entry in models], ["gemini-3.1-pro"])
        self.assertEqual(client_blocked.models.generate_content.call_count, 1)
        client_allowed.models.generate_content.assert_not_called()


# Cover generic engine registry behavior for optional capabilities.
class EngineRegistryTests(SimpleTestCase):
    """Cover generic engine registry behavior for optional capabilities."""

    # Test reload model raises for engines without reload support.
    def test_reload_model_raises_for_engines_without_reload_support(self):
        with self.assertRaises(NotImplementedError):
            llm_api.reload_model("openai", "gpt-oss")

    # Test get models prepares runtime before listing.
    @patch("API.llm_api.prepare_runtime")
    @patch("API.llm_api._get_engine_module")
    def test_get_models_prepares_runtime_before_listing(self, mock_get_engine_module, mock_prepare_runtime):
        mock_module = Mock()
        mock_module.get_models.return_value = ["llama3"]
        mock_get_engine_module.return_value = mock_module

        self.assertEqual(llm_api.get_models("ollama-service"), ["llama3"])
        mock_prepare_runtime.assert_called_once_with("ollama-service")

    # Test get model settings prepares runtime before loading metadata.
    @patch("API.llm_api.prepare_runtime")
    @patch("API.llm_api._get_engine_module")
    def test_get_model_settings_prepares_runtime_before_loading_metadata(
        self,
        mock_get_engine_module,
        mock_prepare_runtime,
    ):
        mock_module = Mock()
        mock_module.get_model_settings.return_value = {"model": "llama3"}
        mock_get_engine_module.return_value = mock_module

        self.assertEqual(llm_api.get_model_settings("ollama-service", "llama3"), {"model": "llama3"})
        mock_prepare_runtime.assert_called_once_with("ollama-service")


# Cover settings-driven engine availability.
class EngineAvailabilitySettingsTests(SimpleTestCase):
    """Cover enabled engine filtering and active engine resolution."""

    # Clear the settings cache between mocked settings snapshots.
    def tearDown(self):
        project_settings._invalidate_settings_cache()

    # Run one assertion block against an isolated settings payload.
    def _with_settings_payload(self, payload, assertion):
        with patch.dict(os.environ, {}, clear=True):
            with patch("Settings.settings._load_settings_from_disk", return_value=payload):
                with patch("Settings.settings._get_settings_mtime_ns", return_value=1):
                    project_settings._invalidate_settings_cache()
                    assertion()

    # Test supported engines only includes enabled engine flags.
    def test_supported_engines_only_includes_enabled_flags(self):
        def assertion():
            self.assertEqual(
                project_settings.get_supported_engines(),
                [
                    {"id": "ollama-service", "label": "Ollama"},
                    {"id": "openai", "label": "OpenAI-Compatible"},
                ],
            )

        self._with_settings_payload(
            {
                "llm-engine": "ollama-service",
                "ollama-service": True,
                "lms": False,
                "openai": True,
                "google-genai": False,
            },
            assertion,
        )

    # Test disabled active engine falls back to the first enabled engine.
    def test_active_engine_falls_back_when_configured_engine_is_disabled(self):
        def assertion():
            self.assertEqual(project_settings.get_llm_engine(), "ollama-service")

        self._with_settings_payload(
            {
                "llm-engine": "openai",
                "ollama-service": True,
                "lms": False,
                "openai": False,
                "google-genai": False,
            },
            assertion,
        )


# Cover LM Studio metadata normalization and capability fallback.
class LmsAdapterTests(SimpleTestCase):
    """Cover LM Studio metadata normalization and capability fallback."""

    # Test serialize model info reads nested info wrapper.
    def test_serialize_model_info_reads_nested_info_wrapper(self):
        # Define info.
        class Info:
            model_key = "qwen3"
            display_name = "Qwen 3"
            vision = True
            trained_for_tool_use = True
            max_context_length = 65536

        # Define wrapper.
        class Wrapper:
            info = Info()

        payload = _serialize_model_info(Wrapper())

        self.assertEqual(payload["modelKey"], "qwen3")
        self.assertTrue(payload["vision"])
        self.assertTrue(payload["trainedForToolUse"])
        self.assertEqual(payload["maxContextLength"], 65536)

    # Test get model settings uses loaded model info when direct lookup fails.
    @patch("API.lms._close_client")
    @patch("API.lms._get_client")
    def test_get_model_settings_uses_loaded_model_info_when_direct_lookup_fails(
        self,
        mock_get_client,
        _mock_close_client,
    ):
        # Define loaded info.
        class LoadedInfo:
            model_key = "qwen3"
            vision = True
            trained_for_tool_use = True
            max_context_length = 65536

        # Define loaded model.
        class LoadedModel:
            info = LoadedInfo()

        client = Mock()
        client.llm.get_model_info.side_effect = RuntimeError("not loaded")
        client.list_loaded_models.return_value = [LoadedModel()]
        mock_get_client.return_value = (Mock(), client)

        payload = get_lms_model_settings("qwen3")

        self.assertTrue(payload["supports_vision"])
        self.assertTrue(payload["supports_tool_calling"])
        self.assertEqual(payload["context_length"], 65536)

    # Test prepare OpenAI prediction options keeps LM Studio custom values in extra body.
    def test_prepare_openai_prediction_options_keeps_lms_custom_values_in_extra_body(self):
        payload = _prepare_openai_prediction_options(
            {
                "temperature": 0.2,
                "contextOverflowPolicy": "truncateMiddle",
                "draftModel": "qwen/qwen3.5-0.5b",
            },
            think_level="high",
        )

        self.assertEqual(payload["temperature"], 0.2)
        self.assertEqual(payload["reasoning_effort"], "high")
        self.assertNotIn("contextOverflowPolicy", payload)
        self.assertEqual(payload["extra_body"]["contextOverflowPolicy"], "truncateMiddle")
        self.assertEqual(payload["extra_body"]["draftModel"], "qwen/qwen3.5-0.5b")
        self.assertIn("reasoningParsing", payload["extra_body"])


# Keep user-visible LM output clean and actionable.
class ViewFormattingTests(SimpleTestCase):
    """Keep user-visible LM output clean and actionable."""

    # Test strip LLM control tokens removes service markers.
    def test_strip_llm_control_tokens_removes_service_markers(self):
        self.assertEqual(
            _strip_llm_control_tokens("<|start|>assistant<|channel|>final<|message|>Hello"),
            "Hello",
        )

    # Test format runtime error hides LM Studio model load verbosity.
    def test_format_runtime_error_hides_lms_model_load_verbosity(self):
        message = _format_runtime_error(
            "lms",
            RuntimeError(
                "Model get/load error: V Cache Quantization requires flash attention to be enabled."
            ),
        )

        self.assertIn("Flash Attention", message)
        self.assertNotIn("Model get/load error", message)

    # Test chat titles are compact and useful for attachment-only threads.
    def test_build_chat_title_handles_long_and_attachment_only_messages(self):
        self.assertEqual(_build_chat_title("Short title", False), "Short title")
        self.assertEqual(_build_chat_title("x" * 31, False), f"{'x' * 30}...")
        self.assertEqual(_build_chat_title("", True), "Attachment chat")
        self.assertEqual(_build_chat_title("", False), "New Chat")

    # Test active tool slugs support both current JSON and legacy string shapes.
    def test_parse_active_tool_slugs_supports_json_and_legacy_values(self):
        self.assertEqual(_parse_active_tool_slugs('["time_suite", "", "browser"]'), ["time_suite", "browser"])
        self.assertEqual(_parse_active_tool_slugs("time_suite"), ["time_suite"])
        self.assertEqual(_parse_active_tool_slugs(""), [])

    # Test shared files keep their UI render payload after tool result splitting.
    def test_shared_file_tool_result_keeps_ui_metadata(self):
        payload = {
            "kind": "shared_file",
            "path": "/workspace/_sandbox/wave_graph.svg",
            "filename": "wave_graph.svg",
            "mime_type": "image/svg+xml",
            "size_bytes": 123,
            "render": {
                "type": "image",
                "mime_type": "image/svg+xml",
                "preview": {"kind": "base64", "data": "abc"},
            },
        }

        model_text, extras = tool_registry.split_tool_result_payload(payload)

        self.assertEqual(model_text, "Shared file ready for download: wave_graph.svg")
        self.assertEqual(extras["structured_content"]["kind"], "shared_file")
        self.assertEqual(extras["structured_content"]["file"]["render"]["type"], "image")
        self.assertEqual(extras["tool_ui"]["kind"], "shared_file")

    # Test repeated tool aliases preserve all shared files in activity segments.
    def test_build_activity_segments_keeps_repeated_share_file_aliases(self):
        class _MessageStub:
            llm_transcript = [
                {
                    "role": "tool",
                    "alias": "sandbox__share_file__0",
                    "tool_id": "share_file",
                    "tool_display_name": "Share File",
                    "arguments": {"path": "a.txt", "filename": "a.txt"},
                    "content": "Shared file ready for download: a.txt",
                    "structured_content": {
                        "kind": "shared_file",
                        "file": {"kind": "shared_file", "path": "a.txt", "filename": "a.txt"},
                    },
                    "tool_ui": {
                        "kind": "shared_file",
                        "status": "done",
                        "file": {"kind": "shared_file", "path": "a.txt", "filename": "a.txt"},
                    },
                },
                {
                    "role": "tool",
                    "alias": "sandbox__share_file__0",
                    "tool_id": "share_file",
                    "tool_display_name": "Share File",
                    "arguments": {"path": "b.txt", "filename": "b.txt"},
                    "content": "Shared file ready for download: b.txt",
                    "structured_content": {
                        "kind": "shared_file",
                        "file": {"kind": "shared_file", "path": "b.txt", "filename": "b.txt"},
                    },
                    "tool_ui": {
                        "kind": "shared_file",
                        "status": "done",
                        "file": {"kind": "shared_file", "path": "b.txt", "filename": "b.txt"},
                    },
                },
            ]

        segments = _build_activity_segments(_MessageStub())
        files = [
            (segment.get("structuredContent") or {}).get("file", {}).get("filename")
            for segment in segments
            if segment.get("type") == "tool"
        ]
        self.assertEqual(files, ["a.txt", "b.txt"])


class BrowserPortalApiTests(SimpleTestCase):
    """Verify wait-for-user portal timing and finish signaling."""

    def test_active_browser_portal_state_uses_deadline_when_available(self):
        with patch("Apps.UI.views.time.time", return_value=1000.0):
            self.assertFalse(
                _is_active_browser_portal_state(
                    {
                        "status": "waiting",
                        "updated_at": 999.0,
                        "timeout_seconds": 45,
                        "deadline_at": 980.0,
                    }
                )
            )
            self.assertTrue(
                _is_active_browser_portal_state(
                    {
                        "status": "waiting",
                        "updated_at": 500.0,
                        "timeout_seconds": 45,
                        "deadline_at": 1005.0,
                    }
                )
            )

    def test_finish_event_response_reports_done_and_queues_event(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "browser_portal"
            events_dir = root / "events"
            events_dir.mkdir(parents=True)
            (root / "state.json").write_text(
                json.dumps(
                    {
                        "ok": True,
                        "status": "waiting",
                        "session_id": "session-a",
                        "updated_at": 999.0,
                        "timeout_seconds": 45,
                        "deadline_at": 1045.0,
                    }
                ),
                encoding="utf-8",
            )

            with patch("Apps.UI.views._browser_portal_roots", return_value=[root]):
                with patch("Apps.UI.views.time.time", return_value=1000.0):
                    response = Client().post(
                        reverse("browser_portal_event_api"),
                        data=json.dumps({"type": "finish", "session_id": "session-a"}),
                        content_type="application/json",
                    )

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertTrue(payload["queued"])
            self.assertEqual(payload["status"], "done")
            queued_events = list(events_dir.glob("event_*.json"))
            self.assertEqual(len(queued_events), 1)
            queued_payload = json.loads(queued_events[0].read_text(encoding="utf-8"))
            self.assertEqual(queued_payload["type"], "finish")
            self.assertEqual(queued_payload["session_id"], "session-a")


# Model metadata cache tests.
# Ensure cached payloads are safe to reuse between requests.
class ModelInfoCacheTests(TestCase):
    """Verify model-info caching behavior."""

    # Clear metadata caches around each test.
    def setUp(self):
        super().setUp()
        _clear_model_metadata_caches()

    # Restore metadata cache state after the test.
    def tearDown(self):
        _clear_model_metadata_caches()
        super().tearDown()

    # Test cached model info is returned as a defensive copy.
    @patch("Apps.UI.views.llm_api.get_model_settings")
    def test_model_info_payload_cache_returns_detached_copies(self, mock_get_model_settings):
        mock_get_model_settings.return_value = {
            "context_length": 32768,
            "defaults": {"temperature": 0.7},
            "supports_tool_calling": False,
        }

        first_payload = _build_model_info_payload("openai", "gpt-test")
        first_payload["defaults"]["temperature"] = 99
        second_payload = _build_model_info_payload("openai", "gpt-test")

        self.assertEqual(second_payload["defaults"]["temperature"], 0.7)
        self.assertEqual(second_payload["context_length"], 32768)
        mock_get_model_settings.assert_called_once_with("openai", "gpt-test")


class ContextCompressionBudgetTests(SimpleTestCase):
    """Cover context compression threshold math."""

    def test_history_budget_uses_same_model_token_estimator_as_usage_ui(self):
        payload = {"context_length": 10000}

        self.assertEqual(
            _resolve_history_char_budget(payload, active_engine="lms", active_model="qwen3"),
            20000,
        )
        self.assertEqual(
            _resolve_history_char_budget(payload, active_engine="ollama-service", active_model="llama3"),
            27000,
        )

    def test_history_budget_blends_observed_token_ratio(self):
        payload = {"context_length": 10000}

        self.assertEqual(
            _resolve_history_char_budget(
                payload,
                active_engine="lms",
                active_model="qwen3",
                observed_chars_per_token=1.6,
            ),
            17400,
        )


# Exercise chat API basics without calling a real model backend.
class ChatApiTests(ToolRegistryTestMixin, TestCase):
    """Exercise chat API basics without calling a real model backend."""

    # Set up the test fixture.
    def setUp(self):
        super().setUp()
        self.client = Client()

    # Test chat API rejects invalid JSON before touching runtime services.
    def test_chat_api_rejects_invalid_json_body(self):
        response = self.client.post(
            reverse("chat_api"),
            data="{",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Invalid JSON format")

    # Test chat API requires a model name.
    def test_chat_api_rejects_missing_model(self):
        response = self.client.post(
            reverse("chat_api"),
            data='{"message":"Hello"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Missing model parameter")

    # Test chat API creates new chat and streams response.
    @patch("Apps.UI.views.llm_api.prepare_runtime")
    @patch("Apps.UI.views.llm_api.generate")
    @patch("Apps.UI.views._get_active_engine", return_value="ollama-service")
    def test_chat_api_creates_new_chat_and_streams_response(
        self,
        _mock_engine,
        mock_generate,
        mock_prepare_runtime,
    ):
        mock_generate.return_value = [{"message": {"content": "Hi there"}}]

        response = self.client.post(
            reverse("chat_api"),
            data='{"message":"Hello","model":"llama3"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.has_header("X-Chat-ID"))
        self.assertEqual(b"".join(response.streaming_content), b"Hi there")
        self.assertEqual(Chat.objects.count(), 1)
        self.assertEqual(Chat.objects.first().messages.count(), 2)
        mock_prepare_runtime.assert_called_once_with("ollama-service")

    # Test chat API supports an attachment-only prompt.
    @patch("Apps.UI.views.llm_api.prepare_runtime")
    @patch("Apps.UI.views.llm_api.generate")
    @patch("Apps.UI.views._get_active_engine", return_value="lms")
    def test_chat_api_creates_attachment_only_thread(
        self,
        _mock_engine,
        mock_generate,
        _mock_prepare_runtime,
    ):
        mock_generate.return_value = [{"message": {"content": "Done"}}]

        response = self.client.post(
            reverse("chat_api"),
            data=json.dumps(
                {
                    "model": "qwen",
                    "attachments": [
                        {
                            "name": "note.txt",
                            "mime_type": "text/plain",
                            "data": "SGVsbG8=",
                        },
                    ],
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        b"".join(response.streaming_content)
        chat = Chat.objects.get()
        self.assertEqual(chat.title, "Attachment chat")
        self.assertEqual(chat.messages.filter(role="user").get().content, "")

    # Test chat API passes selected tool server to Ollama.
    @patch(
        "Apps.UI.views.llm_api.get_model_settings",
        return_value={
            "capabilities": ["tools"],
            "template": "{{ if .Tools }}{{ end }}{{ if .ToolCalls }}{{ end }}",
        },
    )
    @patch("Apps.UI.views.llm_api.prepare_runtime")
    @patch("Apps.UI.views.llm_api.generate")
    @patch("Apps.UI.views._get_active_engine", return_value="ollama-service")
    def test_chat_api_passes_selected_tool_server_to_ollama(
        self,
        _mock_engine,
        mock_generate,
        _mock_prepare_runtime,
        _mock_model_settings,
    ):
        self.write_server(
            'time_suite',
            '''
            MCP_SERVER = {"id": "time_suite", "name": "Time Suite"}
            TOOLS = [
                {"id": "time_now", "name": "Current Time", "parameters": {"type": "object", "properties": {}}},
                {"id": "timezone_name", "name": "Timezone Name", "parameters": {"type": "object", "properties": {}}},
            ]
            def call_tool(tool_id, arguments, context=None):
                return "ok"
            ''',
        )
        mock_generate.return_value = [{"message": {"content": "Done"}}]

        response = self.client.post(
            reverse("chat_api"),
            data='{"message":"Hello","model":"llama3.1","tool_server_id":"time_suite"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(b''.join(response.streaming_content), b'Done')
        self.assertEqual(mock_generate.call_args.kwargs["tool_server_ids"], ["time_suite"])
        self.assertEqual(mock_generate.call_args.kwargs["tool_context"]["engine"], "ollama-service")
        self.assertEqual(Chat.objects.first().active_tool_slug, '["time_suite"]')

    # Test chat API rejects unknown tool server.
    @patch("Apps.UI.views._get_active_engine", return_value="ollama-service")
    def test_chat_api_rejects_unknown_tool_server(self, _mock_engine):
        response = self.client.post(
            reverse("chat_api"),
            data='{"message":"Hello","model":"llama3","tool_server_id":"missing"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Unknown or unsupported tool server", response.json()["error"])

    # Test chat API stream includes server and tool markers.
    @patch("Apps.UI.views.llm_api.prepare_runtime")
    @patch("Apps.UI.views.llm_api.generate")
    @patch("Apps.UI.views._get_active_engine", return_value="ollama-service")
    def test_chat_api_stream_includes_server_and_tool_markers(
        self,
        _mock_engine,
        mock_generate,
        _mock_prepare_runtime,
    ):
        mock_generate.return_value = iter([
            {"message": {"thinking": "Searching..."}},
            {"tool_event": {"server_id": "time_suite", "server_name": "Time Suite", "tool_id": "time_now", "tool_name": "Current Time", "alias": "time_suite__time_now", "arguments": {"label": "now"}}},
            {"message": {"content": "Done"}},
        ])

        response = self.client.post(
            reverse("chat_api"),
            data='{"message":"Hello","model":"llama3"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        body = b''.join(response.streaming_content).decode('utf-8')
        self.assertIn('<think>\nSearching...', body)
        self.assertIn('\"server_id\": \"time_suite\"', body)
        self.assertIn('\"tool_id\": \"time_now\"', body)
        self.assertIn('Done', body)

    # Test chat API keeps reasoning-only output instead of deleting it on abort.
    @patch("Apps.UI.views.llm_api.prepare_runtime")
    @patch("Apps.UI.views.llm_api.generate")
    @patch("Apps.UI.views._get_active_engine", return_value="ollama-service")
    def test_chat_api_persists_reasoning_only_response(
        self,
        _mock_engine,
        mock_generate,
        _mock_prepare_runtime,
    ):
        mock_generate.return_value = iter([
            {"message": {"thinking": "Planning the answer."}},
        ])

        response = self.client.post(
            reverse("chat_api"),
            data='{"message":"Hello","model":"llama3"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        body = b"".join(response.streaming_content).decode("utf-8")
        self.assertIn("<think>\nPlanning the answer.", body)
        assistant_message = Message.objects.filter(role="assistant").latest("created_at")
        self.assertEqual(assistant_message.content, "")
        self.assertEqual(assistant_message.llm_transcript[0]["role"], "assistant")
        self.assertEqual(assistant_message.llm_transcript[0]["thinking"], "Planning the answer.")

    # Test streamed reasoning is buffered before the full response completes.
    @patch("Apps.UI.views.llm_api.prepare_runtime")
    @patch("Apps.UI.views.llm_api.generate")
    @patch("Apps.UI.views._get_active_engine", return_value="ollama-service")
    def test_chat_api_buffers_reasoning_while_streaming(
        self,
        _mock_engine,
        mock_generate,
        _mock_prepare_runtime,
    ):
        mock_generate.return_value = iter([
            {"message": {"thinking": "Live reasoning buffer."}},
            {"message": {"content": "Done"}},
        ])

        response = self.client.post(
            reverse("chat_api"),
            data='{"message":"Hello","model":"llama3"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        stream = iter(response.streaming_content)
        first_chunk = next(stream).decode("utf-8")
        self.assertEqual(first_chunk, "<think>\n")
        assistant_message = Message.objects.filter(role="assistant").latest("created_at")
        self.assertEqual(assistant_message.llm_transcript[0]["thinking"], "Live reasoning buffer.")
        b"".join(stream)

    # Test streaming compression can run during reasoning without waiting for the next send.
    @patch("Apps.UI.views._build_manual_compression_event")
    @patch("Apps.UI.views.llm_api.prepare_runtime")
    @patch("Apps.UI.views.llm_api.generate")
    def test_stream_chat_response_auto_compresses_at_reasoning_safe_point(
        self,
        mock_generate,
        _mock_prepare_runtime,
        mock_build_compression_event,
    ):
        chat = Chat.objects.create(title="Chat")
        assistant_message = Message.objects.create(chat=chat, role="assistant", content="", llm_transcript=[])
        compression_event = {
            "role": "tool",
            "alias": "context_compression_summary",
            "name": "context_compression_summary",
            "tool_name": "context_compression_summary",
            "tool_id": "context_compression_summary",
            "content": "Compressed history",
            "arguments": {},
        }
        mock_build_compression_event.return_value = compression_event
        mock_generate.return_value = iter([
            {"message": {"thinking": "Live reasoning buffer."}},
            {"message": {"content": "Done"}},
        ])

        body = "".join(_stream_chat_response(
            chat,
            "ollama-service",
            {
                "engine": "ollama-service",
                "model_name": "llama3",
                "messages": [],
                "stream": True,
            },
            assistant_message,
            "generation-1",
            model_info_payload={},
            system_prompt="System",
        ))

        self.assertIn("<context_compression>", body)
        self.assertIn('"auto_trigger": "reasoning"', body)
        self.assertIn('"restart_generation": true', body)
        kwargs = mock_build_compression_event.call_args.kwargs
        self.assertEqual(kwargs["draft_text"], "Live reasoning buffer.")
        self.assertEqual(kwargs["exclude_message_ids"], {assistant_message.id})
        self.assertFalse(kwargs["summarize_with_model_enabled"])
        compression_message = (
            Message.objects
            .filter(role="assistant", llm_transcript__0__alias="context_compression_summary")
            .latest("created_at")
        )
        self.assertNotEqual(compression_message.id, assistant_message.id)
        self.assertEqual(compression_message.llm_transcript[0]["arguments"]["auto_trigger"], "reasoning")
        self.assertTrue(compression_message.llm_transcript[0]["arguments"]["restart_generation"])

    # Test streaming compression also checks the threshold when a tool call starts.
    @patch("Apps.UI.views._build_manual_compression_event")
    @patch("Apps.UI.views.llm_api.prepare_runtime")
    @patch("Apps.UI.views.llm_api.generate")
    def test_stream_chat_response_auto_compresses_at_tool_call_safe_point(
        self,
        mock_generate,
        _mock_prepare_runtime,
        mock_build_compression_event,
    ):
        chat = Chat.objects.create(title="Chat")
        assistant_message = Message.objects.create(chat=chat, role="assistant", content="", llm_transcript=[])
        compression_event = {
            "role": "tool",
            "alias": "context_compression_summary",
            "name": "context_compression_summary",
            "tool_name": "context_compression_summary",
            "tool_id": "context_compression_summary",
            "content": "Compressed history",
            "arguments": {},
        }
        mock_build_compression_event.return_value = compression_event
        mock_generate.return_value = iter([
            {
                "tool_event": {
                    "server_id": "time_suite",
                    "server_name": "Time Suite",
                    "tool_id": "time_now",
                    "tool_name": "Current Time",
                    "alias": "time_suite__time_now",
                    "arguments": {"label": "now"},
                },
            },
            {"message": {"content": "Done"}},
        ])

        body = "".join(_stream_chat_response(
            chat,
            "ollama-service",
            {
                "engine": "ollama-service",
                "model_name": "llama3",
                "messages": [],
                "stream": True,
            },
            assistant_message,
            "generation-1",
            model_info_payload={},
            system_prompt="System",
        ))

        self.assertIn("<context_compression>", body)
        self.assertIn('"auto_trigger": "tool_call"', body)
        kwargs = mock_build_compression_event.call_args.kwargs
        self.assertIn("time_now", kwargs["draft_text"])
        compression_message = (
            Message.objects
            .filter(role="assistant", llm_transcript__0__alias="context_compression_summary")
            .latest("created_at")
        )
        self.assertEqual(compression_message.llm_transcript[0]["arguments"]["auto_trigger"], "tool_call")

    # Test the server-side history builder uses the current prompt for the 80% trigger.
    @patch("Apps.UI.views.build_structured_history_summary")
    def test_build_chat_history_compresses_when_current_prompt_crosses_threshold(
        self,
        mock_build_summary,
    ):
        mock_build_summary.return_value = (
            "Compressed prior history",
            {"summary_version": 1, "work_summary": "Compressed prior history"},
        )
        chat = Chat.objects.create(title="Chat")
        Message.objects.create(chat=chat, role="user", content="Older user context")
        Message.objects.create(chat=chat, role="assistant", content="Older assistant context")
        current_user = Message.objects.create(chat=chat, role="user", content="x" * 9800)

        llm_messages, compression_event = _build_chat_history(
            chat,
            current_user,
            current_user.content,
            "system",
            "lms",
            "qwen3",
            {"context_length": 4096, "defaults": {"num_ctx": 4096}},
        )

        self.assertIsNotNone(compression_event)
        self.assertEqual(compression_event["arguments"]["context_window_tokens"], 4096)
        self.assertGreaterEqual(
            compression_event["arguments"]["used_history_chars"],
            int(compression_event["arguments"]["history_budget_chars"] * 0.8),
        )
        self.assertEqual(llm_messages[0]["role"], "system")
        self.assertIn("Compressed prior history", llm_messages[1]["content"])
        self.assertEqual(llm_messages[-1]["content"], current_user.content)

    # Test chat API persists generic attachments and builds LM Studio messages.
    @patch("Apps.UI.views.llm_api.prepare_runtime")
    @patch("Apps.UI.views.llm_api.generate")
    @patch("Apps.UI.views._get_active_engine", return_value="lms")
    def test_chat_api_persists_generic_attachments_and_builds_lms_messages(
        self,
        _mock_engine,
        mock_generate,
        _mock_prepare_runtime,
    ):
        mock_generate.return_value = [{"message": {"content": "Done"}}]

        response = self.client.post(
            reverse("chat_api"),
            data=json.dumps(
                {
                    "message": "Hello",
                    "model": "qwen",
                    "attachments": [
                        {
                            "kind": "image",
                            "name": "photo.png",
                            "mime_type": "image/png",
                            "data": "iVBORw0KGgo=",
                        },
                        {
                            "kind": "file",
                            "name": "note.txt",
                            "mime_type": "text/plain",
                            "data": "SGVsbG8gZnJvbSBmaWxl",
                        },
                    ],
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        b"".join(response.streaming_content)
        self.assertEqual(MessageAttachment.objects.count(), 2)

        outbound_messages = mock_generate.call_args.kwargs["messages"]
        current_user_message = outbound_messages[-1]
        self.assertEqual(current_user_message["role"], "user")
        self.assertEqual(len(current_user_message["images"]), 1)
        self.assertIn("[Attached file: note.txt]", current_user_message["content"])
        self.assertIn("Hello from file", current_user_message["content"])

    # Test chat API rejects tool server when LM Studio model lacks tool support.
    @patch("Apps.Data.lms_presets.lms_api.get_model_settings", return_value={"supports_tool_calling": False, "supports_files": True})
    @patch("Apps.UI.views.llm_api.get_model_settings", return_value={"supports_tool_calling": False, "supports_files": True})
    @patch("Apps.UI.views._get_active_engine", return_value="lms")
    def test_chat_api_rejects_tool_server_when_lms_model_lacks_tool_support(
        self,
        _mock_engine,
        _mock_model_settings,
        _mock_preset_model_settings,
    ):
        self.write_server(
            'time_suite',
            '''
            MCP_SERVER = {"id": "time_suite", "name": "Time Suite"}
            TOOLS = [{"id": "time_now", "name": "Current Time", "parameters": {"type": "object", "properties": {}}}]
            def call_tool(tool_id, arguments, context=None):
                return "ok"
            ''',
        )

        response = self.client.post(
            reverse("chat_api"),
            data='{"message":"Hello","model":"qwen","tool_server_id":"time_suite"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("does not support tool calling", response.json()["error"])

    # Test chat API rejects tool server when Ollama capabilities omit tools.
    @patch(
        "Apps.UI.views.llm_api.get_model_settings",
        return_value={
            "capabilities": ["completion"],
            "template": "{{ if .Tools }}tools{{ end }}{{ if .ToolCalls }}calls{{ end }}",
        },
    )
    @patch("Apps.UI.views._get_active_engine", return_value="ollama-service")
    def test_chat_api_rejects_tool_server_when_ollama_capabilities_omit_tools(
        self,
        _mock_engine,
        _mock_model_settings,
    ):
        self.write_server(
            'time_suite',
            '''
            MCP_SERVER = {"id": "time_suite", "name": "Time Suite"}
            TOOLS = [{"id": "time_now", "name": "Current Time", "parameters": {"type": "object", "properties": {}}}]
            def supports(engine=None, model_name=None):
                return engine == "ollama-service"
            def call_tool(tool_id, arguments, context=None):
                return "ok"
            ''',
        )

        response = self.client.post(
            reverse("chat_api"),
            data='{"message":"Hello","model":"model-without-tools","tool_server_id":"time_suite"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("does not support tool calling", response.json()["error"])

    # Test chat API rejects tool server when OpenAI model lacks tool support.
    @patch("Apps.UI.views.llm_api.get_model_settings", return_value={"supports_tool_calling": False, "supports_files": True})
    @patch("Apps.UI.views._get_active_engine", return_value="openai")
    def test_chat_api_rejects_tool_server_when_openai_model_lacks_tool_support(
        self,
        _mock_engine,
        _mock_model_settings,
    ):
        self.write_server(
            'time_suite',
            '''
            MCP_SERVER = {"id": "time_suite", "name": "Time Suite"}
            TOOLS = [{"id": "time_now", "name": "Current Time", "parameters": {"type": "object", "properties": {}}}]
            def supports(engine=None, model_name=None):
                return engine == "openai"
            def call_tool(tool_id, arguments, context=None):
                return "ok"
            ''',
        )

        response = self.client.post(
            reverse("chat_api"),
            data='{"message":"Hello","model":"gpt-test","tool_server_id":"time_suite"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("does not support tool calling", response.json()["error"])


    # Test chat API saves visible content and machine transcript.
    @patch("Apps.UI.views.llm_api.prepare_runtime")
    @patch("Apps.UI.views.llm_api.generate")
    @patch("Apps.UI.views._get_active_engine", return_value="ollama-service")
    def test_chat_api_saves_visible_content_and_machine_transcript(
        self,
        _mock_engine,
        mock_generate,
        _mock_prepare_runtime,
    ):
        mock_generate.return_value = iter([
            {"message": {"thinking": "Plan first."}},
            {"transcript_message": {"role": "assistant", "content": "", "thinking": "Plan first.", "tool_calls": [{"function": {"name": "time_suite__time_now", "arguments": {"label": "now"}}}]}},
            {"tool_event": {"server_id": "time_suite", "server_name": "Time Suite", "tool_id": "time_now", "tool_name": "Current Time", "alias": "time_suite__time_now", "arguments": {"label": "now"}}},
            {"tool_result": {"role": "tool", "name": "time_suite__time_now", "tool_name": "time_suite__time_now", "content": '{"ok": true}', "server_id": "time_suite", "server_name": "Time Suite", "tool_id": "time_now", "tool_display_name": "Current Time", "arguments": {"label": "now"}}},
            {"message": {"content": "Done"}},
            {"transcript_message": {"role": "assistant", "content": "Done"}},
        ])

        response = self.client.post(
            reverse("chat_api"),
            data='{"message":"Hello","model":"llama3"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        b"".join(response.streaming_content)
        assistant_message = Message.objects.filter(role="assistant").latest("created_at")
        self.assertEqual(assistant_message.content, "Done")
        self.assertEqual(len(assistant_message.llm_transcript), 3)
        self.assertEqual(assistant_message.llm_transcript[1]["role"], "tool")
        self.assertEqual(assistant_message.llm_transcript[1]["server_name"], "Time Suite")

    # Test chat API uses stored transcript for follow up messages.
    @patch("Apps.UI.views.llm_api.prepare_runtime")
    @patch("Apps.UI.views.llm_api.generate")
    @patch("Apps.UI.views._get_active_engine", return_value="ollama-service")
    def test_chat_api_uses_stored_transcript_for_follow_up_messages(
        self,
        _mock_engine,
        mock_generate,
        _mock_prepare_runtime,
    ):
        chat = Chat.objects.create(title="Chat")
        Message.objects.create(chat=chat, role="user", content="Hello")
        Message.objects.create(
            chat=chat,
            role="assistant",
            content="Visible answer",
            llm_transcript=[
                {"role": "assistant", "content": "", "thinking": "Plan", "tool_calls": [{"function": {"name": "time_suite__time_now", "arguments": {"label": "now"}}}]},
                {"role": "tool", "name": "time_suite__time_now", "tool_name": "time_suite__time_now", "content": '{"ok": true}'},
                {"role": "assistant", "content": "Visible answer"},
            ],
        )
        mock_generate.return_value = [{"message": {"content": "Next"}}]

        response = self.client.post(
            reverse("chat_api"),
            data=f'{{"chat_id":"{chat.id}","message":"Follow up","model":"llama3"}}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        b"".join(response.streaming_content)
        history_messages = mock_generate.call_args.kwargs["messages"]
        self.assertEqual([item["role"] for item in history_messages[:4]], ["user", "assistant", "tool", "assistant"])
        self.assertEqual(history_messages[1]["thinking"], "Plan")
        self.assertEqual(history_messages[2]["name"], "time_suite__time_now")
        self.assertEqual(history_messages[-1]["content"], "Follow up")

    # Test chat API strips legacy UI markup when transcript is missing.
    @patch("Apps.UI.views.llm_api.prepare_runtime")
    @patch("Apps.UI.views.llm_api.generate")
    @patch("Apps.UI.views._get_active_engine", return_value="ollama-service")
    def test_chat_api_strips_legacy_ui_markup_when_transcript_is_missing(
        self,
        _mock_engine,
        mock_generate,
        _mock_prepare_runtime,
    ):
        chat = Chat.objects.create(title="Chat")
        Message.objects.create(chat=chat, role="user", content="Hello")
        Message.objects.create(
            chat=chat,
            role="assistant",
            content='<think>\nPlan\n</think>\n<tool_call>{"alias":"time_suite__time_now"}</tool_call>Visible answer',
        )
        mock_generate.return_value = [{"message": {"content": "Next"}}]

        response = self.client.post(
            reverse("chat_api"),
            data=f'{{"chat_id":"{chat.id}","message":"Follow up","model":"llama3"}}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        b"".join(response.streaming_content)
        history_messages = mock_generate.call_args.kwargs["messages"]
        self.assertEqual(history_messages[1], {"role": "assistant", "content": "Visible answer"})

    # Test chat API strips service control tokens from visible output.
    @patch("Apps.UI.views.llm_api.prepare_runtime")
    @patch("Apps.UI.views.llm_api.generate")
    @patch("Apps.UI.views._get_active_engine", return_value="lms")
    def test_chat_api_strips_service_control_tokens_from_visible_output(
        self,
        _mock_engine,
        mock_generate,
        _mock_prepare_runtime,
    ):
        mock_generate.return_value = [
            {"message": {"content": "<|start|>assistant<|channel|>final<|message|>Hello"}},
        ]

        response = self.client.post(
            reverse("chat_api"),
            data='{"message":"Hi","model":"qwen3"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content).decode("utf-8"), "Hello")
        assistant_message = Message.objects.filter(role="assistant").latest("created_at")
        self.assertEqual(assistant_message.content, "Hello")


# Verify runtime settings and dynamic model selection endpoints.
class RuntimeSettingsApiTests(TestCase):
    """Verify runtime settings and dynamic model selection endpoints."""

    RUNTIME_SETTINGS_WITH_API_KEY = {
        "llm-engine": "openai",
        "lms_url": "127.0.0.1:1234",
        "openai_url": "openrouter.ai/api/v1",
        "has_openai_api_key": True,
        "engine_urls": {"openai": "https://openrouter.ai/api/v1"},
    }

    # Run runtime settings API tests against a temporary settings file.
    @contextmanager
    def isolated_settings_payload(self, payload):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings_file = Path(temp_dir) / "settings.json"
            with patch("Settings.settings.SETTINGS_FILE", settings_file):
                with patch("Settings.settings._apply_environment_overrides", side_effect=lambda data: data):
                    with patch("Settings.settings._sync_module_manifest_setting"):
                        project_settings._invalidate_settings_cache()
                        project_settings.save_settings(payload)
                        try:
                            yield
                        finally:
                            project_settings._invalidate_settings_cache()

    # Test get runtime settings payload.
    def test_get_runtime_settings_payload(self):
        response = self.client.get(reverse("runtime_settings_api"))

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("models", response.json())

    # Test runtime settings rejects invalid JSON.
    def test_runtime_settings_rejects_invalid_json(self):
        response = self.client.post(
            reverse("runtime_settings_api"),
            data="{",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Invalid JSON format")

    # Test post runtime settings updates engine.
    @patch("Apps.UI.views.llm_api.handle_engine_transition")
    def test_post_runtime_settings_updates_engine(self, mock_transition):
        with self.isolated_settings_payload(
            {
                "llm-engine": "ollama-service",
                "ollama-service": True,
                "lms": False,
                "openai": True,
                "google-genai": False,
                "openai_url": "127.0.0.1:8000/v1",
            }
        ):
            response = self.client.post(
                reverse("runtime_settings_api"),
                data='{"llm-engine":"openai","openai_url":"http://127.0.0.1:1234/v1"}',
                content_type="application/json",
            )

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["llm-engine"], "openai")
            self.assertEqual(payload["openai_url"], "127.0.0.1:1234/v1")
            self.assertNotIn("models", payload)
            self.assertFalse(payload["has_openai_api_key"])
            mock_transition.assert_called_once()
            self.assertEqual(mock_transition.call_args.args[1], "openai")

    # Test disabled engine selection falls back to an enabled engine.
    @patch("Apps.UI.views.llm_api.handle_engine_transition")
    def test_post_runtime_settings_ignores_disabled_engine(self, mock_transition):
        with self.isolated_settings_payload(
            {
                "llm-engine": "ollama-service",
                "ollama-service": True,
                "lms": False,
                "openai": False,
                "google-genai": False,
            }
        ):
            response = self.client.post(
                reverse("runtime_settings_api"),
                data='{"llm-engine":"openai"}',
                content_type="application/json",
            )

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["llm-engine"], "ollama-service")
            self.assertEqual(payload["engine_options"], [{"id": "ollama-service", "label": "Ollama"}])
            mock_transition.assert_called_once_with("ollama-service", "ollama-service")

    # Test models API returns engine specific models.
    @patch("Apps.UI.views._load_models_for_engine", return_value=["llama3"])
    def test_models_api_returns_engine_specific_models(self, mock_models):
        response = self.client.get(reverse("models_api"), {"engine": "lms"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"engine": "lms", "models": ["llama3"]})
        mock_models.assert_called_once_with("lms")

    # Test model info API requires a model query parameter.
    def test_model_info_api_requires_model_parameter(self):
        response = self.client.get(reverse("model_info_api"), {"engine": "lms"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Model parameter is required")

    # Test model info API maps unsupported engines to 501.
    @patch("Apps.UI.views._build_model_info_payload", side_effect=NotImplementedError("Not supported"))
    def test_model_info_api_returns_501_for_unimplemented_engines(self, mock_build_payload):
        response = self.client.get(reverse("model_info_api"), {"engine": "custom", "model": "model"})

        self.assertEqual(response.status_code, 501)
        self.assertEqual(response.json()["error"], "Not supported")
        mock_build_payload.assert_called_once()

    # Test inference info API returns a compact engine-independent payload.
    @patch("Apps.UI.views._build_model_info_payload")
    def test_inference_info_api_returns_unified_payload(self, mock_build_payload):
        mock_build_payload.return_value = {
            "context_length": 131072,
            "defaults": {"num_ctx": 65536, "num_predict": 8192, "temperature": 0.7},
            "supports_thinking": True,
            "supports_think_toggle": True,
            "supports_think_level": True,
            "supports_vision": False,
            "supports_tool_calling": True,
            "supports_files": False,
            "capabilities": ["tools", "thinking"],
            "runtime_limits": {"output_token_limit": 32768},
            "available_tool_servers": [{"id": "time_suite", "name": "Time Suite"}],
        }

        response = self.client.get(
            reverse("inference_info_api"),
            {"engine": "ollama-service", "model": "llama3"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["engine"], "ollama-service")
        self.assertEqual(payload["engine_label"], "Ollama")
        self.assertEqual(payload["model"], "llama3")
        self.assertEqual(payload["context_window"], 65536)
        self.assertEqual(payload["model_context_limit"], 131072)
        self.assertEqual(payload["max_output_tokens"], 8192)
        self.assertEqual(payload["output_token_limit"], 32768)
        self.assertTrue(payload["capabilities"]["supports_tool_calling"])
        self.assertEqual(payload["tool_servers"][0]["id"], "time_suite")
        self.assertEqual(payload["source"]["model"], "request")
        mock_build_payload.assert_called_once_with("ollama-service", "llama3")

    # Test inference info can use the latest model selected through model info.
    @patch("Apps.UI.views._build_model_info_payload")
    def test_inference_info_api_uses_runtime_selected_model(self, mock_build_payload):
        mock_build_payload.return_value = {
            "context_length": 32768,
            "defaults": {"max_completion_tokens": 2048},
            "supports_tool_calling": False,
        }

        selected = self.client.get(reverse("model_info_api"), {"engine": "openai", "model": "gpt-test"})
        self.assertEqual(selected.status_code, 200)

        response = self.client.get(reverse("inference_info_api"), {"engine": "openai"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["engine"], "openai")
        self.assertEqual(payload["model"], "gpt-test")
        self.assertEqual(payload["context_window"], 32768)
        self.assertEqual(payload["max_output_tokens"], 2048)
        self.assertEqual(payload["source"]["model"], "runtime_selection")

    # Test runtime settings payload does not expose API key.
    @patch("Apps.UI.views.settings.get_supported_engines", return_value=[])
    @patch("Apps.UI.views.settings.get_runtime_engine_settings", return_value=RUNTIME_SETTINGS_WITH_API_KEY)
    def test_runtime_settings_payload_does_not_expose_api_key(
        self,
        _mock_runtime_settings,
        _mock_engines,
    ):
        response = self.client.get(reverse("runtime_settings_api"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["has_openai_api_key"])
        self.assertNotIn("openai_api_key", payload)


# Cover local tool-server listing and chat persistence endpoints.
class ToolApiTests(ToolRegistryTestMixin, TestCase):
    """Cover local tool-server listing and chat persistence endpoints."""

    # Test tools API returns discovered servers.
    def test_tools_api_returns_discovered_servers(self):
        self.write_server(
            'time_suite',
            '''
            MCP_SERVER = {"id": "time_suite", "name": "Time Suite", "description": "Time helpers"}
            TOOLS = [{"id": "time_now", "name": "Current Time", "parameters": {"type": "object", "properties": {}}}]
            def call_tool(tool_id, arguments, context=None):
                return "ok"
            ''',
        )

        response = self.client.get(reverse("tools_api"), {"engine": "ollama-service", "model": "llama3"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["tool_servers"],
            [{
                "id": "time_suite",
                "name": "Time Suite",
                "description": "Time helpers",
                "tool_count": 1,
                "tools": [{"id": "time_now", "name": "Current Time", "description": ""}],
            }],
        )

    # Test load chat API returns active tool server id.
    def test_load_chat_api_returns_active_tool_server_id(self):
        chat = Chat.objects.create(title="Chat", active_tool_slug="time_suite")
        Message.objects.create(
            chat=chat,
            role="assistant",
            content="Visible answer",
            llm_transcript=[
                {"role": "assistant", "content": "", "thinking": "Plan"},
                {"role": "tool", "name": "time_suite__time_now", "tool_name": "time_suite__time_now", "content": '{"ok": true}', "server_id": "time_suite", "server_name": "Time Suite", "tool_id": "time_now", "tool_display_name": "Current Time", "arguments": {"label": "now"}},
                {"role": "assistant", "content": "Visible answer"},
            ],
        )

        response = self.client.get(reverse("load_chat_api", args=[chat.id]))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["active_tool_server_id"], "time_suite")
        self.assertEqual(payload["messages"][0]["content"], "Visible answer")
        self.assertEqual(payload["messages"][0]["activity_segments"][0]["type"], "thought")
        self.assertEqual(payload["messages"][0]["activity_segments"][1]["type"], "tool")

    # Test load chat API returns all active tool server ids.
    def test_load_chat_api_returns_multiple_active_tool_server_ids(self):
        chat = Chat.objects.create(title="Chat", active_tool_slug='["time_suite", "browser"]')
        Message.objects.create(chat=chat, role="user", content="Hello")

        response = self.client.get(reverse("load_chat_api", args=[chat.id]))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["active_tool_server_ids"], ["time_suite", "browser"])
        self.assertEqual(payload["active_tool_server_id"], "time_suite")

    # Test load chat API returns attachment metadata without inline data.
    def test_load_chat_api_returns_attachment_metadata_without_inline_data(self):
        chat = Chat.objects.create(title="Chat")
        message = Message.objects.create(chat=chat, role="user", content="See file")
        attachment = MessageAttachment.objects.create(
            message=message,
            kind="file",
            name="note.txt",
            mime_type="text/plain",
            data="SGVsbG8=",
            size_bytes=5,
        )

        response = self.client.get(reverse("load_chat_api", args=[chat.id]))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        serialized = payload["messages"][0]["attachments"][0]
        self.assertEqual(serialized["id"], attachment.id)
        self.assertEqual(serialized["content_url"], f"/api/attachment/attachment/{attachment.id}/content/")
        self.assertNotIn("data_url", serialized)
        self.assertNotIn("extracted_text", serialized)

    # Test attachment content API streams stored bytes on demand.
    def test_attachment_content_api_streams_stored_bytes(self):
        chat = Chat.objects.create(title="Chat")
        message = Message.objects.create(chat=chat, role="user", content="See file")
        attachment = MessageAttachment.objects.create(
            message=message,
            kind="file",
            name="note.txt",
            mime_type="text/plain",
            data="SGVsbG8=",
            size_bytes=5,
        )

        response = self.client.get(reverse("attachment_content_api", args=["attachment", attachment.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"Hello")
        self.assertEqual(response["Content-Type"], "text/plain")

    # Test attachment content API streams legacy image records.
    def test_attachment_content_api_streams_legacy_image_bytes(self):
        chat = Chat.objects.create(title="Chat")
        message = Message.objects.create(chat=chat, role="user", content="See image")
        image = MessageImage.objects.create(
            message=message,
            mime_type="image/png",
            data="SGVsbG8=",
            order=2,
        )

        response = self.client.get(reverse("attachment_content_api", args=["image", image.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"Hello")
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertIn('filename="image-3"', response["Content-Disposition"])

    # Test attachment content API rejects unknown record types.
    def test_attachment_content_api_rejects_unknown_record_type(self):
        response = self.client.get(reverse("attachment_content_api", args=["unknown", 1]))

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"], "Unknown attachment type")

    # Test delete last assistant API returns the user message to regenerate.
    def test_delete_last_assistant_api_returns_user_message_for_regeneration(self):
        chat = Chat.objects.create(title="Chat")
        user_message = Message.objects.create(chat=chat, role="user", content="See this")
        MessageAttachment.objects.create(
            message=user_message,
            kind=MessageAttachmentKind.IMAGE,
            name="photo.png",
            mime_type="image/png",
            data="iVBORw0KGgo=",
            size_bytes=8,
        )
        assistant_message = Message.objects.create(chat=chat, role="assistant", content="Answer")

        response = self.client.delete(reverse("delete_last_assistant_api", args=[chat.id]))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["user_message"]["content"], "See this")
        self.assertEqual(payload["user_message"]["attachments"][0]["name"], "photo.png")
        self.assertEqual(payload["user_message"]["images"], ["data:image/png;base64,iVBORw0KGgo="])
        self.assertFalse(Message.objects.filter(id=assistant_message.id).exists())

    # Test delete last assistant API rejects chats ending with a user message.
    def test_delete_last_assistant_api_rejects_when_last_message_is_user(self):
        chat = Chat.objects.create(title="Chat")
        Message.objects.create(chat=chat, role="user", content="Still pending")

        response = self.client.delete(reverse("delete_last_assistant_api", args=[chat.id]))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Last message is not from assistant")

    # Test delete message API removes only the selected message.
    def test_delete_message_api_removes_selected_message(self):
        chat = Chat.objects.create(title="Chat")
        first = Message.objects.create(chat=chat, role="user", content="First")
        second = Message.objects.create(chat=chat, role="assistant", content="Second")

        response = self.client.delete(reverse("delete_message_api", args=[first.id]))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Message.objects.filter(id=first.id).exists())
        self.assertTrue(Message.objects.filter(id=second.id).exists())

    # Test rename chat API trims and persists the title.
    def test_rename_chat_api_updates_title(self):
        chat = Chat.objects.create(title="Old")

        response = self.client.patch(
            reverse("rename_chat_api", args=[chat.id]),
            data='{"title":"  New title  "}',
            content_type="application/json",
        )

        chat.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["title"], "New title")
        self.assertEqual(chat.title, "New title")

    # Test delete chat API removes the whole thread.
    def test_delete_chat_api_removes_thread_and_messages(self):
        chat = Chat.objects.create(title="Chat")
        Message.objects.create(chat=chat, role="user", content="Hello")

        response = self.client.delete(reverse("delete_chat_api", args=[chat.id]))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Chat.objects.filter(id=chat.id).exists())
        self.assertEqual(Message.objects.count(), 0)


# Cover Ollama preset API endpoints and model-info integration.
class OllamaPresetApiTests(ToolRegistryTestMixin, TestCase):
    """Cover Ollama preset API endpoints and model-info integration."""

    # Test model info includes active Ollama preset defaults and servers.
    @patch("Apps.UI.views.llm_api.get_model_settings")
    def test_model_info_includes_active_ollama_preset_defaults_and_servers(self, mock_get_model_settings):
        self.write_server(
            'time_suite',
            '''
            MCP_SERVER = {"id": "time_suite", "name": "Time Suite", "description": "Time helpers"}
            TOOLS = [
                {"id": "time_now", "name": "Current Time", "parameters": {"type": "object", "properties": {}}},
                {"id": "timezone_name", "name": "Timezone Name", "parameters": {"type": "object", "properties": {}}},
            ]
            def supports(engine=None, model_name=None):
                return engine == "ollama-service"
            def call_tool(tool_id, arguments, context=None):
                return "ok"
            ''',
        )
        OllamaPreset.objects.create(
            model_name="llama3",
            name="Default",
            config={"num_ctx": 32768, "num_predict": 8192},
            is_default=True,
            is_active=False,
        )
        custom_preset = OllamaPreset.objects.create(
            model_name="llama3",
            name="Custom",
            config={"num_ctx": 65536, "mirostat": 2, "numa": True},
            is_default=False,
            is_active=True,
        )
        mock_get_model_settings.return_value = {
            "modelinfo": {"general.architecture.context_length": 131072},
            "parameters": "temperature 0.8\nPARAMETER mirostat 2\nnuma true",
            "template": "",
            "capabilities": ["tools"],
        }

        response = self.client.get(
            reverse("model_info_api"),
            {"engine": "ollama-service", "model": "llama3"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("ollama_presets", payload)
        self.assertTrue(payload["supports_tool_calling"])
        self.assertEqual(payload["available_tool_servers"][0]["id"], "time_suite")
        self.assertEqual(payload["available_tool_servers"][0]["tool_count"], 2)
        self.assertEqual(payload["defaults"]["num_ctx"], 65536)
        self.assertEqual(payload["defaults"]["temperature"], 0.8)
        self.assertEqual(payload["ollama_presets"]["active_preset_id"], str(custom_preset.id))
        self.assertNotIn("mirostat", payload["defaults"])
        self.assertNotIn("numa", payload["defaults"])

    # Test sync endpoint clones default preset on first change.
    def test_sync_endpoint_clones_default_preset_on_first_change(self):
        response = self.client.post(
            reverse("sync_ollama_preset_api"),
            data='{"model":"llama3","config":{"num_ctx":65536,"num_predict":4096,"think":true,"think_level":"high"}}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["presets"]), 2)
        self.assertEqual(OllamaPreset.objects.filter(model_name="llama3").count(), 2)

    # Test create rename delete endpoints manage custom preset.
    def test_create_rename_delete_endpoints_manage_custom_preset(self):
        created = self.client.post(
            reverse("create_ollama_preset_api"),
            data='{"model":"llama3","name":"Research","config":{"num_ctx":49152}}',
            content_type="application/json",
        )
        self.assertEqual(created.status_code, 200)
        created_payload = created.json()
        active_preset_id = created_payload["active_preset_id"]

        renamed = self.client.post(
            reverse("rename_ollama_preset_api"),
            data=f'{{"model":"llama3","preset_id":"{active_preset_id}","name":"Research v2"}}',
            content_type="application/json",
        )
        self.assertEqual(renamed.status_code, 200)

        deleted = self.client.post(
            reverse("delete_ollama_preset_api"),
            data=f'{{"model":"llama3","preset_id":"{active_preset_id}"}}',
            content_type="application/json",
        )
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(OllamaPreset.objects.filter(model_name="llama3").count(), 1)

    # Test duplicate preset name returns validation error.
    def test_duplicate_preset_name_returns_validation_error(self):
        self.client.post(
            reverse("create_ollama_preset_api"),
            data='{"model":"llama3","name":"Research","config":{"num_ctx":49152}}',
            content_type="application/json",
        )

        duplicate = self.client.post(
            reverse("create_ollama_preset_api"),
            data='{"model":"llama3","name":"Research","config":{"num_ctx":32768}}',
            content_type="application/json",
        )

        self.assertEqual(duplicate.status_code, 400)
        self.assertIn("already exists", duplicate.json()["error"])

    # Test select endpoint activates an existing custom preset.
    def test_select_endpoint_activates_custom_preset(self):
        default_preset = OllamaPreset.objects.create(
            model_name="llama3",
            name="Default",
            config={"num_ctx": 32768},
            is_default=True,
            is_active=True,
        )
        custom_preset = OllamaPreset.objects.create(
            model_name="llama3",
            name="Research",
            config={"num_ctx": 65536},
            is_default=False,
            is_active=False,
        )

        response = self.client.post(
            reverse("select_ollama_preset_api"),
            data=f'{{"model":"llama3","preset_id":"{custom_preset.id}"}}',
            content_type="application/json",
        )

        default_preset.refresh_from_db()
        custom_preset.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["active_preset_id"], str(custom_preset.id))
        self.assertFalse(default_preset.is_active)
        self.assertTrue(custom_preset.is_active)

    # Test default preset mutation errors are returned as validation responses.
    def test_default_preset_mutation_errors_return_400(self):
        default_preset = OllamaPreset.objects.create(
            model_name="llama3",
            name="Default",
            config={"num_ctx": 32768},
            is_default=True,
            is_active=True,
        )

        renamed = self.client.post(
            reverse("rename_ollama_preset_api"),
            data=f'{{"model":"llama3","preset_id":"{default_preset.id}","name":"Renamed"}}',
            content_type="application/json",
        )
        deleted = self.client.post(
            reverse("delete_ollama_preset_api"),
            data=f'{{"model":"llama3","preset_id":"{default_preset.id}"}}',
            content_type="application/json",
        )

        self.assertEqual(renamed.status_code, 400)
        self.assertEqual(deleted.status_code, 400)
        self.assertIn("default preset", renamed.json()["error"])
        self.assertIn("default preset", deleted.json()["error"])

# Cover LM Studio preset API endpoints and model-info integration.
class LmsPresetApiTests(TestCase):
    """Cover LM Studio preset API endpoints and model-info integration."""

    # Test model info includes active LM Studio preset defaults.
    @patch("Apps.UI.views.llm_api.get_model_settings")
    @patch("Apps.Data.lms_presets.lms_api.get_model_settings")
    def test_model_info_includes_active_lms_preset_defaults(self, mock_preset_settings, mock_model_settings):
        base_settings = {
            "context_length": 65536,
            "defaults": {"temperature": 0.7, "think": True},
            "supports_thinking": True,
            "supports_think_level": False,
            "think_param_name": "think",
            "think_level_param_name": "reasoning_effort",
            "supports_vision": True,
            "supports_tool_calling": True,
            "supports_files": True,
            "runtime_limits": {"gpu_devices": [{"id": 0, "name": "RTX"}], "gpu_count": 1, "main_gpu_max": 0},
            "custom_fields": [],
            "capabilities": ["vision", "tools", "thinking", "files"],
        }
        mock_model_settings.return_value = base_settings
        mock_preset_settings.return_value = base_settings

        default_preset = LmsPreset.objects.create(
            model_name="qwen3",
            name="Default",
            config={"operation": {"temperature": 0.7}},
            is_default=True,
            is_active=False,
        )
        custom_preset = LmsPreset.objects.create(
            model_name="qwen3",
            name="Reasoning Off",
            config={"operation": {"temperature": 0.2, "think": False}},
            is_default=False,
            is_active=True,
        )

        response = self.client.get(
            reverse("model_info_api"),
            {"engine": "lms", "model": "qwen3"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("lms_presets", payload)
        self.assertEqual(payload["defaults"]["temperature"], 0.2)
        self.assertFalse(payload["defaults"]["think"])
        self.assertEqual(payload["lms_presets"]["active_preset_id"], str(custom_preset.id))
        self.assertEqual(default_preset.name, "Default")

    # Test sync endpoint clones default LM Studio preset on first change.
    @patch("Apps.Data.lms_presets.lms_api.get_model_settings")
    def test_sync_endpoint_clones_default_lms_preset_on_first_change(self, mock_get_model_settings):
        mock_get_model_settings.return_value = {
            "defaults": {"temperature": 0.7},
        }

        response = self.client.post(
            reverse("sync_lms_preset_api"),
            data='{"model":"qwen3","config":{"operation":{"temperature":0.2,"think":false}}}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["presets"]), 2)
        self.assertEqual(LmsPreset.objects.filter(model_name="qwen3").count(), 2)

    # Test get LM Studio presets endpoint requires a model.
    def test_get_lms_presets_requires_model(self):
        response = self.client.get(reverse("lms_presets_api"))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Model parameter is required")

    # Test create rename delete endpoints manage a custom LM Studio preset.
    @patch("Apps.Data.lms_presets.lms_api.get_model_settings")
    def test_create_rename_delete_endpoints_manage_custom_lms_preset(self, mock_get_model_settings):
        mock_get_model_settings.return_value = {
            "defaults": {"temperature": 0.7},
        }

        created = self.client.post(
            reverse("create_lms_preset_api"),
            data='{"model":"qwen3","name":"Research","config":{"operation":{"temperature":0.2}}}',
            content_type="application/json",
        )
        self.assertEqual(created.status_code, 200)
        active_preset_id = created.json()["active_preset_id"]

        renamed = self.client.post(
            reverse("rename_lms_preset_api"),
            data=f'{{"model":"qwen3","preset_id":"{active_preset_id}","name":"Research v2"}}',
            content_type="application/json",
        )
        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(LmsPreset.objects.get(id=active_preset_id).name, "Research v2")

        deleted = self.client.post(
            reverse("delete_lms_preset_api"),
            data=f'{{"model":"qwen3","preset_id":"{active_preset_id}"}}',
            content_type="application/json",
        )
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(LmsPreset.objects.filter(model_name="qwen3").count(), 1)
        self.assertTrue(LmsPreset.objects.get(model_name="qwen3").is_default)

    # Test duplicate LM Studio preset names return validation errors.
    @patch("Apps.Data.lms_presets.lms_api.get_model_settings")
    def test_duplicate_lms_preset_name_returns_validation_error(self, mock_get_model_settings):
        mock_get_model_settings.return_value = {
            "defaults": {"temperature": 0.7},
        }
        self.client.post(
            reverse("create_lms_preset_api"),
            data='{"model":"qwen3","name":"Research","config":{"operation":{"temperature":0.2}}}',
            content_type="application/json",
        )

        duplicate = self.client.post(
            reverse("create_lms_preset_api"),
            data='{"model":"qwen3","name":"Research","config":{"operation":{"temperature":0.4}}}',
            content_type="application/json",
        )

        self.assertEqual(duplicate.status_code, 400)
        self.assertIn("already exists", duplicate.json()["error"])

    # Test select endpoint activates an existing custom LM Studio preset.
    @patch("Apps.Data.lms_presets.lms_api.get_model_settings")
    def test_select_endpoint_activates_custom_lms_preset(self, mock_get_model_settings):
        mock_get_model_settings.return_value = {
            "defaults": {"temperature": 0.7},
        }
        default_preset = LmsPreset.objects.create(
            model_name="qwen3",
            name="Default",
            config={"operation": {"temperature": 0.7}},
            is_default=True,
            is_active=True,
        )
        custom_preset = LmsPreset.objects.create(
            model_name="qwen3",
            name="Research",
            config={"operation": {"temperature": 0.2}},
            is_default=False,
            is_active=False,
        )

        response = self.client.post(
            reverse("select_lms_preset_api"),
            data=f'{{"model":"qwen3","preset_id":"{custom_preset.id}"}}',
            content_type="application/json",
        )

        default_preset.refresh_from_db()
        custom_preset.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["active_preset_id"], str(custom_preset.id))
        self.assertFalse(default_preset.is_active)
        self.assertTrue(custom_preset.is_active)

    # Test default LM Studio preset mutation errors are returned as validation responses.
    @patch("Apps.Data.lms_presets.lms_api.get_model_settings")
    def test_default_lms_preset_mutation_errors_return_400(self, mock_get_model_settings):
        mock_get_model_settings.return_value = {
            "defaults": {"temperature": 0.7},
        }
        default_preset = LmsPreset.objects.create(
            model_name="qwen3",
            name="Default",
            config={"operation": {"temperature": 0.7}},
            is_default=True,
            is_active=True,
        )

        renamed = self.client.post(
            reverse("rename_lms_preset_api"),
            data=f'{{"model":"qwen3","preset_id":"{default_preset.id}","name":"Renamed"}}',
            content_type="application/json",
        )
        deleted = self.client.post(
            reverse("delete_lms_preset_api"),
            data=f'{{"model":"qwen3","preset_id":"{default_preset.id}"}}',
            content_type="application/json",
        )

        self.assertEqual(renamed.status_code, 400)
        self.assertEqual(deleted.status_code, 400)
        self.assertIn("default preset", renamed.json()["error"])
        self.assertIn("default preset", deleted.json()["error"])


# Verify the three critical fixes: message IDs in headers, no user duplication
# on regenerate, and chat.updated_at bumped on every mutation.
class MessageIdAndRegenerateTests(ToolRegistryTestMixin, TestCase):
    """Verify message IDs are returned and regenerate does not duplicate user messages."""

    def setUp(self):
        super().setUp()
        self.client = Client()

    # chat_api must return X-User-Message-ID and X-Assistant-Message-ID headers
    # so the frontend can stamp fresh rows without waiting for a page reload.
    @patch("Apps.UI.views.llm_api.prepare_runtime")
    @patch("Apps.UI.views.llm_api.generate")
    @patch("Apps.UI.views._get_active_engine", return_value="ollama-service")
    def test_chat_api_returns_message_id_headers(self, _mock_engine, mock_generate, _mock_runtime):
        mock_generate.return_value = [{"message": {"content": "Hi"}}]

        response = self.client.post(
            reverse("chat_api"),
            data='{"message":"Hello","model":"llama3"}',
            content_type="application/json",
        )
        b"".join(response.streaming_content)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.has_header("X-User-Message-ID"), "X-User-Message-ID header missing")
        self.assertTrue(response.has_header("X-Assistant-Message-ID"), "X-Assistant-Message-ID header missing")

        user_id = int(response["X-User-Message-ID"])
        assistant_id = int(response["X-Assistant-Message-ID"])
        self.assertTrue(Message.objects.filter(id=user_id, role="user").exists())
        self.assertTrue(Message.objects.filter(id=assistant_id, role="assistant").exists())

    # After a normal send + regenerate the chat must contain exactly one user
    # message — not two copies of the same prompt.
    @patch("Apps.UI.views.llm_api.prepare_runtime")
    @patch("Apps.UI.views.llm_api.generate")
    @patch("Apps.UI.views._get_active_engine", return_value="ollama-service")
    def test_regenerate_does_not_duplicate_user_message(self, _mock_engine, mock_generate, _mock_runtime):
        mock_generate.return_value = [{"message": {"content": "Answer"}}]

        r1 = self.client.post(
            reverse("chat_api"),
            data='{"message":"hello","model":"llama3"}',
            content_type="application/json",
        )
        b"".join(r1.streaming_content)
        chat_id = r1["X-Chat-ID"]

        self.assertEqual(Message.objects.filter(chat__id=chat_id, role="user").count(), 1)

        mock_generate.return_value = [{"message": {"content": "New answer"}}]
        r2 = self.client.post(
            reverse("regenerate_chat_api", args=[chat_id]),
            data='{"model":"llama3"}',
            content_type="application/json",
        )
        b"".join(r2.streaming_content)

        self.assertEqual(r2.status_code, 200)
        user_count = Message.objects.filter(chat__id=chat_id, role="user").count()
        self.assertEqual(user_count, 1, f"Expected 1 user message after regenerate, got {user_count}")
        assistant_count = Message.objects.filter(chat__id=chat_id, role="assistant").count()
        self.assertEqual(assistant_count, 1, f"Expected 1 assistant message after regenerate, got {assistant_count}")

    # chat.updated_at must be bumped when messages are added so the sidebar
    # sort order stays correct.
    @patch("Apps.UI.views.llm_api.prepare_runtime")
    @patch("Apps.UI.views.llm_api.generate")
    @patch("Apps.UI.views._get_active_engine", return_value="ollama-service")
    def test_chat_updated_at_is_bumped_after_generation(self, _mock_engine, mock_generate, _mock_runtime):
        import time

        mock_generate.return_value = [{"message": {"content": "Hi"}}]

        chat = Chat.objects.create(title="Test")
        ts_before = chat.updated_at

        time.sleep(0.05)

        response = self.client.post(
            reverse("chat_api"),
            data=f'{{"message":"Hi","model":"llama3","chat_id":"{chat.id}"}}',
            content_type="application/json",
        )
        b"".join(response.streaming_content)

        chat.refresh_from_db()
        self.assertGreater(chat.updated_at, ts_before, "chat.updated_at was not bumped after generation")
