# Copyright NEXTGGTECH. Elastic License 2.0.

from __future__ import annotations

import html as html_lib
import re
from typing import Optional
from urllib.parse import urlparse

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

from core.extract.content_processor import (
    _preclean_html,
    _extract_text_with_bs4,
    _regex_html_to_text,
    _normalize_text,
    _dedupe_blocks,
    _get_boilerplate_filter,
)

_MAX_OUTPUT_CHARS = 50_000
_NO_CONTENT_MARKER = "*No content extracted.*"
_WHITESPACE_RE = re.compile(r"[ \t\r\f\v]+")
_TAG_RE = re.compile(r"<[^>]+>")

_MD_HEADING_RE = re.compile(r"^#{1,6}\s")
_MD_LIST_RE = re.compile(r"^(\s*[-*•]\s|\s*\d+[.)]\s)")
_MD_QUOTE_RE = re.compile(r"^>\s?")
_MD_CODE_FENCE_RE = re.compile(r"^```")


# Return whether normalized markdown contains page content rather than metadata alone.
def has_extractable_content(markdown: str) -> bool:
    return bool(markdown and markdown.strip() and _NO_CONTENT_MARKER not in markdown)


# Extract metadata using trafilatura (CPU only).
def _extract_meta_trafilatura(raw_html: str) -> dict[str, str]:
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


# Extract metadata from HTML using regex / bs4.
def _extract_meta_fallback(raw_html: str) -> dict[str, str]:
    meta: dict[str, str] = {}

    m = re.search(r"<title[^>]*>(.*?)</title>", raw_html, re.IGNORECASE | re.DOTALL)
    if m:
        meta["title"] = _normalize_text(m.group(1))

    m = re.search(
        r'<meta[^>]+name=["\']author["\'][^>]+content=["\'](.*?)["\']',
        raw_html, re.IGNORECASE,
    )
    if m:
        meta["author"] = _normalize_text(m.group(1))

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


# Build a meta dict from HTML, fallback text, and URL.
def _extract_meta(raw_html: Optional[str], fallback_text: Optional[str], url: str) -> dict[str, str]:
    meta: dict[str, str] = {}

    if raw_html:
        if _HAS_TRAFILATURA:
            meta = _extract_meta_trafilatura(raw_html)
        if not meta.get("title"):
            fb = _extract_meta_fallback(raw_html)
            meta = {**fb, **{k: v for k, v in meta.items() if v}}

    if not meta.get("title") and fallback_text:
        first_line = fallback_text.strip().split("\n", 1)[0].strip()
        if len(first_line) < 150 and first_line and not first_line.endswith("."):
            meta["title"] = first_line

    parsed = urlparse(url)
    meta["site"] = parsed.netloc.removeprefix("www.")
    meta["url"] = url
    return meta


# Protect preformatted blocks before an extractor normalizes the surrounding DOM.
def _protect_pre_blocks(source_html: str) -> tuple[str, list[tuple[str, str, str]]]:
    if not (_HAS_BS4 and "<pre" in source_html.lower()):
        return source_html, []

    from core.extract.markdown_code import wrap_pre_with_markers

    soup = BeautifulSoup(source_html, "lxml")
    markers = wrap_pre_with_markers(soup)
    return str(soup), markers


# Use trafilatura with include_formatting=True for markdown-like output. Recall mode is
# useful for already-isolated article HTML returned by structured APIs: there is no site
# chrome to reject, so retaining the whole article is safer than main-content guessing.
def _extract_with_trafilatura_formatted(
    cleaned_html: str,
    url: str = "",
    *,
    favor_recall: bool = False,
) -> str:
    if not cleaned_html:
        return ""
    source_html, code_markers = _protect_pre_blocks(cleaned_html)
    try:
        text = trafilatura.extract(
            source_html,
            url=url or None,
            include_comments=False,
            include_tables=True,
            include_formatting=True,
            include_links=True,
            favor_precision=not favor_recall,
            favor_recall=favor_recall,
            deduplicate=False,
            output_format="markdown" if favor_recall else "txt",
        )
    except Exception:
        return ""
    from core.extract.markdown_code import restore_pre_markers

    return restore_pre_markers(text or "", code_markers)


