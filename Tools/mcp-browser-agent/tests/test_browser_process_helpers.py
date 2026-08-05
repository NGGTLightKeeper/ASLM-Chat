# Copyright NEXTGGTECH. Elastic License 2.0.

from __future__ import annotations

import json

import pytest

from browser_process import BrowserProcessManager, _json_safe_context


# _json_safe_context — strip non-serializable MCP session from worker context.

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
def test_json_safe_context_drops_methods_and_runtime_objects_recursively() -> None:
    class RuntimeObject:
        def callback(self) -> None:
            return None

    runtime = RuntimeObject()
    safe = _json_safe_context(
        {
            "callback": runtime.callback,
            "cancel_event": runtime,
            "nested": {
                "label": "browser",
                "callback": runtime.callback,
                "items": ["kept", runtime.callback, runtime],
            },
        }
    )

    assert "callback" not in safe
    assert "cancel_event" not in safe
    assert safe["nested"] == {"label": "browser", "items": ["kept"]}
    assert json.loads(json.dumps(safe)) == safe


# BrowserProcessManager._worker_response_is_retryable — transient vs permanent errors.

@pytest.mark.unit
def test_worker_response_is_retryable_only_for_transient_errors() -> None:
    manager = BrowserProcessManager()
    assert manager._worker_response_is_retryable({"ok": False, "error": "browser worker exited"})
    assert manager._worker_response_is_retryable({"ok": False, "error": "broken pipe while writing"})
    assert not manager._worker_response_is_retryable({"ok": True})
    assert not manager._worker_response_is_retryable({"ok": False, "error": "element ref not found"})


# BrowserProcessManager._restored_refs_message — prepend stale-ref notice for str and dict.

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
