# Copyright NGGT.LightKeeper. All Rights Reserved.

from __future__ import annotations

import json
import re
import uuid
import hashlib
from pathlib import Path
from typing import Any

from Settings import settings

from .file_manifests import UploadedFileManifest, build_uploaded_file_manifest, normalize_upload_name


SANDBOX_ROOT = settings.BASE_DIR / "Tools" / "mcp-sandbox" / "_sandbox"
USER_UPLOAD_ROOT = SANDBOX_ROOT / "User"
SANDBOX_MODEL_PREFIX = "/workspace/_sandbox/User"
UPLOAD_MANIFEST_SUFFIX = ".manifest.json"
MAX_UPLOAD_BYTES = 256 * 1024 * 1024


def _safe_scope(value: str | None) -> str:
    raw_value = str(value or "").strip()
    if not raw_value:
        return "pending"
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", raw_value)[:96] or "pending"


def _stored_file_name(file_id: str, original_name: str) -> str:
    safe_name = normalize_upload_name(original_name)
    safe_name = re.sub(r"[\x00-\x1f<>:\"|?*]+", "_", safe_name).strip(" .") or "uploaded-file"
    normalized_id = re.sub(r"[^a-zA-Z0-9-]+", "", str(file_id or "")) or "upload"
    return f"{normalized_id}__{safe_name}"


def display_kind_for_upload(name: str, mime: str) -> tuple[str, str]:
    """Return UI-facing kind and label for one upload."""

    suffix = Path(normalize_upload_name(name)).suffix.lower()
    normalized_mime = str(mime or "").lower()
    if normalized_mime.startswith("image/"):
        return "image", "Image"
    if suffix == ".zip" or normalized_mime in {"application/zip", "application/x-zip-compressed"}:
        return "archive", "ZIP archive"
    if suffix in {".rar", ".7z"}:
        return "archive", "Archive"
    if suffix == ".pdf" or normalized_mime == "application/pdf":
        return "document", "PDF document"
    if suffix == ".docx":
        return "document", "Word document"
    if suffix == ".xlsx":
        return "table", "Excel spreadsheet"
    if suffix == ".csv":
        return "table", "CSV table"
    if suffix == ".pptx":
        return "presentation", "PowerPoint presentation"
    if suffix in {".py", ".js", ".ts", ".css", ".html", ".sql", ".sh", ".ps1"}:
        return "code", "Code file"
    if normalized_mime.startswith("text/") or suffix in {".txt", ".md", ".log", ".json", ".yaml", ".yml", ".xml"}:
        return "text", "Text file"
    return "file", "File"


def public_upload_payload(manifest: UploadedFileManifest, *, status: str = "ready") -> dict[str, Any]:
    """Return the small user-facing upload payload."""

    display_kind, type_label = display_kind_for_upload(manifest.name, manifest.mime)
    return {
        "file_id": manifest.file_id,
        "name": manifest.name,
        "size_bytes": manifest.size_bytes,
        "status": status,
        "display_kind": display_kind,
        "type_label": type_label,
    }


def model_upload_payload(manifest: dict[str, Any], *, sandbox_enabled: bool = False) -> dict[str, Any]:
    """Return a model-facing manifest that respects the selected sandbox state."""

    payload = dict(manifest or {})
    if not sandbox_enabled:
        payload["sandbox_path"] = None
        recommended_tools = payload.get("recommended_tools")
        if isinstance(recommended_tools, list):
            payload["recommended_tools"] = [tool for tool in recommended_tools if tool != "sandbox"]
    return payload


def _manifest_sidecar_path(file_path: Path) -> Path:
    return file_path.with_name(f"{file_path.name}{UPLOAD_MANIFEST_SUFFIX}")


def _model_sandbox_path(scope: str, stored_name: str) -> str:
    return f"{SANDBOX_MODEL_PREFIX}/{scope}/{stored_name}".replace("\\", "/")


def _file_sha256(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes or b"").hexdigest()


