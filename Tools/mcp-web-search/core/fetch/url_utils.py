# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from urllib.parse import parse_qsl, urlparse, urlunparse, urlencode

_TRACKING_PARAMS = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "fbclid", "gclid", "msclkid", "mc_cid", "mc_eid",
    "ref", "referrer", "source", "_ga", "yclid", "ysclid",
})

def normalize_url(url: str) -> str:
    try:
        p = urlparse(url)
        clean_qs = urlencode([(k, v) for k, v in parse_qsl(p.query) if k.lower() not in _TRACKING_PARAMS])
        return urlunparse((
            p.scheme.lower(), p.netloc.lower(),
            p.path.rstrip("/") or "/", p.params, clean_qs, "",
        ))
    except Exception:
        return url


_NON_TEXT_EXTS = frozenset({
    # Images
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".bmp", ".tif", ".tiff",
    ".ico", ".svg", ".heic", ".heif",
    # Video
    ".mp4", ".m4v", ".mov", ".avi", ".mkv", ".webm", ".wmv", ".flv", ".mpeg", ".mpg",
    # Audio
    ".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".oga", ".opus", ".wma",
    # Archives / compressed blobs
    ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".tgz", ".zst",
    # Office / ebook / database / binaries. PDF is intentionally excluded:
    # the research pipeline routes PDFs to a text extractor.
    ".csv", ".tsv", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods", ".odp",
    ".rtf", ".epub", ".sqlite", ".db", ".exe", ".dmg", ".msi", ".bin", ".dll", ".so",
})

_NON_TEXT_CONTENT_PREFIXES = (
    "image/",
    "video/",
    "audio/",
    "font/",
)

_NON_TEXT_CONTENT_TYPES = frozenset({
    "application/zip",
    "application/x-zip-compressed",
    "application/x-rar-compressed",
    "application/x-7z-compressed",
    "application/x-tar",
    "application/gzip",
    "application/x-gzip",
    "application/x-bzip2",
    "application/x-xz",
    "application/zstd",
    "application/octet-stream",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/epub+zip",
    "application/x-sqlite3",
})


def has_non_text_extension(url: str) -> bool:
    """Return True when URL path points to a non-text binary/media asset."""
    try:
        path = urlparse(url).path.lower()
    except Exception:
        path = url.lower().split("?", 1)[0]
    return any(path.endswith(ext) for ext in _NON_TEXT_EXTS)


def is_non_text_content_type(content_type: str) -> bool:
    """Return True for content types that should not enter text extraction."""
    ctype = (content_type or "").split(";", 1)[0].strip().lower()
    if not ctype:
        return False
    if ctype == "application/pdf":
        return False
    if any(ctype.startswith(prefix) for prefix in _NON_TEXT_CONTENT_PREFIXES):
        return True
    return ctype in _NON_TEXT_CONTENT_TYPES
