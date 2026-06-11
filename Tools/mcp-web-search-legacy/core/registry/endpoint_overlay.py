# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import json
import logging
import os
import sqlite3
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Dict, List, Optional
from urllib.parse import urlparse, urlunparse

try:
    from .config import (
        DISCOVERED_ENDPOINTS_DB,
        ENDPOINT_DEACTIVATE_FAILURE_COUNT,
        ENDPOINT_PROBE_RECHECK_TTL_SEC,
        ENDPOINT_PROMOTION_SUCCESS_COUNT,
    )
except (ImportError, ValueError):
    from config import (  # type: ignore
        DISCOVERED_ENDPOINTS_DB,
        ENDPOINT_DEACTIVATE_FAILURE_COUNT,
        ENDPOINT_PROBE_RECHECK_TTL_SEC,
        ENDPOINT_PROMOTION_SUCCESS_COUNT,
    )

logger = logging.getLogger("endpoint_overlay")

ROOT_PROBE_PATHS = (
    ("robots", "/robots.txt"),
    ("sitemap", "/sitemap.xml"),
    ("sitemap", "/sitemap_index.xml"),
    ("rss", "/feed"),
    ("rss", "/rss"),
    ("rss", "/feed.xml"),
    ("rss", "/rss.xml"),
    ("atom", "/atom.xml"),
)

_XML_EXPECTED_TAGS = {
    "sitemap": ("urlset", "sitemapindex"),
    "xml_feed": ("urlset", "sitemapindex"),
    "rss": ("rss", "feed"),
    "atom": ("feed",),
}

# Normalize a domain string from URL or bare host.
def normalize_domain(url_or_domain: str) -> str:
    raw = (url_or_domain or "").strip().lower()
    if "://" in raw:
        raw = urlparse(raw).netloc.lower()
    if raw.startswith("www."):
        raw = raw[4:]
    return raw.strip("/")

# Normalize URL path; bare input treated as path on https host.
def normalize_path(url_or_domain: str) -> str:
    raw = (url_or_domain or "").strip()
    if not raw:
        return "/"
    if "://" not in raw:
        raw = f"https://{raw.lstrip('/')}"
    parsed = urlparse(raw)
    path = parsed.path or "/"
    return path if path.startswith("/") else f"/{path}"

# Build https base URL for a normalized domain.
def _base_url_for_domain(domain: str) -> str:
    return f"https://{normalize_domain(domain)}"

# Flatten nested JSON into plain text for content sniffing.
def _flatten_json(obj, depth: int = 0, max_depth: int = 5) -> str:
    if depth > max_depth:
        return ""
    if isinstance(obj, dict):
        chunks = []
        for key, value in obj.items():
            if isinstance(value, (dict, list)):
                nested = _flatten_json(value, depth + 1, max_depth)
                if nested:
                    chunks.append(f"{key}: {nested}")
            elif isinstance(value, str) and len(value.strip()) > 2:
                chunks.append(f"{key}: {value.strip()}")
        return "\n".join(chunks)
    if isinstance(obj, list):
        return "\n".join(_flatten_json(item, depth + 1, max_depth) for item in obj[:25])
    if isinstance(obj, str):
        return obj.strip()
    return ""

# Candidate endpoint discovered during probing.
@dataclass
class ProbeCandidate:
    domain: str
    endpoint_url: str
    endpoint_type: str
    scope: str = "domain"
    path_pattern: str = ""
    transform_kind: str = ""
    discovered_from_url: str = ""

    # Build a stable deduplication key for this candidate.
    def key(self) -> tuple:
        return (
            self.domain,
            self.endpoint_url,
            self.scope,
            self.path_pattern,
            self.transform_kind,
        )

# Resolved endpoint strategy for one domain.
@dataclass
class EndpointStrategy:
    domain: str
    endpoint_url: str
    endpoint_type: str
    scope: str
    path_pattern: str = ""
    transform_kind: str = ""
    source: str = "overlay"
    confidence: float = 0.0
    rewritten_url: str = ""

    # Map endpoint type to extraction method.
    @property
    def method(self) -> str:
        if self.endpoint_type == "json_endpoint":
            return "json_api"
        if self.endpoint_type == "prefix_transform":
            return "xml_feed"
        if self.endpoint_type in {"sitemap", "rss", "atom", "xml_feed"}:
            return "xml_feed"
        return "http"

    # Return whether the strategy is seed-only (sitemap/rss/atom/xml_feed).
    @property
    def is_seed_only(self) -> bool:
        return self.endpoint_type in {"sitemap", "rss", "atom", "xml_feed"} and self.scope == "domain"

