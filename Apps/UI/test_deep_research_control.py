from __future__ import annotations

import json
import tempfile
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
