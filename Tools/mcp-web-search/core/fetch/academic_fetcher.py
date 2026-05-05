# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Registry-aware academic search fetcher.

This module provides a unified interface for searching academic aggregators
(Google Scholar, arXiv, PubMed, OpenAlex, etc.) based on the configurations
defined in academic_registry.json.

It avoids blind retries and instead selects the optimal method (HTTP,
Camoufox, or JSON API) for each domain as prescribed by the registry.

Public API
----------
AcademicFetcher -- async fetcher that executes academic searches
"""

from __future__ import annotations

import asyncio
import html
import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import quote_plus, urlparse

from core.extract.scoring import lexical_score
from core.extract.pdf_extractor import looks_like_pdf_url
from core.models.search import SearchResult

logger = logging.getLogger("core.fetch.academic_fetcher")

# ---------------------------------------------------------------------------
# Default Headers
# ---------------------------------------------------------------------------

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json,*/*;q=0.8",
}

_ACADEMIC_SNIPPET_BASE_CHARS = 500
_ACADEMIC_SNIPPET_MAX_EXTRA = 900
_ACADEMIC_SNIPPET_HARD_CAP = 1_800


def _normalize_pdf_url(url: str) -> str:
    value = str(url or "").strip()
    return value if value and looks_like_pdf_url(value) else ""


def _arxiv_pdf_url(url: str) -> str:
    value = str(url or "").strip()
    if not value:
        return ""
    if "arxiv.org/abs/" in value:
        return value.replace("/abs/", "/pdf/", 1)
    return _normalize_pdf_url(value)

# ---------------------------------------------------------------------------
# Registry Loader
# ---------------------------------------------------------------------------

def _load_academic_registry() -> list[dict[str, Any]]:
    try:
        reg_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "registry", "academic_registry.json",
        )
        with open(os.path.normpath(reg_path), encoding="utf-8") as fh:
            data = json.load(fh)
            return data.get("domains", [])
    except Exception as exc:
        logger.error("Failed to load academic registry: %s", exc)
        return []

# ---------------------------------------------------------------------------
# AcademicFetcher
# ---------------------------------------------------------------------------

class AcademicFetcher:
    """Orchestrates searches across multiple academic aggregators.

    Uses the optimal backend for each source as defined in the registry.
    """

    def __init__(self, timeout: float = 15.0):
        self._timeout = timeout
        self._registry = _load_academic_registry()

    def _fast_entries(self, topics: Optional[list[str]] = None) -> list[dict[str, Any]]:
        """Return lightweight academic engines safe for fast web search."""
        wanted_topics = {str(item).lower() for item in (topics or []) if str(item).strip()}
        out: list[dict[str, Any]] = []
        for entry in self._registry:
            method = str(entry.get("method", "")).lower()
            tier = str(entry.get("tier", "")).lower()
            response_ms = int(entry.get("response_time_ms") or 0)
            text_capable = bool(entry.get("text_search_capable", True))
            entry_topics = {str(item).lower() for item in (entry.get("topics") or []) if str(item).strip()}
            if method not in {"json_api", "http"}:
                continue
            if tier != "friendly":
                continue
            if response_ms and response_ms > 1200:
                continue
            if not text_capable:
                continue
            if wanted_topics and entry_topics and not (wanted_topics & entry_topics):
                continue
            out.append(entry)
        return out

    # -- Dispatchers ---------------------------------------------------------

    async def search(
        self,
        query: str,
        target_domains: Optional[list[str]] = None,
        max_results: int = 10,
    ) -> list[SearchResult]:
        """Search across academic engines.

        If target_domains is not specified, searches all academic engines
        concurrently (up to a reasonable limit).
        """
        results: list[SearchResult] = []
        
        # Filter engines to search
        engines_to_probe = []
        for entry in self._registry:
            pattern = entry.get("pattern", "")
            if not target_domains or any(d in pattern for d in target_domains):
                engines_to_probe.append(entry)

        if not engines_to_probe:
            logger.warning("No academic engines matched the request.")
            return []

        # Run searches in parallel
        tasks = [
            self._fetch_engine(entry, query, max_results)
            for entry in engines_to_probe
        ]
        
        all_engine_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for res in all_engine_results:
            if isinstance(res, list):
                results.extend(res)
            elif isinstance(res, Exception):
                logger.error("Academic engine fetch failed: %s", res)

        return results

    async def search_fast(
        self,
        query: str,
        *,
        max_results: int = 8,
        topics: Optional[list[str]] = None,
    ) -> list[SearchResult]:
        """Search only lightweight academic engines suitable for fast web search."""
        engines_to_probe = self._fast_entries(topics=topics)
        if not engines_to_probe:
            return []
        tasks = [self._fetch_engine(entry, query, max_results) for entry in engines_to_probe]
        all_engine_results = await asyncio.gather(*tasks, return_exceptions=True)
        merged: list[SearchResult] = []
        for res in all_engine_results:
            if isinstance(res, list):
                merged.extend(res)
            elif isinstance(res, Exception):
                logger.warning("Fast academic engine failed: %s", res)
        return merged

    async def _fetch_engine(
        self,
        entry: dict[str, Any],
        query: str,
        max_results: int,
    ) -> list[SearchResult]:
        """Fetch results from a single engine entry using its prescribed method."""
        name = entry.get("pattern", "unknown")
        method = entry.get("method", "http")
        url_template = entry.get("json_api_hint")
        
        logger.debug("Academic fetch [%s] method=%s", name, method)

        if not entry.get("text_search_capable", True) and "<doi>" in (url_template or ""):
            logger.debug("Skipping %s — not text-search capable (DOI-only API)", name)
            return []

        try:
            if method == "json_api" and url_template:
                return await self._fetch_json_api(entry, query, max_results)
            elif method == "camoufox":
                return await self._fetch_camoufox(entry, query, max_results)
            else:
                return await self._fetch_http(entry, query, max_results)
        except Exception as exc:
            logger.warning("Fetch failed for academic engine %s: %s", name, exc)
            return []

    # -- Backend Implementation ----------------------------------------------

    async def _fetch_json_api(
        self,
        entry: dict[str, Any],
        query: str,
        max_results: int,
    ) -> list[SearchResult]:
        """Handle REST API engines (OpenAlex, Crossref, etc.)."""
        import httpx
        
        domain = entry.get("pattern", "")
        url_template = entry.get("json_api_hint", "")
        
        # Build URL
        if "<q>" in url_template:
            url = url_template.replace("<q>", quote_plus(query))
        elif "<doi>" in url_template:
            # If it's a DOI query, we assume the whole query might be a DOI
            url = url_template.replace("<doi>", quote_plus(query))
        else:
            # Fallback appending query param if it's not in the template
            url = url_template + quote_plus(query)

        async with httpx.AsyncClient(headers=_HEADERS, timeout=self._timeout, follow_redirects=False) as client:
            r = await client.get(url)
            r.raise_for_status()
            data = r.json()

        # Parse results based on domain
        return self._parse_json_result(domain, data, max_results, query=query)

    async def _fetch_camoufox(
        self,
        entry: dict[str, Any],
        query: str,
        max_results: int,
    ) -> list[SearchResult]:
        """Handle SPA/Hardened engines via Camoufox."""
        from core.fetch.camoufox_fetcher import fetch_with_camoufox
        
        domain = entry.get("pattern", "")
        # For academic web searches, we usually build the URL using common patterns
        # if not explicitly provided in the registry entry.
        url = self._build_web_search_url(domain, query)
        
        result = await fetch_with_camoufox(url, timeout_sec=self._timeout)
        if not result.success or not result.html:
            return []

        return self._parse_html_result(domain, result.html, url, max_results)

    async def _fetch_http(
        self,
        entry: dict[str, Any],
        query: str,
        max_results: int,
    ) -> list[SearchResult]:
        """Handle moderate/friendly engines via HTTP."""
        import httpx
        
        domain = entry.get("pattern", "")
        url = self._build_web_search_url(domain, query)
        
        async with httpx.AsyncClient(headers=_HEADERS, timeout=self._timeout, follow_redirects=False) as client:
            r = await client.get(url)
            r.raise_for_status()
            html = r.text

        return self._parse_html_result(domain, html, url, max_results, query=query)

    # -- Parsing Logic -------------------------------------------------------

    def _build_web_search_url(self, domain: str, query: str) -> str:
        """Heuristically build web search URLs for known academic domains."""
        q = quote_plus(query)
        if "scholar.google.com" in domain:
            return f"https://scholar.google.com/scholar?q={q}&hl=en"
        if "arxiv.org" in domain:
            return f"https://arxiv.org/search/?query={q}&searchtype=all"
        if "pubmed" in domain:
            return f"https://pubmed.ncbi.nlm.nih.gov/?term={q}"
        if "semanticscholar" in domain:
            return f"https://www.semanticscholar.org/search?q={q}"
        if "base-search.net" in domain:
            return f"https://www.base-search.net/Search/Results?lookfor={q}"
        
        # Generic fallback
        return f"https://{domain}/search?q={q}"

    def _parse_html_result(
        self,
        domain: str,
        html: str,
        url: str,
        max_results: int,
        query: str = "",
    ) -> list[SearchResult]:
        """Fallback to Trafilatura-based HTML result extraction if no specific parser exists."""
        from bs4 import BeautifulSoup
        import trafilatura
        
        results: list[SearchResult] = []
        soup = BeautifulSoup(html, "html.parser")
        
        # Specific patterns for Scholar
        if "scholar.google.com" in domain:
            items = soup.find_all("div", class_="gs_r gs_or gs_scl")
            for item in items[:max_results]:
                title_elem = item.find("h3", class_="gs_rt")
                link_elem = title_elem.find("a") if title_elem else None
                snippet_elem = item.find("div", class_="gs_rs")
                pdf_link = ""
                pdf_box = item.find("div", class_="gs_or_ggsm")
                if pdf_box:
                    pdf_anchor = pdf_box.find("a", href=True)
                    if pdf_anchor:
                        pdf_link = _normalize_pdf_url(str(pdf_anchor["href"]))
                
                if title_elem and link_elem:
                    results.append(SearchResult(
                        url=link_elem["href"],
                        title=title_elem.text,
                        snippet=_build_dynamic_snippet(
                            query=query,
                            title=title_elem.text,
                            body=snippet_elem.text if snippet_elem else "",
                            url=link_elem["href"],
                        ),
                        engine=f"academic:{domain}",
                        pdf_url=pdf_link,
                    ))
            if results: return results

        # Specific patterns for arXiv
        if "arxiv.org" in domain:
            # ArXiv search results are usually within <li> with class "arxiv-result"
            items = soup.find_all("li", class_="arxiv-result")
            for item in items[:max_results]:
                # Title is in <p> with class "title"
                title_elem = item.find("p", class_="title")
                # ArXiv links are in a separate div with class "is-marginless"
                link_bar = item.find("div", class_="is-marginless")
                link_elem = link_bar.find("a") if link_bar else None
                # Abstract/Snippet
                snippet_elem = item.find("p", class_="abstract")
                if not snippet_elem:
                    snippet_elem = item.find("span", class_="abstract-full")
                
                if title_elem and link_elem:
                    result_url = (
                        link_elem["href"]
                        if link_elem["href"].startswith("http")
                        else f"https://arxiv.org{link_elem['href']}"
                    )
                    results.append(SearchResult(
                        url=result_url,
                        title=title_elem.text.strip(),
                        snippet=_build_dynamic_snippet(
                            query=query,
                            title=title_elem.text.strip(),
                            body=snippet_elem.text.strip() if snippet_elem else "",
                            url=result_url,
                        ),
                        engine=f"academic:{domain}",
                        pdf_url=_arxiv_pdf_url(result_url),
                    ))
            if results: return results

        # Generic Extraction (less reliable for search results)
        text = trafilatura.extract(html)
        if text:
            results.append(SearchResult(
                url=url,
                title=f"Results from {domain}",
                snippet=_build_dynamic_snippet(
                    query=query,
                    title=f"Results from {domain}",
                    body=text,
                    url=url,
                ),
                engine=f"academic:{domain}"
            ))
            
        return results

    def _parse_json_result(
        self,
        domain: str,
        data: Any,
        max_results: int,
        query: str = "",
    ) -> list[SearchResult]:
        """Map heterogeneous API responses to SearchResult models."""
        results: list[SearchResult] = []

        def _join_authors(names: list[str], limit: int = 3) -> str:
            picked = [item for item in names if item][:limit]
            return ", ".join(picked)

        def _openalex_abstract(item: dict[str, Any]) -> str:
            inv = item.get("abstract_inverted_index")
            if not isinstance(inv, dict):
                return ""
            tokens: list[tuple[int, str]] = []
            for word, positions in inv.items():
                if not isinstance(positions, list):
                    continue
                for pos in positions:
                    try:
                        tokens.append((int(pos), str(word)))
                    except Exception:
                        continue
            tokens.sort(key=lambda pair: pair[0])
            return " ".join(word for _, word in tokens)
        
        try:
            if "openalex.org" in domain:
                # OpenAlex format
                items = data.get("results") or []
                for item in items[:max_results]:
                    loc = item.get("primary_location") or {}
                    source = loc.get("source") or {}
                    journal = source.get("display_name") or "Unknown"
                    authorships = item.get("authorships") if isinstance(item.get("authorships"), list) else []
                    authors = [
                        str((auth.get("author") or {}).get("display_name") or "").strip()
                        for auth in authorships
                        if isinstance(auth, dict)
                    ]
                    year = item.get("publication_year")
                    meta_parts = []
                    if authors:
                        meta_parts.append(_join_authors(authors))
                    if year:
                        meta_parts.append(str(year))
                    if journal:
                        meta_parts.append(str(journal))
                    results.append(SearchResult(
                        url=(loc.get("landing_page_url") or item.get("doi") or item.get("id") or ""),
                        title=item.get("display_name") or "",
                        snippet=_build_dynamic_snippet(
                            query=query,
                            title=item.get("display_name") or "",
                            body=_openalex_abstract(item),
                            url=(loc.get("landing_page_url") or item.get("doi") or item.get("id") or ""),
                            meta_parts=meta_parts,
                        ),
                        engine="academic:openalex",
                        pdf_url=_normalize_pdf_url(loc.get("pdf_url") or ""),
                    ))
            
            elif "crossref.org" in domain:
                # Crossref format
                items = data.get("message", {}).get("items", [])
                for item in items[:max_results]:
                    authors = []
                    for author in item.get("author", []) if isinstance(item.get("author"), list) else []:
                        if not isinstance(author, dict):
                            continue
                        full_name = " ".join(
                            part for part in [author.get("given"), author.get("family")] if str(part or "").strip()
                        ).strip()
                        if full_name:
                            authors.append(full_name)
                    container = item.get('container-title', [''])
                    venue = container[0] if isinstance(container, list) and container else ""
                    year = ""
                    issued = item.get("issued") if isinstance(item.get("issued"), dict) else {}
                    date_parts = issued.get("date-parts") if isinstance(issued.get("date-parts"), list) else []
                    if date_parts and isinstance(date_parts[0], list) and date_parts[0]:
                        year = str(date_parts[0][0])
                    meta_parts = []
                    if authors:
                        meta_parts.append(_join_authors(authors))
                    if year:
                        meta_parts.append(year)
                    if venue:
                        meta_parts.append(venue)
                    results.append(SearchResult(
                        url=item.get("URL", ""),
                        title=item.get("title", [""])[0],
                        snippet=_build_dynamic_snippet(
                            query=query,
                            title=item.get("title", [""])[0],
                            body=_strip_jats(item.get("abstract") or ""),
                            url=item.get("URL", ""),
                            meta_parts=meta_parts,
                        ),
                        engine="academic:crossref"
                    ))
            
            elif "pubmed" in domain:
                # PubMed JSON format from eutils
                # Note: PubMed returns IDs first, then we'd need a second call for summary,
                # effectively this is just the ID list.
                ids = data.get("esearchresult", {}).get("idlist", [])
                for pm_id in ids[:max_results]:
                    results.append(SearchResult(
                        url=f"https://pubmed.ncbi.nlm.nih.gov/{pm_id}/",
                        title=f"PubMed ID: {pm_id}",
                        snippet="Click link for abstract.",
                        engine="academic:pubmed"
                    ))

            elif "core.ac.uk" in domain:
                items = data.get("results") or []
                for item in items[:max_results]:
                    authors = item.get("authors") if isinstance(item.get("authors"), list) else []
                    author_names = [str(author.get("name") or "").strip() for author in authors if isinstance(author, dict)]
                    year = item.get("yearPublished") or item.get("year")
                    meta_parts = []
                    if author_names:
                        meta_parts.append(_join_authors(author_names))
                    if year:
                        meta_parts.append(str(year))
                    results.append(SearchResult(
                        url=item.get("downloadUrl") or item.get("fullTextUrl") or "",
                        title=item.get("title") or "",
                        snippet=_build_dynamic_snippet(
                            query=query,
                            title=item.get("title") or "",
                            body=item.get("abstract") or "",
                            url=item.get("downloadUrl") or item.get("fullTextUrl") or "",
                            meta_parts=meta_parts,
                        ),
                        engine="academic:core",
                        pdf_url=_normalize_pdf_url(item.get("downloadUrl") or item.get("fullTextUrl") or ""),
                    ))

            elif "europepmc" in domain:
                items = data.get("resultList", {}).get("result", [])
                for item in items[:max_results]:
                    authors = str(item.get("authorString") or "").strip()
                    year = str(item.get("pubYear") or "").strip()
                    meta_parts = [part for part in [authors, year] if part]
                    results.append(SearchResult(
                        url=f"https://europepmc.org/article/{item.get('source')}/{item.get('id')}",
                        title=item.get("title", ""),
                        snippet=_build_dynamic_snippet(
                            query=query,
                            title=item.get("title", ""),
                            body=item.get("abstractText", ""),
                            url=f"https://europepmc.org/article/{item.get('source')}/{item.get('id')}",
                            meta_parts=meta_parts,
                        ),
                        engine="academic:europepmc"
                    ))

            elif "doaj.org" in domain:
                items = data.get("results", [])
                for item in items[:max_results]:
                    bib = item.get("bibjson", {})
                    results.append(SearchResult(
                        url=next((l.get("url") for l in bib.get("link", []) if l.get("type") == "fulltext"), ""),
                        title=bib.get("title", ""),
                        snippet=_build_dynamic_snippet(
                            query=query,
                            title=bib.get("title", ""),
                            body=bib.get("abstract", ""),
                            url=next((l.get("url") for l in bib.get("link", []) if l.get("type") == "fulltext"), ""),
                        ),
                        engine="academic:doaj"
                    ))

        except Exception as exc:
            logger.warning("JSON parsing failed for %s: %s", domain, exc)

        return results


def _strip_jats(text: str) -> str:
    value = str(text or "").strip()
    if not value:
        return ""
    value = re.sub(r"</?(?:jats:)?[^>]+>", " ", value)
    value = html.unescape(value)
    return " ".join(value.split())


def _clean_snippet_text(text: str) -> str:
    value = " ".join(str(text or "").split()).strip()
    value = re.sub(r"(?:\s*(?:\.{3}|…)+\s*)+$", "", value)
    return value


def _trim_to_sentence(text: str, target_chars: int, hard_cap: int) -> str:
    value = _clean_snippet_text(text)
    if not value:
        return ""
    if len(value) <= hard_cap:
        return value

    target_chars = max(160, min(int(target_chars), hard_cap))
    sentence_end_re = re.compile(r"[.!?](?:['\")\]]+)?(?=\s|$)")

    for match in sentence_end_re.finditer(value):
        end = match.end()
        if target_chars <= end <= hard_cap:
            return _finalize_sentence_candidate(value[:end].strip())

    best_end = -1
    for match in sentence_end_re.finditer(value[:hard_cap]):
        best_end = match.end()
    if best_end > 0:
        return _finalize_sentence_candidate(value[:best_end].strip())

    cut = value[:hard_cap]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.strip(" ,;:-")


def _build_dynamic_snippet(
    *,
    query: str,
    title: str,
    body: str,
    url: str,
    meta_parts: Optional[list[str]] = None,
) -> str:
    body_text = _clean_snippet_text(body)
    meta = " | ".join(part for part in (meta_parts or []) if str(part).strip())
    if not body_text:
        return meta

    relevance = lexical_score(query, title or "", body_text, url or "")
    target_chars = _ACADEMIC_SNIPPET_BASE_CHARS + int(_ACADEMIC_SNIPPET_MAX_EXTRA * relevance)
    hard_cap = min(_ACADEMIC_SNIPPET_HARD_CAP, target_chars + 220)
    snippet = _trim_to_sentence(body_text, target_chars=target_chars, hard_cap=hard_cap)

    if not meta:
        return snippet

    combined = f"{snippet} — {meta}" if snippet else meta
    if len(combined) <= _ACADEMIC_SNIPPET_HARD_CAP:
        return combined

    room_for_body = max(0, _ACADEMIC_SNIPPET_HARD_CAP - len(meta) - 3)
    if room_for_body >= 160:
        snippet = _trim_to_sentence(
            body_text,
            target_chars=min(target_chars, room_for_body),
            hard_cap=room_for_body,
        )
        return f"{snippet} — {meta}" if snippet else meta
    return snippet or meta


def _finalize_sentence_candidate(text: str) -> str:
    raw = str(text or "").strip()
    cleaned = _clean_snippet_text(raw)
    if raw.endswith(("...", "…")) and cleaned and cleaned[-1] not in ".!?":
        cleaned = f"{cleaned}."
    return cleaned
