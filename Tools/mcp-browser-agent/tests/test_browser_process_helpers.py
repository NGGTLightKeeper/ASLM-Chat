# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import pytest

from browser_process import BrowserProcessManager, _json_safe_context


@pytest.mark.unit
def test_json_safe_context_strips_mcp_session() -> None:
    safe = _json_safe_context(
        {
            "mcp_session": object(),
            "engine": "ollama-service",
            "module_dir": "/tmp/project",
        }
    )
    assert "mcp_session" not in safe
    assert safe["engine"] == "ollama-service"
    assert "module_dir" in safe
    assert "project_dir" in safe


@pytest.mark.unit
def test_worker_response_is_retryable_only_for_transient_errors() -> None:
    manager = BrowserProcessManager()
    assert manager._worker_response_is_retryable({"ok": False, "error": "browser worker exited"})
    assert manager._worker_response_is_retryable({"ok": False, "error": "broken pipe while writing"})
    assert not manager._worker_response_is_retryable({"ok": True})
    assert not manager._worker_response_is_retryable({"ok": False, "error": "element ref not found"})


@pytest.mark.unit
def test_restored_refs_message_prepends_note_for_string_and_dict() -> None:
    manager = BrowserProcessManager()
    text = manager._restored_refs_message("snapshot body")
    assert "previous browser refs are no longer valid" in text
    assert "snapshot body" in text

    structured = manager._restored_refs_message(
        {"model_context": "ctx", "ui": {"status": "done"}}
    )
    assert isinstance(structured, dict)
    assert "previous browser refs are no longer valid" in structured["model_context"]
