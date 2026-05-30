# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import json
from pathlib import Path

import pytest

from browser_screenshot import _load_model_runtime_metadata, _model_supports_vision, _png_dimensions


def _minimal_png(width: int, height: int) -> bytes:
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr_data = (
        width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x02\x00\x00\x00"
    )
    ihdr_chunk = (
        len(ihdr_data).to_bytes(4, "big")
        + b"IHDR"
        + ihdr_data
        + b"\x00\x00\x00\x00"
    )
    iend_chunk = b"\x00\x00\x00\x00IEND\xaeB`\x82"
    return signature + ihdr_chunk + iend_chunk


@pytest.mark.unit
def test_png_dimensions_reads_width_and_height() -> None:
    data = _minimal_png(640, 480)
    dims = _png_dimensions(data)
    assert dims == {"width": 640, "height": 480}
    assert _png_dimensions(b"not-a-png") is None


@pytest.mark.unit
def test_model_supports_vision_from_runtime_metadata(tmp_path: Path) -> None:
    meta = {
        "active": {"engine": "ollama-service", "model": "vision-model"},
        "models": {
            "ollama-service:vision-model": {
                "capabilities": {"vision": True},
            }
        },
    }
    path = tmp_path / "Tools" / "model_runtime_metadata.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(meta), encoding="utf-8")

    supported, record, reason = _model_supports_vision(
        {"module_dir": str(tmp_path), "engine": "ollama-service", "model_name": "vision-model"}
    )
    assert supported
    assert reason == "matched"
    assert isinstance(record, dict)

    payload = _load_model_runtime_metadata(str(tmp_path))
    assert isinstance(payload.get("models"), dict)
