# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlparse


# File-type policy used by read_page to explain when a URL points to a file
# rather than to a normal HTML page.
ALLOWED_EXTENSIONS: dict[str, list[str]] = {
    "text": [".pdf", ".docx", ".xlsx", ".csv", ".txt", ".md", ".json", ".xml", ".html"],
    "media": [".mp3", ".mp4", ".wav", ".webm", ".mkv", ".jpg", ".jpeg", ".png", ".gif", ".webp"],
    "archive": [".zip", ".tar", ".gz", ".tar.gz", ".7z"],
    "data": [".sqlite", ".db"],
    "code": [
        ".py", ".js", ".mjs", ".cjs", ".ts", ".jsx", ".tsx",
        ".css", ".scss", ".sass", ".rb", ".php", ".lua",
    ],
}

BLOCKED_EXTENSIONS: list[str] = [
    ".exe",
    ".dll",
    ".bat",
    ".sh",
    ".ps1",
    ".msi",
    ".bin",
    ".vbs",
    ".cmd",
    ".so",
    ".dylib",
]


def _extract_extension(filename: str) -> str:
    """Return the lowercase extension, including compound archive suffixes."""

    name = filename.lower()
    for compound in (".tar.gz", ".tar.bz2", ".tar.xz"):
        if name.endswith(compound):
            return compound
    return Path(name).suffix


def get_download_info(url: str) -> tuple[str, str] | None:
    """Return (extension, category) if *url* points to a known downloadable file."""

    try:
        path = unquote(urlparse(url).path)
        filename = PurePosixPath(path).name or ""
    except Exception:
        return None

    ext = _extract_extension(filename)
    if not ext or ext in BLOCKED_EXTENSIONS:
        return None

    for category, exts in ALLOWED_EXTENSIONS.items():
        if ext in exts:
            return ext, category

    return None


__all__ = ["ALLOWED_EXTENSIONS", "BLOCKED_EXTENSIONS", "get_download_info"]
