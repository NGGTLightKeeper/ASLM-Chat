# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from typing import Any

SERVER_ROOT = Path(__file__).resolve().parent
MODEL_RUNTIME_METADATA_PATH = SERVER_ROOT.parent / "model_runtime_metadata.json"
SANDBOX_SCREEN_TARGETS = {
    "linux_sandbox": (("mcp-sandbox", "_sandbox", "screens"), "screens"),
}


def _load_model_runtime_metadata(module_dir: str | None = None) -> dict[str, Any]:
    candidates = []
    if module_dir:
        candidates.append(Path(module_dir) / "Tools" / "model_runtime_metadata.json")
    candidates.append(MODEL_RUNTIME_METADATA_PATH)

    for path in candidates:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def _model_supports_vision(context: dict[str, Any] | None) -> tuple[bool, dict[str, Any], str]:
    safe_context = context or {}
    payload = _load_model_runtime_metadata(str(safe_context.get("module_dir") or ""))
    if not payload:
        return False, {}, "missing_metadata"

    active = payload.get("active", {})
    if not isinstance(active, dict):
        active = {}

    engine = str(safe_context.get("engine") or active.get("engine") or "").strip()
    model_name = str(safe_context.get("model_name") or active.get("model") or "").strip()
    models = payload.get("models", {})
    if not isinstance(models, dict):
        return False, {}, "missing_models"

    record = models.get(f"{engine}:{model_name}") if engine and model_name else None
    if not isinstance(record, dict):
        active_engine = str(active.get("engine") or "").strip()
        active_model = str(active.get("model") or "").strip()
        record = models.get(f"{active_engine}:{active_model}") if active_engine and active_model else None

    if not isinstance(record, dict):
        return False, {}, "missing_model_record"

    capabilities = record.get("capabilities", {})
    if not isinstance(capabilities, dict):
        capabilities = {}
    return bool(capabilities.get("vision", False)), record, "matched"


def _png_dimensions(data: bytes) -> dict[str, int] | None:
    if len(data) < 24 or not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    return {
        "width": int.from_bytes(data[16:20], "big"),
        "height": int.from_bytes(data[20:24], "big"),
    }


def _sandbox_screens_dir(context: dict[str, Any] | None) -> tuple[Path | None, str]:
    safe_context = context or {}
    sandbox_enabled = bool(safe_context.get("sandbox_enabled"))
    selected = safe_context.get("selected_tool_server_ids")
    if isinstance(selected, list):
        sandbox_enabled = sandbox_enabled or any(str(item) == "sandbox" for item in selected)

    module_dir = str(safe_context.get("module_dir") or safe_context.get("project_dir") or "").strip()
    if not module_dir:
        return None, ""

    mode = "linux_sandbox" if sandbox_enabled else ""
    target = SANDBOX_SCREEN_TARGETS.get(mode)
    if not target:
        return None, ""
    path_parts, model_prefix = target
    return Path(module_dir).joinpath("Tools", *path_parts), model_prefix


def _image_result_from_png(
    *,
    data: bytes,
    path: str,
    host_path: str,
    supports_vision: bool,
    model_record: dict[str, Any],
    metadata_source: str,
) -> dict[str, Any]:
    image: dict[str, Any] = {
        "kind": "image",
        "path": path,
        "host_path": host_path,
        "mime": "image/png",
        "size_bytes": len(data),
        "encoding": None,
    }
    dimensions = _png_dimensions(data)
    if dimensions:
        image.update(dimensions)

    if supports_vision:
        image["preview"] = {
            "type": "inline_base64",
            "mime_type": "image/png",
            "data_base64": base64.b64encode(data).decode("utf-8"),
        }
        return image

    image["preview"] = {
        "type": "text_placeholder",
        "message": (
            "Visual preview was withheld because the active model metadata says "
            "this model does not support vision."
        ),
    }
    image["vision_gate"] = {
        "allowed": False,
        "metadata_source": metadata_source,
        "engine": model_record.get("engine", ""),
        "model": model_record.get("model", ""),
    }
    return image


def _structured_image_result(image: dict[str, Any], *, supports_vision: bool) -> dict[str, Any]:
    if supports_vision and image.get("preview", {}).get("type") == "inline_base64":
        return {
            "ok": True,
            "tool": "browser_screenshot",
            "result": image,
            "error": None,
            "warnings": [],
            "truncated": False,
        }

    path = str(image.get("path") or image.get("host_path") or "screenshot.png")
    result = dict(image)
    result["model_context"] = (
        f"Screenshot saved: {path}. "
        "The active model does not support vision, so only image metadata is available. "
        "If sandbox is enabled, use view_image on this path with a vision-capable model or edit the file from the workspace."
    )
    result["ui"] = {
        "kind": "browser_screenshot",
        "status": "done",
        "image": dict(image),
    }
    return result


async def capture_browser_screenshot(full_page: bool, context: dict[str, Any] | None = None) -> dict[str, Any]:
    from browser import DOWNLOADS_DIR, log, state

    sandbox_dir, sandbox_prefix = _sandbox_screens_dir(context)
    output_dir = sandbox_dir or (DOWNLOADS_DIR / "screens")
    output_dir.mkdir(parents=True, exist_ok=True)

    file_name = f"screenshot_{int(time.time())}.png"
    file_path = output_dir / file_name
    await state.page.screenshot(path=str(file_path), full_page=full_page)
    log.info("Screenshot saved: %s", file_path)

    data = file_path.read_bytes()
    model_path = f"{sandbox_prefix}/{file_name}" if sandbox_prefix else str(file_path)
    supports_vision, model_record, metadata_source = _model_supports_vision(context)
    image = _image_result_from_png(
        data=data,
        path=model_path,
        host_path=str(file_path),
        supports_vision=supports_vision,
        model_record=model_record,
        metadata_source=metadata_source,
    )
    return _structured_image_result(image, supports_vision=supports_vision)
