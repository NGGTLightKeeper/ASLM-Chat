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
import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import quote_plus, urlparse

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

# ---------------------------------------------------------------------------
# Registry Loader (Shared with academic_pdf_fetcher)
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

        async with httpx.AsyncClient(headers=_HEADERS, timeout=self._timeout, follow_redirects=True) as client:
            r = await client.get(url)
            r.raise_for_status()
            data = r.json()

        # Parse results based on domain
        return self._parse_json_result(domain, data, max_results)

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
        
        async with httpx.AsyncClient(headers=_HEADERS, timeout=self._timeout, follow_redirects=True) as client:
            r = await client.get(url)
            r.raise_for_status()
            html = r.text

        return self._parse_html_result(domain, html, url, max_results)

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

    def _parse_html_result(self, domain: str, html: str, url: str, max_results: int) -> list[SearchResult]:
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
                
                if title_elem and link_elem:
                    results.append(SearchResult(
                        url=link_elem["href"],
                        title=title_elem.text,
                        snippet=snippet_elem.text if snippet_elem else "",
                        engine=f"academic:{domain}"
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
                    results.append(SearchResult(
                        url=link_elem["href"] if link_elem["href"].startswith("http") else f"https://arxiv.org{link_elem['href']}",
                        title=title_elem.text.strip(),
                        snippet=snippet_elem.text.strip() if snippet_elem else "",
                        engine=f"academic:{domain}"
                    ))
            if results: return results

        # Generic Extraction (less reliable for search results)
        text = trafilatura.extract(html)
        if text:
            results.append(SearchResult(
                url=url,
                title=f"Results from {domain}",
                snippet=text[:500],
                engine=f"academic:{domain}"
            ))
            
        return results

    def _parse_json_result(self, domain: str, data: Any, max_results: int) -> list[SearchResult]:
        """Map heterogeneous API responses to SearchResult models."""
        results: list[SearchResult] = []
        
        try:
            if "openalex.org" in domain:
                # OpenAlex format
                items = data.get("results") or []
                for item in items[:max_results]:
                    loc = item.get("primary_location") or {}
                    source = loc.get("source") or {}
                    journal = source.get("display_name") or "Unknown"
                    results.append(SearchResult(
                        url=item.get("doi") or item.get("id") or "",
                        title=item.get("display_name") or "",
                        snippet=f"Paper in {journal}",
                        engine="academic:openalex"
                    ))
            
            elif "crossref.org" in domain:
                # Crossref format
                items = data.get("message", {}).get("items", [])
                for item in items[:max_results]:
                    results.append(SearchResult(
                        url=item.get("URL", ""),
                        title=item.get("title", [""])[0],
                        snippet=f"Published in {item.get('container-title', [''])[0]}",
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
                    results.append(SearchResult(
                        url=item.get("downloadUrl") or item.get("fullTextUrl") or "",
                        title=item.get("title") or "",
                        snippet=(item.get("abstract") or "")[:500],
                        engine="academic:core"
                    ))

            elif "europepmc" in domain:
                items = data.get("resultList", {}).get("result", [])
                for item in items[:max_results]:
                    results.append(SearchResult(
                        url=f"https://europepmc.org/article/{item.get('source')}/{item.get('id')}",
                        title=item.get("title", ""),
                        snippet=item.get("abstractText", "")[:500],
                        engine="academic:europepmc"
                    ))

            elif "doaj.org" in domain:
                items = data.get("results", [])
                for item in items[:max_results]:
                    bib = item.get("bibjson", {})
                    results.append(SearchResult(
                        url=next((l.get("url") for l in bib.get("link", []) if l.get("type") == "fulltext"), ""),
                        title=bib.get("title", ""),
                        snippet=bib.get("abstract", "")[:500],
                        engine="academic:doaj"
                    ))

        except Exception as exc:
            logger.warning("JSON parsing failed for %s: %s", domain, exc)

        return results
