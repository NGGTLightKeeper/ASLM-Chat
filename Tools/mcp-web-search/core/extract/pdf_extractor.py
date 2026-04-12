# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""PDF text extraction helpers.

The fetch layer sometimes receives application/pdf content from URLs that do
not end with ".pdf" (for example arxiv.org/pdf/<id>). This module turns those
bytes into bounded markdown and deletes the temporary file after parsing.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from urllib.parse import urlparse


MAX_PDF_BYTES = 10 * 1024 * 1024
MAX_PDF_TEXT_CHARS = 80_000

_BLANK_LINES_RE = re.compile(r"\n{3,}")
_PDF_DUMP_MARKERS = (
    "%PDF-",
    "endobj",
    "/FlateDecode",
    "xref",
    "startxref",
)


def looks_like_pdf_url(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.lower()
    if path.endswith(".pdf"):
        return True
    if parsed.netloc.lower().endswith("arxiv.org") and path.startswith("/pdf/"):
        return True
    if "format=pdf" in parsed.query.lower():
        return True
    return False


def looks_like_pdf_bytes(data: bytes) -> bool:
    return data.lstrip().startswith(b"%PDF-")


def looks_like_pdf_text_dump(text: str) -> bool:
    """Return True for PDF object streams decoded as text."""
    if not text:
        return False
    head = text.lstrip()[:12000]
    if head.startswith("%PDF-"):
        return True
    marker_count = sum(1 for marker in _PDF_DUMP_MARKERS if marker in head)
    return marker_count >= 3


def looks_like_decoded_binary(text: str) -> bool:
    """Detect arbitrary binary payloads that were decoded as text."""
    if looks_like_pdf_text_dump(text):
        return True
    sample = text[:12000]
    if not sample:
        return False
    printable_controls = {"\t", "\n", "\r"}
    control_count = sum(1 for ch in sample if ord(ch) < 32 and ch not in printable_controls)
    replacement_count = sample.count("\ufffd")
    length = max(1, len(sample))
    return control_count / length > 0.005 or replacement_count / length > 0.01


def pdf_bytes_to_markdown(
    *,
    url: str,
    data: bytes,
    title: str = "",
    max_chars: int = MAX_PDF_TEXT_CHARS,
) -> str:
    """Extract PDF bytes into a bounded markdown document."""
    if not data:
        return ""
    if len(data) > MAX_PDF_BYTES:
        return ""
    if not looks_like_pdf_bytes(data):
        return ""

    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as handle:
            handle.write(data)
            tmp_path = Path(handle.name)
        return pdf_file_to_markdown(url=url, path=tmp_path, title=title, max_chars=max_chars)
    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass


def pdf_file_to_markdown(
    *,
    url: str,
    path: Path,
    title: str = "",
    max_chars: int = MAX_PDF_TEXT_CHARS,
) -> str:
    """Extract a local PDF file into a bounded markdown document."""
    import fitz  # PyMuPDF

    text_parts: list[str] = []
    doc = fitz.open(str(path))
    try:
        meta = doc.metadata or {}
        title = (title or str(meta.get("title") or "")).strip() or "PDF Document"
        for index, page in enumerate(doc, 1):
            page_text = (page.get_text("text") or "").strip()
            if not page_text:
                continue
            text_parts.append(f"\n\n## Page {index}\n\n{page_text}")
            if sum(len(part) for part in text_parts) >= max_chars:
                break
    finally:
        doc.close()

    body = "\n".join(text_parts).strip()
    if not body:
        return ""
    if len(body) > max_chars:
        body = body[:max_chars].rsplit("\n", 1)[0].rstrip() + "\n\n[...truncated]"

    site = urlparse(url).netloc.removeprefix("www.")
    markdown = (
        f"# {title}\n\n"
        f"**Site:** {site}\n"
        f"**URL:** {url}\n"
        "**Source type:** PDF\n\n"
        "---\n\n"
        f"{body}"
    )
    return _BLANK_LINES_RE.sub("\n\n", markdown).strip()