# Build deduplicated probe candidates for a domain and optional sample URL.
def build_probe_candidates(domain: str, sample_url: str = "") -> List[ProbeCandidate]:
    normalized_domain = normalize_domain(domain)
    if not normalized_domain:
        return []

    base_url = _base_url_for_domain(normalized_domain)
    candidates: List[ProbeCandidate] = []

    for endpoint_type, path in ROOT_PROBE_PATHS:
        candidates.append(
            ProbeCandidate(
                domain=normalized_domain,
                endpoint_url=base_url + path,
                endpoint_type=endpoint_type,
                scope="domain",
                discovered_from_url=sample_url or base_url,
            )
        )

    sample_path = normalize_path(sample_url) if sample_url else "/"
    sample_path = sample_path if sample_path != "/" else ""
    if sample_path and not sample_path.endswith((".json", ".xml")):
        candidates.append(
            ProbeCandidate(
                domain=normalized_domain,
                endpoint_url=f"{base_url}{sample_path}.json",
                endpoint_type="json_endpoint",
                scope="path_exact",
                path_pattern=sample_path,
                discovered_from_url=sample_url,
            )
        )
        candidates.append(
            ProbeCandidate(
                domain=normalized_domain,
                endpoint_url=f"{base_url}{sample_path}.xml",
                endpoint_type="xml_feed",
                scope="path_exact",
                path_pattern=sample_path,
                discovered_from_url=sample_url,
            )
        )

        parsed = urlparse(sample_url)
        host = parsed.netloc.lower()
        bare_host = host[4:] if host.startswith("www.") else host
        if bare_host.count(".") == 1 and not host.startswith("xml."):
            transformed = urlunparse((parsed.scheme or "https", f"xml.{bare_host}", parsed.path, "", "", ""))
            candidates.append(
                ProbeCandidate(
                    domain=normalize_domain(bare_host),
                    endpoint_url=transformed,
                    endpoint_type="prefix_transform",
                    scope="domain",
                    path_pattern="/*",
                    transform_kind="xml_prefix_host",
                    discovered_from_url=sample_url,
                )
            )

    deduped: List[ProbeCandidate] = []
    seen = set()
    for candidate in candidates:
        key = candidate.key()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped

