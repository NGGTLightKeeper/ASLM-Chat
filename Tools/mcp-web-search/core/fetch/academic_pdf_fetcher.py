# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Academic PDF discovery and extraction pipeline.

Designed to operate within the Deep Research agentic loop.
Discovers direct PDF links from academic search result pages (Google Scholar,
arXiv, etc.), downloads them, and extracts clean markdown text via the
existing pdf_extractor layer.

No OCR fallback — relies exclusively on native digitized text extraction
(pymupdf4llm → PyMuPDF plaintext). Scanned-only PDFs will yield empty
content and will be silently skipped.

Public API
----------
AcademicPdfResult   -- structured result for a single PDF fetch+extract
AcademicPdfFetcher  -- async fetcher that discovers, downloads, and parses
                       PDF links from a given HTML page or a list of URLs
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from urllib.parse import urlparse

logger = logging.getLogger("core.fetch.academic_pdf_fetcher")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PDF_LINK_PATTERNS = re.compile(
    r"(?:\.pdf|/pdf/|format=pdf|arxiv\.org/pdf)",
    re.IGNORECASE,
)

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/pdf,*/*;q=0.8",
}

# Hard cap: 10 MB.  Matches the existing pdf_extractor limit.
_MAX_PDF_BYTES = 10 * 1_024 * 1_024


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class AcademicPdfResult:
    """Structured outcome of discovering and extracting one PDF."""

    url: str
    """Original URL of the PDF."""

    title: str = ""
    """Title extracted from PDF metadata or first heading."""

    markdown: str = ""
    """Extracted markdown text.  Empty if extraction failed."""

    source_page: str = ""
    """URL of the page where the PDF link was discovered."""

    error: str = ""
    """Non-empty if download or extraction failed."""

    @property
    def ok(self) -> bool:
        """Return True when markdown content is non-empty."""
        return bool(self.markdown)


# ---------------------------------------------------------------------------
# Link discovery helpers
# ---------------------------------------------------------------------------

def _find_pdf_links_in_html(html: str, base_url: str) -> list[str]:
    """Extract all href values that look like PDF URLs.

    Works without BeautifulSoup to avoid an extra dependency; uses a
    simple regex that is good enough for Scholar/arXiv result pages.
    """
    from urllib.parse import urljoin

    raw_hrefs = re.findall(r'href=["\']([^"\']+)["\']', html, re.IGNORECASE)
    results: list[str] = []
    seen: set[str] = set()

    for href in raw_hrefs:
        absolute = urljoin(base_url, href)
        if absolute in seen:
            continue
        if _PDF_LINK_PATTERNS.search(absolute):
            seen.add(absolute)
            results.append(absolute)

    return results


# ---------------------------------------------------------------------------
# Registry-aware download helpers
# ---------------------------------------------------------------------------

def _resolve_method(url: str) -> str:
    """Return the fetch method prescribed for *url* by the academic registry.

    Falls back to the general domain registry, and then to ``"http"`` if
    the domain is not listed anywhere.
    """
    # Try academic registry first (it's the authoritative source for these domains).
    try:
        import json
        import os

        _reg_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "registry", "academic_registry.json",
        )
        with open(os.path.normpath(_reg_path), encoding="utf-8") as fh:
            _reg = json.load(fh)
        domain = urlparse(url).netloc.lower().removeprefix("www.")
        for entry in _reg.get("domains", []):
            pattern = entry.get("pattern", "").lower()
            aliases = [a.lower() for a in entry.get("aliases") or []]
            if domain == pattern or domain in aliases or domain.endswith("." + pattern):
                return entry.get("method", "http")
    except Exception as exc:
        logger.debug("academic_registry lookup failed: %s", exc)

    # Fall through to the general domain registry.
    try:
        from core.registry.domain_registry import get_registry
        return get_registry().lookup(url).method
    except Exception:
        pass

    return "http"


async def _download_via_httpx(url: str, timeout: float) -> bytes:
    """Fetch PDF bytes using plain httpx (streaming, size-bounded)."""
    from core.extract.pdf_extractor import looks_like_pdf_bytes
    import httpx

    async with httpx.AsyncClient(
        headers=_DEFAULT_HEADERS,
        follow_redirects=True,
        verify=False,
        timeout=timeout,
    ) as client:
        async with client.stream("GET", url) as r:
            if r.status_code < 200 or r.status_code >= 400:
                raise ValueError(f"HTTP {r.status_code}")
            chunks: list[bytes] = []
            total = 0
            async for chunk in r.aiter_bytes():
                total += len(chunk)
                if total > _MAX_PDF_BYTES:
                    logger.debug("PDF too large, skipping: %s", url)
                    return b""
                chunks.append(chunk)
            data = b"".join(chunks)
            return data if looks_like_pdf_bytes(data) else b""


async def _download_via_camoufox(url: str, timeout: float) -> bytes:
    """Fetch PDF bytes using camoufox (JS-capable headless browser).

    Navigates to the PDF URL and returns the raw response body.  Camoufox
    is only reached when the registry explicitly prescribes it.
    """
    from core.extract.pdf_extractor import looks_like_pdf_bytes
    from core.fetch.camoufox_fetcher import fetch_with_camoufox

    result = await fetch_with_camoufox(url, timeout_ms=int(timeout * 1000))
    if not result.ok:
        raise ValueError(result.error or "camoufox returned empty response")

    # fetch_with_camoufox returns HTML text; for a PDF URL this is the
    # decoded body — check if it looks like raw PDF bytes decoded as text.
    # More reliably: try a direct byte fetch through the camoufox CDP layer.
    # For now we treat the raw bytes from the response body.
    data = result.html.encode("latin-1", errors="replace") if result.html else b""
    return data if looks_like_pdf_bytes(data) else b""


async def _download_pdf_bytes(url: str, timeout: float = 20.0) -> bytes:
    """Dispatch to the correct downloader based on the domain's registry entry.

    Consults ``academic_registry.json`` (and falls back to the general
    domain registry) to determine exactly which backend to use.  No cascade
    — the registry's decision is final.
    """
    method = _resolve_method(url)
    logger.debug("PDF download method=%s for %s", method, url)

    try:
        if method == "camoufox":
            return await _download_via_camoufox(url, timeout)
        else:
            # "http", "json_api", "curl_cffi", unknown — default to httpx.
            return await _download_via_httpx(url, timeout)
    except Exception as exc:
        logger.debug("PDF download failed (%s) for %s: %s", method, url, exc)
        return b""


# ---------------------------------------------------------------------------
# Core fetcher
# ---------------------------------------------------------------------------

class AcademicPdfFetcher:
    """Discover, download, and extract PDF documents from academic pages.

    Parameters
    ----------
    max_per_page:
        Maximum number of PDFs to process from a single source page.
    concurrency:
        Maximum parallel PDF downloads.
    timeout:
        Per-request timeout in seconds.
    """

    def __init__(
        self,
        max_per_page: int = 3,
        concurrency: int = 3,
        timeout: float = 20.0,
    ) -> None:
        self._max_per_page = max_per_page
        self._semaphore = asyncio.Semaphore(concurrency)
        self._timeout = timeout

    # -- Internal helpers ----------------------------------------------------

    async def _process_pdf_url(
        self,
        pdf_url: str,
        source_page: str = "",
    ) -> AcademicPdfResult:
        """Download one PDF and extract its markdown text."""
        async with self._semaphore:
            logger.debug("Downloading PDF: %s", pdf_url)

            data = await _download_pdf_bytes(pdf_url, timeout=self._timeout)
            if not data:
                return AcademicPdfResult(
                    url=pdf_url,
                    source_page=source_page,
                    error="download failed or not a valid PDF",
                )

            try:
                from core.extract.pdf_extractor import pdf_bytes_to_markdown

                markdown = pdf_bytes_to_markdown(url=pdf_url, data=data)
            except Exception as exc:
                logger.warning("PDF extraction error for %s: %s", pdf_url, exc)
                return AcademicPdfResult(
                    url=pdf_url,
                    source_page=source_page,
                    error=f"extraction failed: {exc}",
                )

            if not markdown or len(markdown) < 120:
                return AcademicPdfResult(
                    url=pdf_url,
                    source_page=source_page,
                    error="extracted content too short (likely scanned/image-only PDF)",
                )

            # Pull title from the first markdown heading
            title = ""
            for line in markdown.splitlines():
                stripped = line.lstrip("# ").strip()
                if stripped:
                    title = stripped[:200]
                    break

            logger.info(
                "PDF extracted: %s chars from %s",
                len(markdown),
                pdf_url,
            )
            return AcademicPdfResult(
                url=pdf_url,
                title=title,
                markdown=markdown,
                source_page=source_page,
            )

    # -- Public API ----------------------------------------------------------

    async def fetch_from_urls(
        self,
        pdf_urls: list[str],
        source_page: str = "",
    ) -> list[AcademicPdfResult]:
        """Fetch and extract a list of known PDF URLs directly.

        Parameters
        ----------
        pdf_urls:
            Direct links to PDF documents.
        source_page:
            URL of the page these PDFs were discovered on (for logging).

        Returns
        -------
        List of AcademicPdfResult, one per URL, in input order.
        Includes both successful and failed results.
        """
        capped = pdf_urls[: self._max_per_page]
        tasks = [
            self._process_pdf_url(url, source_page=source_page)
            for url in capped
        ]
        return list(await asyncio.gather(*tasks))

    async def discover_and_fetch(
        self,
        page_html: str,
        page_url: str,
    ) -> list[AcademicPdfResult]:
        """Discover PDF links within a Scholar/arXiv result page and extract them.

        Scans ``page_html`` for all href values matching PDF patterns, then
        downloads and extracts up to ``max_per_page`` of them concurrently.

        Parameters
        ----------
        page_html:
            Raw HTML of the search result page.
        page_url:
            URL of the search result page (used for relative URL resolution
            and logged as the source in each result).

        Returns
        -------
        List of AcademicPdfResult objects, filtered to those with content.
        Failed/empty results are included so callers can log them if needed.
        """
        pdf_links = _find_pdf_links_in_html(page_html, base_url=page_url)

        if not pdf_links:
            logger.debug("No PDF links found on page: %s", page_url)
            return []

        logger.info(
            "Found %d PDF link(s) on %s, processing up to %d",
            len(pdf_links),
            page_url,
            self._max_per_page,
        )

        return await self.fetch_from_urls(pdf_links, source_page=page_url)
