# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlparse


# Extension policy tables.
ALLOWED_EXTENSIONS: dict[str, list[str]] = {
    "text": [".pdf", ".docx", ".xlsx", ".csv", ".txt", ".md", ".json", ".xml", ".html"],
    "media": [".mp3", ".mp4", ".wav", ".webm", ".mkv", ".jpg", ".jpeg", ".png", ".gif", ".webp"],
    "archive": [".zip", ".tar", ".gz", ".tar.gz", ".7z"],
    "data": [".sqlite", ".db"],
}

BLOCKED_EXTENSIONS: list[str] = [
    ".exe",
    ".dll",
    ".bat",
    ".sh",
    ".ps1",
    ".msi",
    ".bin",
    ".py",
    ".js",
    ".vbs",
    ".cmd",
    ".so",
    ".dylib",
]


# MIME type category mappings.
_MIME_CATEGORY: dict[str, str] = {
    "application/pdf": "text",
    "application/msword": "text",
    "application/vnd.openxmlformats": "text",
    "application/json": "text",
    "application/xml": "text",
    "text/": "text",
    "audio/": "media",
    "video/": "media",
    "image/": "media",
    "application/zip": "archive",
    "application/x-tar": "archive",
    "application/gzip": "archive",
    "application/x-7z-compressed": "archive",
    "application/x-sqlite3": "data",
}

_MIME_TO_EXT: dict[str, str] = {
    "application/pdf": ".pdf",
    "application/msword": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/json": ".json",
    "application/xml": ".xml",
    "application/zip": ".zip",
    "application/gzip": ".gz",
    "application/x-tar": ".tar",
    "application/x-7z-compressed": ".7z",
    "application/x-sqlite3": ".sqlite",
    "text/csv": ".csv",
    "text/plain": ".txt",
    "text/markdown": ".md",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "audio/webm": ".webm",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/x-matroska": ".mkv",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
}

_ALL_KNOWN_EXTS: set[str] = {
    ext for extensions in ALLOWED_EXTENSIONS.values() for ext in extensions
} | set(BLOCKED_EXTENSIONS)


# Filename parsing helpers.
def _extract_extension(filename: str) -> str:
    """Return the lowercase extension, including compound archive suffixes."""

    name = filename.lower()
    for compound in (".tar.gz", ".tar.bz2", ".tar.xz"):
        if name.endswith(compound):
            return compound

    return Path(name).suffix

# Filename parsing helpers.
def _is_known_extension(ext: str) -> bool:
    """Return whether the extension is present in the allowlist or blocklist."""

    return ext in _ALL_KNOWN_EXTS

# Filename parsing helpers.
def _filename_from_content_disposition(content_disposition: str) -> str | None:
    """Extract a filename from a Content-Disposition header value."""

    for part in content_disposition.split(";"):
        part = part.strip()
        if part.lower().startswith("filename*="):
            # RFC 5987 format: filename*=UTF-8''name.ext
            value = part.split("=", 1)[1].strip().strip("'\"")
            if "''" in value:
                value = value.split("''", 1)[1]
            return unquote(value)
        if part.lower().startswith("filename="):
            return part.split("=", 1)[1].strip().strip('"\'')

    return None


# Workspace path helpers.
def _resolve_save_path(project_dir: Path, save_to: str, filename: str) -> Path:
    """Resolve an absolute destination path inside the task workspace."""

    workspace_root = project_dir.parent.parent
    task_root = workspace_root / "task"

    # Normalize separators and reject any path traversal attempt before resolving.
    save_to_clean = save_to.replace("\\", "/").strip("/")
    if ".." in save_to_clean.split("/"):
        raise ValueError(f"Path traversal detected in save_to: '{save_to}'")

    dest = (task_root / save_to_clean / filename).resolve()
    if not dest.is_relative_to(task_root.resolve()):
        raise ValueError(f"Resolved path escapes task directory: '{dest}'")

    return dest


# Content-type helpers.
def _content_type_category(content_type: str) -> str | None:
    """Map a Content-Type header value to an allowed-types category."""

    content_type_lower = content_type.lower().split(";")[0].strip()
    for prefix, category in _MIME_CATEGORY.items():
        if content_type_lower.startswith(prefix):
            return category

    return None


