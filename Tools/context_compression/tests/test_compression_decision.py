# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import json
from pathlib import Path

import pytest

from context_compression.history_compressor import decide_compression, resolve_context_window_tokens


# resolve_context_window_tokens — model payload and runtime metadata.

@pytest.mark.unit
def test_resolve_context_window_tokens_from_model_defaults() -> None:
    payload = {"defaults": {"num_ctx": 8192}}
    assert resolve_context_window_tokens(payload) == 8192


@pytest.mark.unit
def test_resolve_context_window_tokens_from_runtime_metadata(tmp_path: Path) -> None:
    meta = {
        "active": {"engine": "ollama-service", "model": "qwen"},
        "models": {
            "ollama-service:qwen": {"limits": {"context_window": 32768}},
        },
    }
    path = tmp_path / "model_runtime_metadata.json"
    path.write_text(json.dumps(meta), encoding="utf-8")

    assert (
        resolve_context_window_tokens(
            None,
            runtime_metadata_path=path,
            active_engine="ollama-service",
            active_model="qwen",
        )
        == 32768
    )


# decide_compression — trigger ratio, thresholds, and debug override.

@pytest.mark.unit
def test_decide_compression_enables_at_trigger_ratio() -> None:
    decision = decide_compression(
        used_history_chars=800,
        history_budget_chars=1000,
        model_info_payload={"defaults": {"num_ctx": 4096}},
        runtime_metadata_path=None,
        active_engine="",
        active_model="",
        trigger_ratio=0.80,
    )
    assert decision.enabled
    assert decision.history_budget_chars == 1000
    assert decision.context_window_tokens == 4096
    assert "used=800" in decision.reason


@pytest.mark.unit
def test_decide_compression_disabled_below_threshold() -> None:
    decision = decide_compression(
        used_history_chars=100,
        history_budget_chars=1000,
        model_info_payload=None,
        runtime_metadata_path=None,
        active_engine="",
        active_model="",
    )
    assert not decision.enabled


@pytest.mark.unit
def test_decide_compression_debug_force_4k_overrides_context_window() -> None:
    decision = decide_compression(
        used_history_chars=10_000,
        history_budget_chars=1000,
        model_info_payload={"defaults": {"num_ctx": 128_000}},
        runtime_metadata_path=None,
        active_engine="",
        active_model="",
        debug_force_4k=True,
    )
    assert decision.enabled
    assert decision.context_window_tokens == 4096
