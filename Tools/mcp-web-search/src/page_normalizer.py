"""
Page normalizer: turns raw HTML (or fallback text) into a clean,
structured markdown document.  Pure CPU heuristics — no models, no VRAM.

Public API
----------
normalize_page(url, raw_html, fallback_text) -> str   # markdown
"""

from __future__ import annotations

import html as html_lib
import re
from typing import Optional
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Optional dependency probes
# ---------------------------------------------------------------------------
try:
    import trafilatura  # type: ignore

    _HAS_TRAFILATURA = True
except Exception:
    _HAS_TRAFILATURA = False

try:
    from bs4 import BeautifulSoup  # type: ignore

    _HAS_BS4 = True
except Exception:
    _HAS_BS4 = False

# ---------------------------------------------------------------------------
# Reuse helpers from content_processor (same package)
# ---------------------------------------------------------------------------
try:
    from content_processor import (
        _preclean_html,
        _extract_text_with_bs4,
        _regex_html_to_text,
        _normalize_text,
        _dedupe_blocks,
        _get_boilerplate_filter,
    )
except ImportError:
    from .content_processor import (  # type: ignore
        _preclean_html,
        _extract_text_with_bs4,
        _regex_html_to_text,
        _normalize_text,
        _dedupe_blocks,
        _get_boilerplate_filter,
    )

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_MAX_OUTPUT_CHARS = 50_000
_WHITESPACE_RE = re.compile(r"[ \t\r\f\v]+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")
_TAG_RE = re.compile(r"<[^>]+>")
# Matches method tags prepended by _process_single: [OVERDRIVE], [PREVIEW_BOT], etc.
_METHOD_TAG_RE = re.compile(r"^\[[\w_]+\]\s*", re.MULTILINE)

# Patterns that indicate a line is a markdown-style heading
_MD_HEADING_RE = re.compile(r"^#{1,6}\s")
# Patterns for list items
_MD_LIST_RE = re.compile(r"^(\s*[-*•]\s|\s*\d+[.)]\s)")
# Patterns for blockquotes
_MD_QUOTE_RE = re.compile(r"^>\s?")
# Patterns for code fences
_MD_CODE_FENCE_RE = re.compile(r"^```")

# ---------------------------------------------------------------------------
# Fallback text pre-processing
# ---------------------------------------------------------------------------

def _strip_process_single_headers(text: str) -> str:
    """
    Strip the "Source: <url>" line and method tags like [OVERDRIVE] that
    _process_single prepends to the text before returning it.
    """
    t = text.lstrip()
    # Remove "Source: <url>" first line
    if t.lower().startswith("source:"):
        lines = t.split("\n", 1)
        t = lines[1].lstrip() if len(lines) > 1 else ""
    # Remove optional API line "API: <url>"
    if t.lower().startswith("api:"):
        lines = t.split("\n", 1)
        t = lines[1].lstrip() if len(lines) > 1 else ""
    # Remove method tag [OVERDRIVE] / [PREVIEW_BOT] on its own line
    t = _METHOD_TAG_RE.sub("", t, count=1).lstrip()
    return t


# ---------------------------------------------------------------------------
# Meta extraction
# ---------------------------------------------------------------------------

def _extract_meta_trafilatura(raw_html: str) -> dict[str, str]:
    """Extract metadata using trafilatura (CPU only)."""
    meta: dict[str, str] = {}
    try:
        obj = trafilatura.extract_metadata(raw_html)
        if obj is None:
            return meta
        if getattr(obj, "title", None):
            meta["title"] = str(obj.title).strip()
        if getattr(obj, "author", None):
            meta["author"] = str(obj.author).strip()
        if getattr(obj, "date", None):
            meta["date"] = str(obj.date).strip()
    except Exception:
        pass
    return meta


def _extract_meta_fallback(raw_html: str) -> dict[str, str]:
    """Extract metadata from HTML using regex / bs4 when trafilatura is unavailable."""
    meta: dict[str, str] = {}

    # Title
    m = re.search(r"<title[^>]*>(.*?)</title>", raw_html, re.IGNORECASE | re.DOTALL)
    if m:
        meta["title"] = _normalize_text(m.group(1))

    # Author
    m = re.search(
        r'<meta[^>]+name=["\']author["\'][^>]+content=["\'](.*?)["\']',
        raw_html,
        re.IGNORECASE,
    )
    if m:
        meta["author"] = _normalize_text(m.group(1))

    # Date — try multiple meta variants
    for pattern in (
        r'<meta[^>]+property=["\']article:published_time["\'][^>]+content=["\'](.*?)["\']',
        r'<meta[^>]+name=["\']date["\'][^>]+content=["\'](.*?)["\']',
        r'<meta[^>]+name=["\']publish[_-]?date["\'][^>]+content=["\'](.*?)["\']',
        r'<time[^>]+datetime=["\'](.*?)["\']',
    ):
        m = re.search(pattern, raw_html, re.IGNORECASE)
        if m:
            meta["date"] = _normalize_text(m.group(1))
            break

    return meta