# Download workflow.
async def download_file(
    url: str,
    project_dir: Path,
    save_to: str = "downloads/",
    allowed_types: list[str] | None = None,
    max_size_mb: int = 200,
) -> dict:
    """Download a file from the web and save it to the task workspace."""

    import httpx

    max_bytes = max_size_mb * 1024 * 1024

    # Validate the URL before any network traffic.
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return {
            "status": "error",
            "message": f"URL scheme '{parsed.scheme}' not allowed. Use http or https.",
        }

    # Start with the filename inferred from the URL path.
    url_path = unquote(parsed.path)
    url_filename = PurePosixPath(url_path).name or "download"
    ext = _extract_extension(url_filename)

    if ext in BLOCKED_EXTENSIONS:
        return {
            "status": "error",
            "message": f"Extension '{ext}' is blocked for security reasons.",
        }

    # When the URL already exposes a known extension, validate it early.
    ext_known = _is_known_extension(ext)
    if ext_known and ext and allowed_types is not None:
        permitted_exts: set[str] = set()
        for category in allowed_types:
            permitted_exts.update(ALLOWED_EXTENSIONS.get(category, []))
        if ext not in permitted_exts:
            return {
                "status": "error",
                "message": f"Extension '{ext}' not permitted. Allowed types: {allowed_types}.",
            }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    content_type = "application/octet-stream"

    # Use HEAD to fail fast on size or obvious content-type mismatches when possible.
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
            head_response = await client.head(url, headers=headers)
            if head_response.status_code not in (405, 501):
                head_response.raise_for_status()

                content_type_header = head_response.headers.get("content-type", "")
                if content_type_header:
                    content_type = content_type_header.split(";")[0].strip()

                content_length_header = head_response.headers.get("content-length")
                if content_length_header:
                    content_length = int(content_length_header)
                    if content_length > max_bytes:
                        return {
                            "status": "error",
                            "message": (
                                f"File too large: {content_length / (1024 * 1024):.1f} MB "
                                f"exceeds limit of {max_size_mb} MB."
                            ),
                        }
    except httpx.HTTPStatusError as error:
        if error.response.status_code not in (405, 501):
            return {"status": "error", "message": f"HEAD request failed: {error}"}
    except Exception:
        # Some servers reject HEAD or provide misleading metadata, so continue with GET.
        pass

    bytes_written = 0
    filename = url_filename
    dest_path: Path | None = None

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            async with client.stream("GET", url, headers=headers) as response:
                response.raise_for_status()

                # Re-check the response headers on the actual download request.
                content_type_get = response.headers.get("content-type", "")
                if content_type_get:
                    content_type = content_type_get.split(";")[0].strip()

                content_disposition = response.headers.get("content-disposition", "")
                if content_disposition:
                    content_disposition_name = _filename_from_content_disposition(content_disposition)
                    if content_disposition_name:
                        filename = content_disposition_name
                        ext = _extract_extension(filename)

                # If the URL had no extension, derive one from the MIME type when possible.
                if not ext:
                    mime_ext = _MIME_TO_EXT.get(content_type.lower())
                    if mime_ext:
                        filename = filename + mime_ext
                        ext = mime_ext
                        ext_known = True

                # Extension-less URLs must be validated by the resolved content type instead.
                if allowed_types is not None and not ext_known:
                    content_category = _content_type_category(content_type)
                    if content_category not in allowed_types:
                        return {
                            "status": "error",
                            "message": (
                                f"Content-Type '{content_type}' (category: {content_category!r}) "
                                f"not in allowed types: {allowed_types}."
                            ),
                        }

                if content_type.startswith("text/html"):
                    return {
                        "status": "error",
                        "message": "Server returned text/html, likely an antibot page, not the requested file.",
                    }

                content_length_get = response.headers.get("content-length")
                if content_length_get and int(content_length_get) > max_bytes:
                    return {
                        "status": "error",
                        "message": (
                            f"File too large: {int(content_length_get) / (1024 * 1024):.1f} MB "
                            f"exceeds limit of {max_size_mb} MB."
                        ),
                    }

                try:
                    dest_path = _resolve_save_path(project_dir, save_to, filename)
                except ValueError as error:
                    return {"status": "error", "message": str(error)}

                dest_path.parent.mkdir(parents=True, exist_ok=True)
                abort_reason: str | None = None

                # Delete only after the handle is closed to stay compatible with Windows.
                with open(dest_path, "wb") as file_obj:
                    first_chunk = True
                    async for chunk in response.aiter_bytes(chunk_size=65536):
                        if first_chunk:
                            first_chunk = False
                            if len(chunk) >= 5 and chunk[:5].lower().startswith(b"<!doc"):
                                abort_reason = "html"
                                break

                        bytes_written += len(chunk)
                        if bytes_written > max_bytes:
                            abort_reason = "size"
                            break

                        file_obj.write(chunk)

                if abort_reason:
                    dest_path.unlink(missing_ok=True)
                    if abort_reason == "html":
                        return {
                            "status": "error",
                            "message": "Response starts with HTML, likely an antibot or redirect page.",
                        }
                    return {
                        "status": "error",
                        "message": (
                            f"Download aborted: file exceeds {max_size_mb} MB limit "
                            f"({bytes_written / (1024 * 1024):.1f} MB received so far)."
                        ),
                    }
    except httpx.HTTPStatusError as error:
        return {"status": "error", "message": f"HTTP {error.response.status_code}: {error}"}
    except Exception as error:
        return {"status": "error", "message": f"Download failed: {error}"}

    workspace_root = project_dir.parent.parent
    task_root = workspace_root / "task"
    rel_path = dest_path.relative_to(task_root.resolve()).as_posix()

    return {
        "status": "ok",
        "file": rel_path,
        "size_bytes": bytes_written,
        "content_type": content_type,
        "message": f"File saved to task/{rel_path}",
    }
