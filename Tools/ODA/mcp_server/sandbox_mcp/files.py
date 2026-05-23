"""Explicit file bridge: staging, validation, per-run input/output mounts."""
from __future__ import annotations

import base64
import ctypes
import json
import mimetypes
import os
import re
import shutil
import subprocess
import stat
import tempfile
import time
import uuid
import zipfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TMP_ROOT = Path(tempfile.gettempdir()) / "ada-sandbox"
DEFAULT_SHARED_ROOT = _REPO_ROOT / "tmp" / "_sandbox"
SHARED_DIR_NAME = "_sandbox"
MODEL_SHARED_ROOT = "/mnt/data/_sandbox"

SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9._-]{1,128}$")
ALLOWED_EXTENSIONS = frozenset(
    {
        ".csv",
        ".json",
        ".txt",
        ".py",
        ".md",
        ".tsv",
        ".parquet",
        ".xlsx",
        ".zip",
        ".html",
        ".xml",
        ".yaml",
        ".yml",
        ".log",
        ".ndjson",
    }
)

DEFAULT_MAX_FILE_BYTES = 50 * 1024 * 1024
DEFAULT_MAX_OUTPUT_TOTAL_BYTES = 50 * 1024 * 1024
DEFAULT_MAX_FILES_PER_LIST = 20
DEFAULT_MAX_SHARED_LIST_FILES = 100
DEFAULT_STAGING_TTL_SECONDS = 24 * 60 * 60
DEFAULT_ARTIFACTS_TTL_SECONDS = 60 * 60
DEFAULT_ARCHIVE_TTL_SECONDS = 30 * 60


class FileBridgeError(ValueError):
    pass


_WRITABLE_MODE = stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC
_CHMOD_NO_FOLLOW = os.chmod in getattr(os, "supports_follow_symlinks", [])


def _chmod_writable(target: Path | str) -> None:
    """chmod without following symlinks (never touch link targets on the host)."""
    path = Path(target)
    try:
        st = path.lstat()
    except OSError:
        return
    if stat.S_ISLNK(st.st_mode):
        if _CHMOD_NO_FOLLOW:
            try:
                os.chmod(path, stat.S_IWRITE | stat.S_IREAD, follow_symlinks=False)
            except OSError:
                pass
        return
    try:
        if _CHMOD_NO_FOLLOW:
            os.chmod(path, _WRITABLE_MODE, follow_symlinks=False)
        else:
            os.chmod(path, _WRITABLE_MODE)
    except OSError:
        pass


def remove_tree(path: Path) -> None:
    def _make_writable_and_retry(func, failed_path, _exc_info) -> None:
        _chmod_writable(failed_path)
        try:
            func(failed_path)
        except OSError:
            pass

    shutil.rmtree(path, ignore_errors=False, onerror=_make_writable_and_retry)