def _load_manifest_from_sidecar(sidecar_path: Path) -> dict[str, Any] | None:
    try:
        manifest = json.loads(sidecar_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return manifest if isinstance(manifest, dict) else None


def _find_existing_upload(
    target_dir: Path,
    *,
    clean_name: str,
    file_bytes: bytes,
) -> tuple[Path, dict[str, Any] | None] | None:
    expected_sha256 = _file_sha256(file_bytes)
    expected_size = len(file_bytes)
    expected_name = str(clean_name or "").strip()

    for file_path in target_dir.iterdir():
        if not file_path.is_file() or file_path.name.endswith(UPLOAD_MANIFEST_SUFFIX):
            continue
        sidecar_path = _manifest_sidecar_path(file_path)
        manifest = _load_manifest_from_sidecar(sidecar_path) if sidecar_path.exists() else None
        if manifest:
            manifest_sha = str(manifest.get("sha256") or "")
            manifest_size = int(manifest.get("size_bytes") or 0)
            manifest_name = str(manifest.get("name") or "")
            if (
                manifest_sha == expected_sha256
                and manifest_size == expected_size
                and manifest_name == expected_name
            ):
                return file_path, manifest
            continue
        try:
            existing_bytes = file_path.read_bytes()
        except OSError:
            continue
        if existing_bytes == file_bytes:
            return file_path, None
    return None


def _manifest_from_dict(manifest: dict[str, Any]) -> UploadedFileManifest | None:
    try:
        return UploadedFileManifest(**manifest)
    except TypeError:
        return None


def _normalize_existing_manifest_for_path(
    manifest: dict[str, Any],
    *,
    safe_scope: str,
    stored_name: str,
) -> UploadedFileManifest | None:
    parsed = _manifest_from_dict(manifest)
    if parsed is None:
        return None

    expected_sandbox_path = _model_sandbox_path(safe_scope, stored_name)
    if str(parsed.sandbox_path or "") == expected_sandbox_path:
        return parsed

    patched = dict(manifest)
    patched["sandbox_path"] = expected_sandbox_path
    return _manifest_from_dict(patched)


def save_upload_to_sandbox(
    uploaded_file: Any,
    *,
    scope: str | None = None,
    model_supports_vision: bool = False,
) -> tuple[UploadedFileManifest, dict[str, Any]]:
    """Persist one Django uploaded file and return its private manifest plus public payload."""

    clean_name = normalize_upload_name(getattr(uploaded_file, "name", "") or "uploaded-file")
    size_bytes = int(getattr(uploaded_file, "size", 0) or 0)
    if size_bytes > MAX_UPLOAD_BYTES:
        raise ValueError("File is too large")

    safe_scope = _safe_scope(scope)
    target_dir = USER_UPLOAD_ROOT / safe_scope
    target_dir.mkdir(parents=True, exist_ok=True)

    chunks = uploaded_file.chunks() if hasattr(uploaded_file, "chunks") else [uploaded_file.read()]
    payload_chunks = [chunk for chunk in chunks if chunk]
    file_bytes = b"".join(payload_chunks)
    mime = str(getattr(uploaded_file, "content_type", "") or "")

    existing_upload = _find_existing_upload(
        target_dir,
        clean_name=clean_name,
        file_bytes=file_bytes,
    )
    if existing_upload:
        existing_path, existing_manifest = existing_upload
        if existing_manifest:
            parsed_manifest = _normalize_existing_manifest_for_path(
                existing_manifest,
                safe_scope=safe_scope,
                stored_name=existing_path.name,
            )
            if parsed_manifest is not None:
                return parsed_manifest, public_upload_payload(parsed_manifest)

        # Existing binary matched but sidecar is missing/corrupted. Rebuild one
        # manifest bound to the existing file path, then reuse it.
        rebuilt_manifest = build_uploaded_file_manifest(
            file_bytes,
            name=clean_name,
            mime=mime,
            sandbox_path=_model_sandbox_path(safe_scope, existing_path.name),
            model_supports_vision=model_supports_vision,
            file_id=uuid.uuid4().hex,
        )
        _manifest_sidecar_path(existing_path).write_text(
            json.dumps(rebuilt_manifest.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return rebuilt_manifest, public_upload_payload(rebuilt_manifest)

    file_id = uuid.uuid4().hex
    stored_name = _stored_file_name(file_id, clean_name)
    target_path = target_dir / stored_name
    with target_path.open("wb") as handle:
        handle.write(file_bytes)

    manifest = build_uploaded_file_manifest(
        file_bytes,
        name=clean_name,
        mime=mime,
        sandbox_path=_model_sandbox_path(safe_scope, stored_name),
        model_supports_vision=model_supports_vision,
        file_id=file_id,
    )
    _manifest_sidecar_path(target_path).write_text(
        json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest, public_upload_payload(manifest)


def load_upload_manifest(file_id: str) -> dict[str, Any] | None:
    """Load a private manifest by file id from the sandbox sidecars."""

    normalized_id = re.sub(r"[^a-fA-F0-9-]+", "", str(file_id or ""))
    if not normalized_id:
        return None
    for sidecar in USER_UPLOAD_ROOT.glob(f"**/*{UPLOAD_MANIFEST_SUFFIX}"):
        manifest = _load_manifest_from_sidecar(sidecar)
        if manifest and str(manifest.get("file_id") or "") == normalized_id:
            return manifest
    return None
