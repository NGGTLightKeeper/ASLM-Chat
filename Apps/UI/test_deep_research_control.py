from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from Tools import deep_research_control as control
from Apps.UI import views


class DeepResearchControlApiTests(SimpleTestCase):
    def setUp(self) -> None:
        self.control_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.control_directory.cleanup)
        root = Path(self.control_directory.name)
        self.enterContext(mock.patch.object(control, "STATE_ROOT", root / "state"))
        self.enterContext(mock.patch.object(control, "COMMAND_ROOT", root / "commands"))
        self.session_id = control.new_session_id()
        control.create_session(
            self.session_id,
            topic="Test topic",
            status="awaiting_approval",
            extra={"plan": "- [ ] Verify the claim", "plan_version": 1},
        )

    def post(self, payload: dict):
        return self.client.post(
            "/api/deep-research/control/",
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_state_can_be_read_and_current_plan_approved(self) -> None:
        response = self.client.get(
            "/api/deep-research/control/",
            {"session_id": self.session_id},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["state"]["plan_version"], 1)

        response = self.post(
            {
                "session_id": self.session_id,
                "action": "approve",
                "expected_plan_version": 1,
            }
        )
        self.assertEqual(response.status_code, 202)
        commands = control.read_commands(self.session_id)
        self.assertEqual(commands[0][1]["action"], "approve")

    def test_stale_revision_is_rejected_with_latest_state(self) -> None:
        response = self.post(
            {
                "session_id": self.session_id,
                "action": "revise",
                "plan": "- [ ] Use the revised evidence goal",
                "expected_plan_version": 0,
            }
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["state"]["plan_version"], 1)
        self.assertEqual(control.read_commands(self.session_id), [])

    def test_cancel_is_idempotent_after_terminal_state(self) -> None:
        control.update_state(self.session_id, status="cancelled")
        response = self.post(
            {
                "session_id": self.session_id,
                "action": "cancel",
                "expected_plan_version": 1,
            }
        )
        self.assertEqual(response.status_code, 202)
        self.assertTrue(response.json()["terminal"])

    @mock.patch.object(views.tool_registry, "abort_active_research", return_value=1)
    def test_cancel_immediately_interrupts_matching_active_worker(self, abort_research) -> None:
        response = self.post(
            {
                "session_id": self.session_id,
                "action": "cancel",
                "expected_plan_version": 1,
            }
        )

        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertTrue(payload["terminal"])
        self.assertEqual(payload["interrupted_active_tools"], 1)
        self.assertEqual(payload["state"]["status"], "cancelled")
        self.assertFalse(payload["state"]["can_stop"])
        abort_research.assert_called_once_with(self.session_id)

    @mock.patch.object(views.tool_registry, "abort_active_research", return_value=0)
    def test_cancel_hides_stop_while_worker_stops_cooperatively(self, abort_research) -> None:
        response = self.post(
            {
                "session_id": self.session_id,
                "action": "cancel",
                "expected_plan_version": 1,
            }
        )

        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertFalse(payload["terminal"])
        self.assertEqual(payload["state"]["status"], "stopping")
        self.assertFalse(payload["state"]["can_stop"])
        persisted = control.read_state(self.session_id)
        self.assertEqual(persisted["status"], "stopping")
        self.assertFalse(persisted["can_stop"])
        abort_research.assert_called_once_with(self.session_id)

    def test_invalid_session_id_is_rejected(self) -> None:
        response = self.post({"session_id": "../../outside", "action": "cancel"})
        self.assertEqual(response.status_code, 400)

    def test_revision_is_rejected_after_edit_window_closes(self) -> None:
        control.update_state(self.session_id, can_edit=False)

        response = self.post(
            {
                "session_id": self.session_id,
                "action": "revise",
                "plan": "- [ ] Too late",
                "expected_plan_version": 1,
            }
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(control.read_commands(self.session_id), [])

    def test_processed_commands_are_removed_after_acknowledgement(self) -> None:
        control.submit_command(
            self.session_id,
            "approve",
            expected_plan_version=1,
        )
        commands = control.read_commands(self.session_id)
        filename = commands[0][0]
        command_directory = control.COMMAND_ROOT / control.session_key(self.session_id)

        self.assertEqual(
            control.read_commands(self.session_id, processed={filename}),
            [],
        )
        self.assertFalse((command_directory / filename).exists())
        self.assertFalse(command_directory.exists())

    def test_terminal_snapshot_removes_obsolete_command_inbox(self) -> None:
        control.submit_command(
            self.session_id,
            "approve",
            expected_plan_version=1,
        )
        command_directory = control.COMMAND_ROOT / control.session_key(self.session_id)
        self.assertTrue(command_directory.exists())

        control.update_state(self.session_id, status="completed", report="Done")

        self.assertFalse(command_directory.exists())

    def test_stale_worker_checkpoint_cannot_resurrect_a_stopping_run(self) -> None:
        control.update_state(
            self.session_id,
            status="stopping",
            phase="stopping",
            can_stop=False,
            can_edit=False,
            can_approve=False,
        )

        state = control.update_state(
            self.session_id,
            status="researching",
            phase="search",
            can_stop=True,
            can_edit=True,
            can_approve=True,
            source_count=7,
        )

        self.assertEqual(state["status"], "stopping")
        self.assertEqual(state["phase"], "stopping")
        self.assertFalse(state["can_stop"])
        self.assertFalse(state["can_edit"])
        self.assertFalse(state["can_approve"])
        self.assertEqual(state["source_count"], 7)

        terminal = control.update_state(
            self.session_id,
            status="cancelled",
            phase="cancelled",
        )
        self.assertEqual(terminal["status"], "cancelled")
        self.assertEqual(terminal["phase"], "cancelled")


class DeepResearchStorageTests(SimpleTestCase):
    def _patch_storage(self, runtime_root: Path, legacy_root: Path) -> None:
        self.enterContext(mock.patch.object(control, "CONTROL_ROOT", runtime_root))
        self.enterContext(mock.patch.object(control, "STATE_ROOT", runtime_root / "state"))
        self.enterContext(mock.patch.object(control, "COMMAND_ROOT", runtime_root / "commands"))
        self.enterContext(mock.patch.object(control, "LEGACY_CONTROL_ROOT", legacy_root))
        self.enterContext(mock.patch.object(control, "_last_retention_check", 0.0))

    def test_runtime_directory_can_be_overridden(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.dict(
                os.environ,
                {"ASLM_DEEP_RESEARCH_RUNTIME_DIR": directory},
                clear=False,
            ):
                self.assertEqual(control._default_control_root(), Path(directory))

    def test_windows_default_is_outside_the_repository(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("ASLM_DEEP_RESEARCH_RUNTIME_DIR", None)
                os.environ["LOCALAPPDATA"] = directory
                with mock.patch.object(control.platform, "system", return_value="Windows"):
                    expected = Path(directory) / "ASLM-Chat" / "runtime" / "deep-research"
                    self.assertEqual(control._default_control_root(), expected)
                    self.assertFalse(expected.is_relative_to(control.PROJECT_ROOT))

    def test_legacy_store_is_atomically_moved_and_payload_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime_root = root / "runtime"
            legacy_root = root / "project" / "Data" / "deep_research"
            session_key = "a" * 32
            session_id = f"deep-research:{session_key}"
            state_payload = {
                "schema_version": 1,
                "session_id": session_id,
                "status": "awaiting_approval",
                "updated_at": time.time(),
                "report": "Evidence [caaaaaaaa-7]",
                "citations": [{"handle": "caaaaaaaa-7", "url": "https://example.test"}],
                "citation_next": 8,
            }
            command_payload = {
                "schema_version": 1,
                "command_id": "command-1",
                "session_id": session_id,
                "action": "approve",
            }
            legacy_state = legacy_root / "state" / f"{session_key}.json"
            legacy_command = legacy_root / "commands" / session_key / "command.json"
            legacy_state.parent.mkdir(parents=True)
            legacy_command.parent.mkdir(parents=True)
            legacy_state.write_text(json.dumps(state_payload), encoding="utf-8")
            legacy_command.write_text(json.dumps(command_payload), encoding="utf-8")
            self._patch_storage(runtime_root, legacy_root)

            control._ensure_roots()

            self.assertEqual(control._read_json(runtime_root / "state" / legacy_state.name), state_payload)
            self.assertEqual(
                control._read_json(runtime_root / "commands" / session_key / legacy_command.name),
                command_payload,
            )
            self.assertTrue((runtime_root / control._MIGRATION_MARKER).exists())
            self.assertFalse(legacy_root.exists())

    def test_migration_keeps_newer_runtime_state_and_legacy_only_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime_root = root / "runtime"
            legacy_root = root / "legacy"
            session_key = "b" * 32
            legacy_state = legacy_root / "state" / f"{session_key}.json"
            current_state = runtime_root / "state" / f"{session_key}.json"
            legacy_state.parent.mkdir(parents=True)
            current_state.parent.mkdir(parents=True)
            legacy_state.write_text(
                json.dumps(
                    {"status": "completed", "updated_at": time.time() - 10, "citation_next": 12}
                ),
                encoding="utf-8",
            )
            current_state.write_text(
                json.dumps({"status": "completed", "updated_at": time.time(), "report": "new"}),
                encoding="utf-8",
            )
            self._patch_storage(runtime_root, legacy_root)

            control._ensure_roots()

            merged = control._read_json(current_state)
            self.assertGreater(merged["updated_at"], time.time() - 5)
            self.assertEqual(merged["report"], "new")
            self.assertEqual(merged["citation_next"], 12)
            self.assertFalse(legacy_root.exists())

    def test_locked_legacy_artifact_does_not_break_runtime_storage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime_root = root / "runtime"
            legacy_root = root / "legacy"
            session_key = "c" * 32
            legacy_state = legacy_root / "state" / f"{session_key}.json"
            legacy_state.parent.mkdir(parents=True)
            legacy_state.write_text(
                json.dumps({"status": "researching", "updated_at": time.time()}),
                encoding="utf-8",
            )
            self._patch_storage(runtime_root, legacy_root)
            original_unlink = Path.unlink

            def fail_for_legacy(path: Path, *args, **kwargs):
                if path == legacy_state:
                    raise PermissionError("locked")
                return original_unlink(path, *args, **kwargs)

            with mock.patch.object(Path, "unlink", new=fail_for_legacy):
                control._ensure_roots()

            self.assertTrue(legacy_state.exists())
            self.assertTrue((runtime_root / "state" / legacy_state.name).exists())
            self.assertFalse((runtime_root / control._MIGRATION_MARKER).exists())

    def test_restart_cleanup_removes_persisted_acknowledgements_and_terminal_inboxes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime_root = root / "runtime"
            self._patch_storage(runtime_root, root / "missing-legacy")
            active_key = "d" * 32
            terminal_key = "e" * 32
            processed_name = "0001-processed.json"
            pending_name = "0002-pending.json"
            control._atomic_write_json(
                runtime_root / "state" / f"{active_key}.json",
                {
                    "status": "researching",
                    "processed_commands": [processed_name],
                    "updated_at": time.time(),
                },
            )
            control._atomic_write_json(
                runtime_root / "state" / f"{terminal_key}.json",
                {"status": "completed", "updated_at": time.time()},
            )
            active_commands = runtime_root / "commands" / active_key
            terminal_commands = runtime_root / "commands" / terminal_key
            active_commands.mkdir(parents=True)
            terminal_commands.mkdir(parents=True)
            (active_commands / processed_name).write_text("{}", encoding="utf-8")
            (active_commands / pending_name).write_text("{}", encoding="utf-8")
            (terminal_commands / pending_name).write_text("{}", encoding="utf-8")

            control._apply_terminal_retention(force=True)

            self.assertFalse((active_commands / processed_name).exists())
            self.assertTrue((active_commands / pending_name).exists())
            self.assertFalse(terminal_commands.exists())

    def test_terminal_retention_bounds_age_and_count_without_touching_active_runs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime_root = root / "runtime"
            legacy_root = root / "missing-legacy"
            self._patch_storage(runtime_root, legacy_root)
            (runtime_root / "state").mkdir(parents=True)
            (runtime_root / "commands").mkdir(parents=True)
            now = time.time()
            keys = ["1" * 32, "2" * 32, "3" * 32, "4" * 32]
            snapshots = [
                (keys[0], "completed", now - 10),
                (keys[1], "failed", now - 20),
                (keys[2], "cancelled", now - (3 * 86400)),
                (keys[3], "researching", now - (90 * 86400)),
            ]
            for key, status, updated_at in snapshots:
                control._atomic_write_json(
                    runtime_root / "state" / f"{key}.json",
                    {"status": status, "updated_at": updated_at},
                )
                command_dir = runtime_root / "commands" / key
                command_dir.mkdir(parents=True)
                (command_dir / "command.json").write_text("{}", encoding="utf-8")

            with mock.patch.dict(
                os.environ,
                {
                    "ASLM_DEEP_RESEARCH_TERMINAL_RETENTION_DAYS": "1",
                    "ASLM_DEEP_RESEARCH_TERMINAL_RETENTION_MAX": "1",
                },
                clear=False,
            ):
                control._apply_terminal_retention(force=True)

            self.assertTrue((runtime_root / "state" / f"{keys[0]}.json").exists())
            self.assertFalse((runtime_root / "state" / f"{keys[1]}.json").exists())
            self.assertFalse((runtime_root / "state" / f"{keys[2]}.json").exists())
            self.assertTrue((runtime_root / "state" / f"{keys[3]}.json").exists())
            self.assertFalse((runtime_root / "commands" / keys[1]).exists())
            self.assertFalse((runtime_root / "commands" / keys[2]).exists())
            self.assertTrue((runtime_root / "commands" / keys[3]).exists())


class DeepResearchTranscriptReloadTests(SimpleTestCase):
    def test_pending_tool_call_restores_pollable_research_card(self) -> None:
        session_id = "deep-research:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        message = SimpleNamespace(
            llm_transcript=[
                {
                    "role": "assistant",
                    "content": "",
                    "thinking": "I will start research.",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "deep_research__deep_research",
                                "arguments": {
                                    "topic": "Reload-safe research",
                                    "max_rounds": 2,
                                    "session_id": session_id,
                                },
                            }
                        }
                    ],
                }
            ]
        )

        segments = views._build_activity_segments(message)

        research = next(segment for segment in segments if segment["type"] == "tool")
        self.assertEqual(research["toolUi"]["kind"], "deep_research")
        self.assertEqual(research["toolUi"]["session_id"], session_id)
        self.assertEqual(research["toolUi"]["query_budget"], 4)
        self.assertIsNone(research["result"])

    def test_completed_tool_call_and_result_merge_without_duplicate_card(self) -> None:
        message = SimpleNamespace(
            llm_transcript=[
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "deep_research__deep_research",
                                "arguments": {"topic": "Completed research", "max_rounds": 2},
                            }
                        }
                    ],
                },
                {
                    "role": "tool",
                    "alias": "deep_research__deep_research__0",
                    "content": "Final report",
                    "tool_ui": {"kind": "deep_research", "status": "completed"},
                },
            ]
        )

        tools = [
            segment
            for segment in views._build_activity_segments(message)
            if segment["type"] == "tool"
        ]

        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0]["result"], "Final report")
        self.assertEqual(tools[0]["toolUi"]["status"], "completed")