def make_tree_writable(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    _chmod_writable(path)
    if not path.is_dir():
        return
    for root, dirs, files in os.walk(path, topdown=True, followlinks=False):
        root_path = Path(root)
        for name in dirs + files:
            _chmod_writable(root_path / name)


def send_to_trash(path: Path) -> None:
    if not path.exists():
        return
    make_tree_writable(path)
    if os.name == "nt":
        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [
                ("hwnd", ctypes.c_void_p),
                ("wFunc", ctypes.c_uint),
                ("pFrom", ctypes.c_wchar_p),
                ("pTo", ctypes.c_wchar_p),
                ("fFlags", ctypes.c_uint),
                ("fAnyOperationsAborted", ctypes.c_bool),
                ("hNameMappings", ctypes.c_void_p),
                ("lpszProgressTitle", ctypes.c_wchar_p),
            ]

        operation = SHFILEOPSTRUCTW()
        operation.wFunc = 3  # FO_DELETE
        operation.pFrom = str(path.resolve()) + "\0\0"
        operation.fFlags = 0x40 | 0x10 | 0x04 | 0x400  # recycle, no confirm, silent, no UI
        result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))
        if result != 0 or operation.fAnyOperationsAborted:
            raise OSError(f"SHFileOperationW failed with code {result}")
        return

    try:
        from send2trash import send2trash  # type: ignore
    except Exception:
        send2trash = None
    if send2trash is not None:
        send2trash(str(path))
        return

    gio = shutil.which("gio")
    if gio:
        subprocess.run(
            [gio, "trash", str(path)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return

    raise OSError("No platform trash backend is available")


def tmp_root() -> Path:
    raw = os.environ.get("SANDBOX_TMP_ROOT")
    path = Path(raw).expanduser().resolve() if raw else DEFAULT_TMP_ROOT
    path.mkdir(parents=True, exist_ok=True)
    return path


def _is_link_or_reparse_point(path: Path, st: os.stat_result) -> bool:
    if stat.S_ISLNK(st.st_mode):
        return True
    attrs = getattr(st, "st_file_attributes", 0)
    return bool(attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _env_int(name: str, default: int, *, min_v: int, max_v: int) -> int:
    try:
        value = int(os.environ.get(name, default))
    except ValueError:
        value = default
    return max(min_v, min(max_v, value))


def _env_bytes(name: str, default: int) -> int:
    raw = os.environ.get(name, str(default))
    try:
        if raw.lower().endswith("m"):
            return int(float(raw[:-1]) * 1024 * 1024)
        if raw.lower().endswith("k"):
            return int(float(raw[:-1]) * 1024)
        return int(raw)
    except ValueError:
        return default


def max_file_bytes() -> int:
    return _env_bytes("SANDBOX_MAX_FILE_BYTES", DEFAULT_MAX_FILE_BYTES)


def max_output_total_bytes() -> int:
    return _env_bytes("SANDBOX_MAX_OUTPUT_TOTAL_BYTES", DEFAULT_MAX_OUTPUT_TOTAL_BYTES)


def max_files_per_list() -> int:
    return _env_int("SANDBOX_MAX_FILES_PER_LIST", DEFAULT_MAX_FILES_PER_LIST, min_v=1, max_v=50)


def max_shared_list_files() -> int:
    return _env_int("SANDBOX_MAX_SHARED_LIST_FILES", DEFAULT_MAX_SHARED_LIST_FILES, min_v=1, max_v=500)


def staging_ttl_seconds() -> int:
    return _env_int(
        "SANDBOX_STAGING_TTL_SECONDS",
        DEFAULT_STAGING_TTL_SECONDS,
        min_v=60,
        max_v=30 * 24 * 60 * 60,
    )


def artifacts_ttl_seconds() -> int:
    return _env_int(
        "SANDBOX_ARTIFACTS_TTL_SECONDS",
        DEFAULT_ARTIFACTS_TTL_SECONDS,
        min_v=60,
        max_v=30 * 24 * 60 * 60,
    )


def archive_ttl_seconds() -> int:
    return _env_int(
        "SANDBOX_ARCHIVE_TTL_SECONDS",
        DEFAULT_ARCHIVE_TTL_SECONDS,
        min_v=1,
        max_v=30 * 24 * 60 * 60,
    )


def archive_root() -> Path:
    raw = os.environ.get("SANDBOX_ARCHIVE_ROOT")
    path = Path(raw).expanduser().resolve() if raw else tmp_root() / "archive"
    path.mkdir(parents=True, exist_ok=True)
    return path


def shared_root() -> Path:
    raw = os.environ.get("SANDBOX_SHARED_ROOT")
    path = Path(raw).expanduser().resolve() if raw else DEFAULT_SHARED_ROOT
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    return path


def staging_root() -> Path:
    raw = os.environ.get("SANDBOX_STAGING_ROOT")
    path = Path(raw).expanduser().resolve() if raw else tmp_root() / "staging"
    path.mkdir(parents=True, exist_ok=True)
    return path


def artifacts_root() -> Path:
    raw = os.environ.get("SANDBOX_ARTIFACTS_ROOT")
    path = Path(raw).expanduser().resolve() if raw else tmp_root() / "artifacts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_filename(name: object) -> str:
    if not isinstance(name, str) or not name.strip():
        raise FileBridgeError("filename must be a non-empty string")
    if Path(name).name != name:
        raise FileBridgeError(
            f"invalid filename: {name!r} (use basename, chars: a-z A-Z 0-9 . _ -)"
        )
    base = Path(name).name
    if base in (".", "..") or not SAFE_NAME_RE.match(base):
        raise FileBridgeError(
            f"invalid filename: {name!r} (use basename, chars: a-z A-Z 0-9 . _ -)"
        )
    ext = Path(base).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise FileBridgeError(
            f"extension not allowed: {ext or '(none)'}; allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )
    return base


def validate_filename_list(names: object, *, label: str) -> list[str]:
    if names is None:
        return []
    if not isinstance(names, list):
        raise FileBridgeError(f"{label} must be an array of strings")
    if len(names) > max_files_per_list():
        raise FileBridgeError(f"{label}: at most {max_files_per_list()} files")
    return [safe_filename(n) for n in names]


def validate_session_id(session_id: object) -> str:
    if session_id is None:
        return uuid.uuid4().hex
    if not isinstance(session_id, str) or not re.fullmatch(r"[a-f0-9]{32}", session_id):
        raise FileBridgeError("session_id must be a 32-char hex string")
    return session_id


def validate_run_id(run_id: object) -> str:
    if not isinstance(run_id, str) or not re.fullmatch(r"[a-f0-9]{32}", run_id):
        raise FileBridgeError("run_id must be a 32-char hex string")
    return run_id


def session_dir(session_id: str) -> Path:
    path = staging_root() / session_id
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    return path


def upload_file(session_id: str | None, filename: str, content_base64: str) -> dict[str, str | int]:
    sid = validate_session_id(session_id)
    safe = safe_filename(filename)
    if not isinstance(content_base64, str):
        raise FileBridgeError("content_base64 must be a string")

    try:
        data = base64.b64decode(content_base64, validate=True)
    except Exception as exc:
        raise FileBridgeError(f"invalid base64: {exc}") from exc

    limit = max_file_bytes()
    if len(data) > limit:
        raise FileBridgeError(f"file too large: {len(data)} bytes (max {limit})")

    dest = session_dir(sid) / safe
    dest.write_bytes(data)
    os.chmod(dest, 0o600)
    return {"session_id": sid, "filename": safe, "size": len(data)}


def prepare_run_layout(run_dir: Path) -> tuple[Path, Path, Path]:
    input_dir = run_dir / "input"
    output_dir = run_dir / "output"
    work_dir = run_dir / "work"
    for d in (input_dir, output_dir, work_dir):
        d.mkdir(parents=True, exist_ok=True)
    os.chmod(input_dir, 0o500)
    os.chmod(output_dir, 0o700)
    os.chmod(work_dir, 0o700)
    return input_dir, output_dir, work_dir


def prepare_shared_layout(run_dir: Path | None = None) -> Path:
    return shared_root()


def normalize_shared_path(path: object) -> str:
    if not isinstance(path, str) or not path.strip():
        raise FileBridgeError("path must be a non-empty string")
    raw = path.replace("\\", "/").strip()
    if "\x00" in raw:
        raise FileBridgeError("path must not contain null bytes")
    if re.match(r"^[a-zA-Z]:/", raw):
        raise FileBridgeError("path must not be a Windows path")

    root = MODEL_SHARED_ROOT.rstrip("/")
    if raw == root:
        rel = "."
    elif raw.startswith(f"{root}/"):
        rel = raw[len(root) + 1 :]
    elif raw == SHARED_DIR_NAME:
        rel = "."
    elif raw.startswith(f"{SHARED_DIR_NAME}/"):
        rel = raw[len(SHARED_DIR_NAME) + 1 :]
    elif raw.startswith("/"):
        raise FileBridgeError(f"path must be inside {MODEL_SHARED_ROOT}")
    else:
        rel = raw

    rel = rel.strip("/") or "."
    normalized = Path(rel).as_posix()
    if normalized == ".":
        return "."
    if normalized.startswith("../") or normalized == ".." or "/../" in f"/{normalized}/":
        raise FileBridgeError("path must not escape _sandbox")
    return normalized


def resolve_shared_file(path: object) -> tuple[Path, str]:
    rel = normalize_shared_path(path)
    shared_dir = shared_root().resolve()
    candidate = shared_dir / rel
    if rel != ".":
        try:
            st = candidate.lstat()
        except FileNotFoundError:
            pass
        else:
            if not _is_link_or_reparse_point(candidate, st):
                try:
                    candidate.resolve(strict=True).relative_to(shared_dir)
                except (FileNotFoundError, ValueError) as exc:
                    raise FileBridgeError("path escapes _sandbox") from exc
    return candidate, rel


def describe_shared_file(path: object, filename: object | None = None) -> dict:
    full_path, rel = resolve_shared_file(path)
    shared_dir = shared_root().resolve()
    try:
        st = full_path.lstat()
    except FileNotFoundError as exc:
        raise FileBridgeError(f"shared file not found: {rel}") from exc
    if _is_link_or_reparse_point(full_path, st):
        raise FileBridgeError(f"shared file is a symlink: {rel}")
    if not stat.S_ISREG(st.st_mode):
        raise FileBridgeError(f"shared path is not a regular file: {rel}")
    try:
        resolved = full_path.resolve(strict=True)
    except FileNotFoundError as exc:
        raise FileBridgeError(f"shared file not found: {rel}") from exc
    try:
        resolved.relative_to(shared_dir)
    except ValueError as exc:
        raise FileBridgeError("shared file escapes _sandbox") from exc

    raw_filename = str(filename or "").strip()
    display_name = Path(raw_filename).name if raw_filename else full_path.name
    lower_name = (display_name or full_path.name).lower()
    if lower_name.endswith(".csv"):
        mime_type = "text/csv"
    elif lower_name.endswith(".tsv"):
        mime_type = "text/tab-separated-values"
    else:
        mime_type, _ = mimetypes.guess_type(display_name or full_path.name)
    return {
        "kind": "shared_file",
        "path": rel,
        "container_path": f"{MODEL_SHARED_ROOT}/{rel}" if rel != "." else MODEL_SHARED_ROOT,
        "host_path": str(resolved),
        "filename": display_name or "download",
        "mime_type": mime_type or "application/octet-stream",
        "size_bytes": st.st_size,
        "model_context": f"Shared file ready: {display_name or full_path.name}",
    }


def _shared_mime_type(name: str) -> str:
    lower_name = name.lower()
    if lower_name.endswith(".csv"):
        return "text/csv"
    if lower_name.endswith(".tsv"):
        return "text/tab-separated-values"
    mime_type, _ = mimetypes.guess_type(name)
    return mime_type or "application/octet-stream"


def list_shared_files(*, limit: int | None = None) -> dict[str, object]:
    root = shared_root().resolve()
    max_items = limit if limit is not None else max_shared_list_files()
    max_items = max(1, min(500, int(max_items)))
    files: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []
    truncated = False

    try:
        iterator = root.rglob("*")
        for path in iterator:
            try:
                rel = path.relative_to(root).as_posix()
            except ValueError:
                skipped.append({"path": str(path), "reason": "outside shared root"})
                continue
            try:
                st = path.lstat()
            except OSError as exc:
                skipped.append({"path": rel, "reason": f"stat failed: {exc.__class__.__name__}"})
                continue
            if _is_link_or_reparse_point(path, st):
                skipped.append({"path": rel, "reason": "symlink/reparse point"})
                continue
            if stat.S_ISDIR(st.st_mode):
                continue
            if not stat.S_ISREG(st.st_mode):
                skipped.append({"path": rel, "reason": "not a regular file"})
                continue
            try:
                resolved = path.resolve(strict=True)
                resolved.relative_to(root)
            except (OSError, ValueError) as exc:
                skipped.append({"path": rel, "reason": f"resolve failed: {exc.__class__.__name__}"})
                continue
            if len(files) >= max_items:
                truncated = True
                continue
            files.append(
                {
                    "kind": "shared_file",
                    "path": rel,
                    "container_path": f"{MODEL_SHARED_ROOT}/{rel}",
                    "host_path": str(resolved),
                    "filename": path.name,
                    "mime_type": _shared_mime_type(path.name),
                    "size_bytes": st.st_size,
                    "mtime": st.st_mtime,
                }
            )
    except OSError as exc:
        skipped.append({"path": ".", "reason": f"scan failed: {exc.__class__.__name__}"})

    files.sort(key=lambda item: str(item["path"]))
    skipped.sort(key=lambda item: str(item["path"]))
    return {
        "kind": "shared_file_list",
        "root": str(root),
        "container_root": MODEL_SHARED_ROOT,
        "files": files,
        "skipped": skipped,
        "truncated": truncated,
        "limit": max_items,
    }


def shared_file_snapshot() -> dict[str, float]:
    listing = list_shared_files(limit=500)
    snapshot: dict[str, float] = {}
    for item in listing["files"]:
        if isinstance(item, dict) and isinstance(item.get("path"), str):
            try:
                snapshot[item["path"]] = float(item.get("mtime", 0.0))
            except (TypeError, ValueError):
                snapshot[item["path"]] = 0.0
    return snapshot


def format_shared_file_changes(before: dict[str, float], after_listing: dict[str, object]) -> str:
    changed: list[str] = []
    for item in after_listing.get("files", []):
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        mtime = item.get("mtime")
        if not isinstance(path, str):
            continue
        try:
            current_mtime = float(mtime)
        except (TypeError, ValueError):
            current_mtime = 0.0
        if path not in before or current_mtime > before[path] + 1e-6:
            changed.append(path)
    if not changed:
        return ""
    visible = changed[:10]
    suffix = "" if len(changed) <= 10 else f" (+{len(changed) - 10} more)"
    return (
        "shared_files_changed: "
        + ", ".join(visible)
        + suffix
        + "\nshare_hint: call oda_share_file with one of these paths to present it to the user"
    )


def stage_input_files(
    run_dir: Path,
    session_id: str,
    names: list[str],
) -> list[str]:
    if not names:
        return []
    input_dir = run_dir / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(input_dir, 0o700)
    staged: list[str] = []
    src_root = session_dir(session_id)
    for name in names:
        src = src_root / name
        if not src.is_file():
            raise FileBridgeError(f"staged input missing: {name} (session {session_id})")
        if src.stat().st_size > max_file_bytes():
            raise FileBridgeError(f"staged input too large: {name}")
        dest = input_dir / name
        if dest.exists():
            os.chmod(dest, 0o600)
            dest.unlink()
        shutil.copy2(src, dest)
        os.chmod(dest, 0o400)
        staged.append(name)
    os.chmod(input_dir, 0o500)
    return staged


def collect_output_files(run_dir: Path, names: list[str]) -> dict[str, bytes]:
    if not names:
        return {}
    output_dir = run_dir / "output"
    result: dict[str, bytes] = {}
    total = 0
    limit_total = max_output_total_bytes()
    per_file = max_file_bytes()

    for name in names:
        path = output_dir / name
        try:
            st = path.lstat()
        except FileNotFoundError:
            raise FileBridgeError(f"output file not produced: {name}")
        if _is_link_or_reparse_point(path, st):
            raise FileBridgeError(f"output file is a symlink: {name}")
        if not stat.S_ISREG(st.st_mode):
            raise FileBridgeError(f"output path is not a regular file: {name}")
        resolved = path.resolve(strict=True)
        try:
            resolved.relative_to(output_dir.resolve(strict=True))
        except ValueError as exc:
            raise FileBridgeError(f"output path escapes output directory: {name}") from exc
        size = st.st_size
        if size > per_file:
            raise FileBridgeError(f"output file too large: {name} ({size} bytes)")
        total += size
        if total > limit_total:
            raise FileBridgeError(f"total output size exceeds {limit_total} bytes")
        result[name] = path.read_bytes()
    return result


def save_artifacts(
    run_id: str,
    *,
    exit_code: int,
    session_id: str | None,
    inputs: list[str],
    outputs: dict[str, bytes],
    stdout: str,
    stderr: str,
    timed_out: bool,
) -> None:
    root = artifacts_root() / run_id
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o700)

    out_dir = root / "output"
    out_dir.mkdir(exist_ok=True)
    for name, data in outputs.items():
        (out_dir / name).write_bytes(data)
        os.chmod(out_dir / name, 0o600)

    manifest = {
        "run_id": run_id,
        "exit_code": exit_code,
        "session_id": session_id,
        "input_files": inputs,
        "output_files": list(outputs.keys()),
        "timed_out": timed_out,
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (root / "stdout.txt").write_text(stdout, encoding="utf-8", errors="replace")
    (root / "stderr.txt").write_text(stderr, encoding="utf-8", errors="replace")


def read_output_file(run_id: str, filename: str) -> tuple[bytes, dict]:
    rid = validate_run_id(run_id)
    safe = safe_filename(filename)
    root = artifacts_root() / rid
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise FileBridgeError(f"unknown run_id: {rid}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if safe not in manifest.get("output_files", []):
        raise FileBridgeError(f"file not declared in run outputs: {safe}")

    path = root / "output" / safe
    try:
        st = path.lstat()
    except FileNotFoundError:
        raise FileBridgeError(f"artifact missing on host: {safe}")
    if _is_link_or_reparse_point(path, st):
        raise FileBridgeError(f"artifact is a symlink: {safe}")
    if not stat.S_ISREG(st.st_mode):
        raise FileBridgeError(f"artifact is not a regular file: {safe}")

    return path.read_bytes(), manifest


def format_file_bridge_summary(
    *,
    run_id: str,
    session_id: str | None,
    inputs: list[str],
    outputs: list[str],
) -> str:
    lines = [
        f"run_id: {run_id}",
    ]
    if session_id:
        lines.append(f"session_id: {session_id}")
    if inputs:
        lines.append(f"input_files: {', '.join(inputs)}")
    if outputs:
        lines.append(f"output_files: {', '.join(outputs)}")
        lines.append("fetch: use sandbox_download with run_id and filename")
    return "\n".join(lines)


def cleanup_artifacts(run_id: str) -> None:
    try:
        send_to_trash(artifacts_root() / validate_run_id(run_id))
    except OSError:
        pass


def cleanup_old_uuid_dirs(root: Path, ttl_seconds: int) -> int:
    now = time.time()
    removed = 0
    if not root.exists():
        return 0
    for child in root.iterdir():
        if not child.is_dir() or not re.fullmatch(r"[a-f0-9]{32}", child.name):
            continue
        try:
            age = now - child.stat().st_mtime
        except OSError:
            continue
        if age < ttl_seconds:
            continue
        try:
            send_to_trash(child)
        except OSError:
            continue
        removed += 1
    return removed


def cleanup_old_archives(root: Path, ttl_seconds: int) -> int:
    now = time.time()
    removed = 0
    if not root.exists():
        return 0
    for child in root.rglob("*.zip"):
        try:
            age = now - child.stat().st_mtime
        except OSError:
            continue
        if age < ttl_seconds:
            continue
        try:
            send_to_trash(child)
        except OSError:
            continue
        removed += 1
    return removed


def archive_tree(source: Path, category: str, name: str | None = None) -> Path | None:
    if not source.exists() or not source.is_dir():
        return None
    safe_category = re.sub(r"[^a-zA-Z0-9._-]+", "-", category).strip(".-") or "misc"
    safe_name = re.sub(r"[^a-zA-Z0-9._-]+", "-", name or source.name).strip(".-") or source.name
    dest_dir = archive_root() / safe_category
    dest_dir.mkdir(parents=True, exist_ok=True)
    archive_path = dest_dir / f"{int(time.time())}-{safe_name}.zip"

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in source.rglob("*"):
            try:
                st = path.lstat()
            except OSError:
                continue
            rel = path.relative_to(source).as_posix()
            if _is_link_or_reparse_point(path, st):
                zf.writestr(f"{rel}.skipped.txt", "Skipped symlink/reparse point during archive.\n")
                continue
            if path.is_dir():
                continue
            if not stat.S_ISREG(st.st_mode):
                continue
            try:
                zf.write(path, rel)
            except OSError:
                continue
    return archive_path


def cleanup_file_bridge() -> int:
    return (
        cleanup_old_uuid_dirs(staging_root(), staging_ttl_seconds())
        + cleanup_old_uuid_dirs(artifacts_root(), artifacts_ttl_seconds())
        + cleanup_old_archives(archive_root(), archive_ttl_seconds())
    )