# Persist discovered endpoint strategies and validation state in SQLite.
class EndpointOverlayStore:

    # Open overlay DB and ensure endpoint_overlay table exists.
    def __init__(
        self,
        db_path: Optional[str] = None,
        promotion_success_count: int = ENDPOINT_PROMOTION_SUCCESS_COUNT,
        deactivate_failure_count: int = ENDPOINT_DEACTIVATE_FAILURE_COUNT,
        recheck_ttl_sec: int = ENDPOINT_PROBE_RECHECK_TTL_SEC,
    ):
        self.db_path = db_path or DISCOVERED_ENDPOINTS_DB
        self.promotion_success_count = max(1, int(promotion_success_count))
        self.deactivate_failure_count = max(1, int(deactivate_failure_count))
        self.recheck_ttl_sec = max(60, int(recheck_ttl_sec))
        self._lookup_cache: Dict[tuple[str, str], Optional[EndpointStrategy]] = {}
        self._seed_urls_cache: Dict[str, List[str]] = {}
        db_dir = os.path.dirname(os.path.abspath(self.db_path))
        if db_dir and self.db_path != ":memory:":
            os.makedirs(db_dir, exist_ok=True)
        self._init_db()

    # Open SQLite connection with row factory.
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # Create endpoint_overlay table if missing.
    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS endpoint_overlay (
                    domain TEXT NOT NULL,
                    endpoint_url TEXT NOT NULL,
                    endpoint_type TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    path_pattern TEXT NOT NULL DEFAULT '',
                    transform_kind TEXT NOT NULL DEFAULT '',
                    confidence REAL NOT NULL DEFAULT 0.0,
                    success_count INTEGER NOT NULL DEFAULT 0,
                    failure_count INTEGER NOT NULL DEFAULT 0,
                    consecutive_failures INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'candidate',
                    discovered_from_url TEXT NOT NULL DEFAULT '',
                    content_type TEXT NOT NULL DEFAULT '',
                    http_status INTEGER NOT NULL DEFAULT 0,
                    last_checked_at REAL NOT NULL DEFAULT 0,
                    last_success_at REAL NOT NULL DEFAULT 0,
                    last_failure_at REAL NOT NULL DEFAULT 0,
                    PRIMARY KEY (domain, endpoint_url, scope, path_pattern, transform_kind)
                )
                """
            )

    # Fetch existing overlay row matching probe candidate key.
    def _fetch_existing(self, conn: sqlite3.Connection, candidate: ProbeCandidate) -> Optional[sqlite3.Row]:
        return conn.execute(
            """
            SELECT * FROM endpoint_overlay
            WHERE domain = ? AND endpoint_url = ? AND scope = ? AND path_pattern = ? AND transform_kind = ?
            """,
            candidate.key(),
        ).fetchone()

    # Return best validated EndpointStrategy for domain and optional URL path.
    def lookup_validated(self, domain: str, url: Optional[str] = None) -> Optional[EndpointStrategy]:
        normalized_domain = normalize_domain(domain)
        if not normalized_domain:
            return None
        path = normalize_path(url or "")
        cache_key = (normalized_domain, path)
        if cache_key in self._lookup_cache:
            return self._lookup_cache[cache_key]
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM endpoint_overlay
                WHERE domain = ? AND status = 'validated'
                ORDER BY
                    CASE
                        WHEN scope = 'path_exact' AND path_pattern = ? THEN 0
                        WHEN endpoint_type = 'prefix_transform' THEN 1
                        WHEN scope = 'domain' THEN 2
                        ELSE 3
                    END,
                    confidence DESC,
                    success_count DESC
                """,
                (normalized_domain, path),
            ).fetchall()
        for row in rows:
            scope = str(row["scope"] or "domain")
            path_pattern = str(row["path_pattern"] or "")
            if scope == "path_exact" and path_pattern and path_pattern != path:
                continue
            if scope == "domain" and path not in ("", "/"):
                endpoint_path = normalize_path(str(row["endpoint_url"] or ""))
                if str(row["endpoint_type"] or "") != "prefix_transform" and endpoint_path != path:
                    continue
            rewritten_url = ""
            if str(row["endpoint_type"]) == "prefix_transform" and url:
                parsed = urlparse(url if "://" in url else f"https://{normalized_domain}{path}")
                rewritten_url = urlunparse(
                    (
                        parsed.scheme or "https",
                        f"xml.{normalized_domain}",
                        parsed.path,
                        "",
                        "",
                        "",
                    )
                )
            elif scope == "path_exact" and url:
                rewritten_url = str(row["endpoint_url"])
            strategy = EndpointStrategy(
                domain=normalized_domain,
                endpoint_url=str(row["endpoint_url"]),
                endpoint_type=str(row["endpoint_type"]),
                scope=scope,
                path_pattern=path_pattern,
                transform_kind=str(row["transform_kind"] or ""),
                confidence=float(row["confidence"] or 0.0),
                rewritten_url=rewritten_url,
            )
            self._lookup_cache[cache_key] = strategy
            return strategy
        self._lookup_cache[cache_key] = None
        return None

    # List validated domain-scoped seed endpoint URLs for domain.
    def get_validated_seed_urls(self, domain: str) -> List[str]:
        normalized_domain = normalize_domain(domain)
        if not normalized_domain:
            return []
        if normalized_domain in self._seed_urls_cache:
            return list(self._seed_urls_cache[normalized_domain])
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT endpoint_url
                FROM endpoint_overlay
                WHERE domain = ? AND status = 'validated' AND scope = 'domain'
                  AND endpoint_type != 'prefix_transform'
                ORDER BY confidence DESC, success_count DESC
                """,
                (normalized_domain,),
            ).fetchall()
        seed_urls = [str(row["endpoint_url"]) for row in rows]
        self._seed_urls_cache[normalized_domain] = seed_urls
        return list(seed_urls)


_overlay_store: Optional[EndpointOverlayStore] = None

# Shared EndpointOverlayStore singleton (optional db_path override).
def get_endpoint_overlay(db_path: Optional[str] = None) -> EndpointOverlayStore:
    global _overlay_store
    if _overlay_store is None or (db_path and _overlay_store.db_path != db_path):
        _overlay_store = EndpointOverlayStore(db_path=db_path)
    return _overlay_store