def _extract_meta(raw_html: Optional[str], fallback_text: Optional[str], url: str) -> dict[str, str]:
    """Build a meta dict from whatever sources are available."""
    meta: dict[str, str] = {}

    if raw_html:
        if _HAS_TRAFILATURA:
            meta = _extract_meta_trafilatura(raw_html)
        if not meta.get("title"):
            fb = _extract_meta_fallback(raw_html)
            meta = {**fb, **{k: v for k, v in meta.items() if v}}

    # Infer title from first line of text when nothing else worked
    if not meta.get("title") and fallback_text:
        body = _strip_process_single_headers(fallback_text)
        first_line = body.split("\n", 1)[0].strip()
        if len(first_line) < 150 and first_line and not first_line.endswith("."):
            meta["title"] = first_line

    parsed = urlparse(url)
    meta["site"] = parsed.netloc.removeprefix("www.")
    meta["url"] = url
    return meta


# ---------------------------------------------------------------------------
# Content extraction (structured, with markdown formatting)
# ---------------------------------------------------------------------------

def _extract_with_trafilatura_formatted(cleaned_html: str, url: str = "") -> str:
    """Use trafilatura with include_formatting=True for markdown-like output."""
    if not cleaned_html:
        return ""
    try:
        text = trafilatura.extract(
            cleaned_html,
            url=url or None,
            include_comments=False,
            include_tables=True,
            include_formatting=True,
            include_links=False,
            favor_precision=True,
            deduplicate=True,
            output_format="txt",
        )
    except Exception:
        return ""
    return text or ""


def _extract_content(raw_html: Optional[str], fallback_text: Optional[str], url: str) -> str:
    """
    Extract and return the main textual content.
    Tries the best available method; always returns *something*.
    """
    # --- Path A: we have raw HTML ---
    if raw_html:
        cleaned_html = _preclean_html(raw_html)
        min_chars = 200

        # 1) trafilatura with formatting
        if _HAS_TRAFILATURA:
            text = _extract_with_trafilatura_formatted(cleaned_html, url)
            if len(_normalize_text(text)) >= min_chars:
                return text

        # 2) bs4 block extraction
        if _HAS_BS4:
            text = _extract_text_with_bs4(cleaned_html)
            if len(_normalize_text(text)) >= min_chars:
                return text

        # 3) regex fallback
        text = _regex_html_to_text(cleaned_html or raw_html)
        if text.strip():
            return text

    # --- Path B: work from fallback text ---
    if fallback_text:
        text = _strip_process_single_headers(fallback_text)
        return text.strip()

    return ""


# ---------------------------------------------------------------------------
# Post-cleaning: structure-preserving block processing
# ---------------------------------------------------------------------------

def _split_blocks_structured(text: str) -> list[str]:
    """
    Split text into blocks by double-newlines, but preserve markdown
    structure (headings, lists, quotes, code fences).
    """
    pieces = re.split(r"\n\s*\n", text or "")
    blocks: list[str] = []
    for piece in pieces:
        stripped = piece.strip()
        if not stripped:
            continue
        # Keep markdown-structured blocks as-is (don't normalize away their prefixes)
        if (_MD_HEADING_RE.match(stripped)
                or _MD_LIST_RE.match(stripped)
                or _MD_QUOTE_RE.match(stripped)
                or _MD_CODE_FENCE_RE.match(stripped)):
            blocks.append(stripped)
        else:
            # Regular text: normalize whitespace within the block
            normalized = _WHITESPACE_RE.sub(" ", html_lib.unescape(stripped).replace("\u00a0", " ")).strip()
            if normalized:
                blocks.append(normalized)
    return blocks


def _is_structured_block(block: str) -> bool:
    """Return True if block starts with a markdown structural prefix."""
    return bool(
        _MD_HEADING_RE.match(block)
        or _MD_LIST_RE.match(block)
        or _MD_QUOTE_RE.match(block)
        or _MD_CODE_FENCE_RE.match(block)
    )


def _clean_content(text: str, strict: bool = True) -> str:
    """
    Clean and deduplicate blocks while preserving markdown structure.

    strict=True  (default, from HTML extraction): apply full boilerplate filter
                 including the minimum-length check (~40 chars).
    strict=False (fallback text): only filter noise-marker blocks; keep short
                 content blocks since they may be legitimate short paragraphs.
    """
    is_boilerplate = _get_boilerplate_filter()
    blocks = _split_blocks_structured(text)

    filtered: list[str] = []
    for block in blocks:
        # Never filter structural blocks (headings, lists, quotes, code)
        if _is_structured_block(block):
            filtered.append(block)
            continue
        if strict:
            if not is_boilerplate(block):
                filtered.append(block)
        else:
            # Lenient: only drop obvious noise-marker blocks, not short-but-real ones
            compact = _normalize_text(block).lower()
            if not any(m in compact for m in (
                "cookie", "consent", "gdpr", "newsletter", "subscribe",
                "sign up", "advert", "sponsored", "all rights reserved",
                "accept all", "privacy policy", "terms of service",
            )):
                filtered.append(block)

    deduped = _dedupe_blocks(filtered)
    return "\n\n".join(deduped)