# DOM block extraction with structural nav/UI rejection. Returns (joined_text, stats);
# ("", {}) on any failure so the caller falls back to trafilatura/bs4/regex.
def _extract_with_dom_blocks(cleaned_html: str, url: str) -> tuple[str, dict]:
    try:
        from core.extract.dom_block_extractor import extract_dom_blocks
        from core.extract.markdown_code import restore_pre_markers

        source_html, code_markers = _protect_pre_blocks(cleaned_html)
        blocks, stats = extract_dom_blocks(source_html, url=url)
        text = restore_pre_markers("\n\n".join(blocks), code_markers)
        return text, dict(stats)
    except Exception:  # noqa: BLE001 — extraction refinement must never sink a read
        return "", {}


# Extract and return the main textual content from HTML or fallback.
def _extract_content(raw_html: Optional[str], fallback_text: Optional[str], url: str) -> str:
    if raw_html:
        cleaned_html = _preclean_html(raw_html)
        min_chars = 200

        # Keep the formatted result whenever it is substantial. A DOM pass's own reject
        # count cannot tell us whether this different extractor retained boilerplate.
        if _HAS_TRAFILATURA:
            text = _extract_with_trafilatura_formatted(cleaned_html, url)
            if len(_normalize_text(text)) >= min_chars:
                return text

        # Structural nav/UI rejection remains the fallback for thin formatted output.
        dom_text, _dom_stats = _extract_with_dom_blocks(cleaned_html, url)
        dom_ok = len(_normalize_text(dom_text)) >= min_chars
        if dom_ok:
            return dom_text

        if _HAS_BS4:
            text = _extract_text_with_bs4(cleaned_html)
            if len(_normalize_text(text)) >= min_chars:
                return text

        text = _regex_html_to_text(cleaned_html or raw_html)
        if text.strip():
            return text

    if fallback_text:
        return fallback_text.strip()

    return ""


# Split text into blocks by double-newlines, preserving markdown structure.
def _split_blocks_structured(text: str) -> list[str]:
    pieces = re.split(r"\n\s*\n", text or "")
    blocks: list[str] = []
    for piece in pieces:
        stripped = piece.strip()
        if not stripped:
            continue
        if (
            _MD_HEADING_RE.match(stripped)
            or _MD_LIST_RE.match(stripped)
            or _MD_QUOTE_RE.match(stripped)
            or _MD_CODE_FENCE_RE.match(stripped)
        ):
            blocks.append(stripped)
        else:
            normalized = _WHITESPACE_RE.sub(
                " ", html_lib.unescape(stripped).replace("\u00a0", " ")
            ).strip()
            if normalized:
                blocks.append(normalized)
    return blocks


# True when block is markdown heading, list, quote, or code fence.
def _is_structured_block(block: str) -> bool:
    return bool(
        _MD_HEADING_RE.match(block)
        or _MD_LIST_RE.match(block)
        or _MD_QUOTE_RE.match(block)
        or _MD_CODE_FENCE_RE.match(block)
    )


# Clean and deduplicate blocks while preserving markdown structure.
def _clean_content(text: str, strict: bool = True) -> str:
    is_boilerplate = _get_boilerplate_filter()
    blocks = _split_blocks_structured(text)

    filtered: list[str] = []
    for block in blocks:
        if _is_structured_block(block):
            filtered.append(block)
            continue
        if strict:
            if not is_boilerplate(block):
                filtered.append(block)
        else:
            compact = _normalize_text(block).lower()
            if not any(m in compact for m in (
                "cookie", "consent", "gdpr", "newsletter", "subscribe",
                "sign up", "advert", "sponsored", "all rights reserved",
                "accept all", "privacy policy", "terms of service",
            )):
                filtered.append(block)

    deduped = _dedupe_blocks(filtered)
    return "\n\n".join(deduped)


_SENTENCE_END_RE = re.compile(r'(?<=[.!?])\s+(?=[A-ZА-ЯЁ"])')


