# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

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
_WHITESPACE_RE = re.compile(r"[ \t\r\f\v]+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")
_TAG_RE = re.compile(r"<[^>]+>")

_MD_HEADING_RE = re.compile(r"^#{1,6}\s")
_MD_LIST_RE = re.compile(r"^(\s*[-*•]\s|\s*\d+[.)]\s)")
_MD_QUOTE_RE = re.compile(r"^>\s?")
_MD_CODE_FENCE_RE = re.compile(r"^```")


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


# Use trafilatura with include_formatting=True for markdown-like output.
def _extract_with_trafilatura_formatted(cleaned_html: str, url: str = "") -> str:
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


# DOM block extraction with structural nav/UI rejection. Returns (joined_text, stats);
# ("", {}) on any failure so the caller falls back to trafilatura/bs4/regex.
def _extract_with_dom_blocks(cleaned_html: str, url: str) -> tuple[str, dict]:
    try:
        from core.extract.dom_block_extractor import extract_dom_blocks

        blocks, stats = extract_dom_blocks(cleaned_html, url=url)
        return "\n\n".join(blocks), dict(stats)
    except Exception:  # noqa: BLE001 — extraction refinement must never sink a read
        return "", {}


# Extract and return the main textual content from HTML or fallback.
def _extract_content(raw_html: Optional[str], fallback_text: Optional[str], url: str) -> str:
    if raw_html:
        cleaned_html = _preclean_html(raw_html)
        min_chars = 200

        # Structural nav/UI rejection (menus, control clusters, link farms) — catches
        # boilerplate that survives trafilatura's main-content heuristic.
        dom_text, dom_stats = _extract_with_dom_blocks(cleaned_html, url)
        dom_ok = len(_normalize_text(dom_text)) >= min_chars

        if _HAS_TRAFILATURA:
            text = _extract_with_trafilatura_formatted(cleaned_html, url)
            if len(_normalize_text(text)) >= min_chars:
                # When the DOM pass rejected several nav/UI blocks, the page carries real
                # boilerplate that trafilatura's main-content heuristic tends to swallow —
                # prefer the structurally-filtered blocks. Clean pages (few/no rejects)
                # keep trafilatura's richer formatting (headings/lists/tables).
                if dom_ok and int(dom_stats.get("nav_rejected", 0)) >= 3:
                    return dom_text
                return text

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
    text = _BLANK_LINES_RE.sub("\n\n", text)

    if len(text) > _MAX_OUTPUT_CHARS:
        text = text[:_MAX_OUTPUT_CHARS].rsplit("\n", 1)[0] + "\n\n[...truncated]"

    return text


# Produce a clean, structured markdown representation of a web page.
def normalize_page(
    url: str,
    raw_html: Optional[str] = None,
    fallback_text: Optional[str] = None,
) -> str:
    meta = _extract_meta(raw_html, fallback_text, url)
    content = _extract_content(raw_html, fallback_text, url)

    if not content.strip():
        return _build_markdown(meta, "*No content extracted.*")

    strict = bool(raw_html)
    cleaned = _clean_content(content, strict=strict)

    block_count = len([b for b in cleaned.split("\n\n") if b.strip()])
    if block_count <= 1 and len(cleaned) > 300:
        cleaned = _fallback_segment(content)
        cleaned = _clean_content(cleaned, strict=strict)

    return _build_markdown(meta, cleaned)