# ---------------------------------------------------------------------------
# Fallback segmentation: when text is one giant blob
# ---------------------------------------------------------------------------

_SENTENCE_END_RE = re.compile(r'(?<=[.!?])\s+(?=[A-ZА-ЯЁ"])')


def _fallback_segment(text: str) -> str:
    """
    Segment a wall-of-text into reasonable blocks.
    Used when double-newline splitting produces ≤1 block.
    """
    # Try splitting by double newlines first
    parts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(parts) > 1:
        return "\n\n".join(parts)

    # Split by sentences, then group into paragraphs of 3-5 sentences
    sentences = _SENTENCE_END_RE.split(text.strip())
    sentences = [s.strip() for s in sentences if s.strip()]

    if len(sentences) <= 1:
        # Last resort: split by single newlines
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        if len(lines) > 1:
            return _segment_lines(lines)
        return text.strip()

    paragraphs: list[str] = []
    group: list[str] = []
    for s in sentences:
        group.append(s)
        if len(group) >= 4:
            paragraphs.append(" ".join(group))
            group = []
    if group:
        paragraphs.append(" ".join(group))

    return "\n\n".join(paragraphs)


def _segment_lines(lines: list[str]) -> str:
    """
    Try to detect headings and lists from plain lines.
    Short lines without trailing period → potential heading.
    Lines starting with -, •, or digit. → list items.
    """
    result: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Already has markdown prefix
        if _MD_HEADING_RE.match(stripped) or _MD_LIST_RE.match(stripped) or _MD_QUOTE_RE.match(stripped):
            result.append(stripped)
        # Short line without period → heading candidate
        elif len(stripped) < 80 and not stripped.endswith((".", "!", "?", ",", ";", ":")):
            result.append(f"## {stripped}")
        else:
            result.append(stripped)
    return "\n\n".join(result)


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def _build_markdown(meta: dict[str, str], content: str) -> str:
    """Assemble the final markdown document."""
    parts: list[str] = []

    # Title
    title = meta.get("title", "").strip() or "Untitled"
    parts.append(f"# {title}")
    parts.append("")

    # Meta block
    if meta.get("site"):
        parts.append(f"**Site:** {meta['site']}")
    if meta.get("url"):
        parts.append(f"**URL:** {meta['url']}")
    if meta.get("date"):
        parts.append(f"**Date:** {meta['date']}")
    if meta.get("author"):
        parts.append(f"**Author:** {meta['author']}")

    parts.append("")
    parts.append("---")
    parts.append("")

    # Content
    parts.append(content)

    text = "\n".join(parts)

    # Collapse excessive blank lines
    text = _BLANK_LINES_RE.sub("\n\n", text)

    # Enforce output limit
    if len(text) > _MAX_OUTPUT_CHARS:
        text = text[:_MAX_OUTPUT_CHARS].rsplit("\n", 1)[0] + "\n\n[...truncated]"

    return text


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def normalize_page(
    url: str,
    raw_html: Optional[str] = None,
    fallback_text: Optional[str] = None,
) -> str:
    """
    Produce a clean, structured markdown representation of a web page.

    Parameters
    ----------
    url : str
        The page URL (used for meta and as trafilatura hint).
    raw_html : str | None
        The original HTML of the page, if available.
    fallback_text : str | None
        Already-extracted text to use when raw_html is not available.

    Returns
    -------
    str
        A markdown document with meta header and cleaned content.
    """
    meta = _extract_meta(raw_html, fallback_text, url)
    content = _extract_content(raw_html, fallback_text, url)

    if not content.strip():
        return _build_markdown(meta, "*No content extracted.*")

    # Use strict boilerplate filtering only when we had raw HTML to work from;
    # for fallback text (already extracted) be lenient to keep short-but-real blocks.
    strict = bool(raw_html)
    cleaned = _clean_content(content, strict=strict)

    # If cleaning collapsed everything into ≤1 block, try fallback segmentation
    block_count = len([b for b in cleaned.split("\n\n") if b.strip()])
    if block_count <= 1 and len(cleaned) > 300:
        cleaned = _fallback_segment(content)
        cleaned = _clean_content(cleaned, strict=strict)

    return _build_markdown(meta, cleaned)