# Segment a wall-of-text into reasonable blocks.
def _fallback_segment(text: str) -> str:
    parts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(parts) > 1:
        return "\n\n".join(parts)

    sentences = _SENTENCE_END_RE.split(text.strip())
    sentences = [s.strip() for s in sentences if s.strip()]

    if len(sentences) <= 1:
        lines = [line.strip() for line in text.split("\n") if line.strip()]
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


# Turn short non-sentence lines into markdown headings.
def _segment_lines(lines: list[str]) -> str:
    result: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if _MD_HEADING_RE.match(stripped) or _MD_LIST_RE.match(stripped) or _MD_QUOTE_RE.match(stripped):
            result.append(stripped)
        elif len(stripped) < 80 and not stripped.endswith((".", "!", "?", ",", ";", ":")):
            result.append(f"## {stripped}")
        else:
            result.append(stripped)
    return "\n\n".join(result)


# Assemble the final markdown document with meta header.
def _build_markdown(meta: dict[str, str], content: str) -> str:
    parts: list[str] = []

    title = meta.get("title", "").strip() or "Untitled"
    parts.append(f"# {title}")
    parts.append("")

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
    parts.append(content)

    text = "\n".join(parts)
    # Repair GFM tables (trafilatura drops the header row's leading `|`, etc.) so every
    # renderer parses them. No-op on table-free pages.
    from core.extract.markdown_tables import normalize_markdown_tables

    text = normalize_markdown_tables(text)
    from core.extract.markdown_code import collapse_blank_lines_preserving_fences

    text = collapse_blank_lines_preserving_fences(text)

    if len(text) > _MAX_OUTPUT_CHARS:
        from core.extract.content_processor import _truncate_markdown_to_budget

        text = _truncate_markdown_to_budget(text, _MAX_OUTPUT_CHARS)

    return text


# Clean extraction below this is "too thin" — worth comparing against the full body
# (mirrors openserp's minCleanTextRunes).
_MIN_CLEAN_CHARS = 250


# Produce a clean, structured markdown representation of a web page.
def normalize_page(
    url: str,
    raw_html: Optional[str] = None,
    fallback_text: Optional[str] = None,
    *,
    favor_recall: bool = False,
) -> str:
    meta = _extract_meta(raw_html, fallback_text, url)

    # Trafilatura's formatted precision pass is both faster and more faithful on normal
    # articles and reference pages than flattening the same document into DOM blocks and
    # rebuilding structure afterwards. Keep the DOM/full-body machinery as the fallback
    # for genuinely thin extraction instead of running every successful page through it.
    if raw_html and _HAS_TRAFILATURA:
        formatted = _extract_with_trafilatura_formatted(raw_html, url, favor_recall=favor_recall)
        if len(_normalize_text(formatted)) >= 200:
            return _build_markdown(meta, formatted)

    content = _extract_content(raw_html, fallback_text, url)

    cleaned = ""
    if content.strip():
        strict = bool(raw_html)
        cleaned = _clean_content(content, strict=strict)

        block_count = len([b for b in cleaned.split("\n\n") if b.strip()])
        if block_count <= 1 and len(cleaned) > 300:
            cleaned = _fallback_segment(content)
            cleaned = _clean_content(cleaned, strict=strict)

    # thin→full-body rescue (openserp port): the clean pass strips everything it deems
    # boilerplate, which guts landing pages, doc indexes and download pages where the
    # "chrome" is the actual information. When the cleaned result is near-empty but the
    # page itself carried more visible text, return the whole readable body instead of a
    # husk — metadata keeps the clean pass's title/date. Bypasses _clean_content: block
    # filters would re-delete the short nav/CTA lines this path exists to preserve.
    if raw_html and len(_normalize_text(cleaned)) < _MIN_CLEAN_CHARS:
        from core.extract.content_processor import extract_full_body_text

        full = extract_full_body_text(raw_html)
        if len(_normalize_text(full)) > len(_normalize_text(cleaned)):
            return _build_markdown(meta, full)

    if not cleaned.strip():
        return _build_markdown(meta, _NO_CONTENT_MARKER)
    return _build_markdown(meta, cleaned)
