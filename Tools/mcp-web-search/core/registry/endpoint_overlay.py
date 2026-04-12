# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
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

# URL normalization helpers.
# Normalize a domain string.
def normalize_domain(url_or_domain: str) -> str:
    raw = (url_or_domain or "").strip().lower()
    if "://" in raw:
        raw = urlparse(raw).netloc.lower()
    if raw.startswith("www."):
        raw = raw[4:]
    return raw.strip("/")

# URL normalization helpers.
# Normalize a URL path.
def normalize_path(url_or_domain: str) -> str:
    raw = (url_or_domain or "").strip()
    if not raw:
        return "/"
    if "://" not in raw:
        raw = f"https://{raw.lstrip('/')}"
    parsed = urlparse(raw)
    path = parsed.path or "/"
    return path if path.startswith("/") else f"/{path}"

# URL normalization helpers.
# Build a base URL for a domain.
def _base_url_for_domain(domain: str) -> str:
    return f"https://{normalize_domain(domain)}"

# Payload helpers.
# Flatten nested JSON into plain text.
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

# Probe candidate models.
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

    # Identity helpers.
    # Build a stable deduplication key.
    def key(self) -> tuple:
        return (
            self.domain,
            self.endpoint_url,
            self.scope,
            self.path_pattern,
            self.transform_kind,
        )

# Endpoint strategy models.
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

    # Strategy helpers.
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

    # Strategy helpers.
    # Return whether the strategy is seed-only.
    @property
    def is_seed_only(self) -> bool:
        return self.endpoint_type in {"sitemap", "rss", "atom", "xml_feed"} and self.scope == "domain"

# Probe candidate builders.
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

# Probe validation helpers.
def validate_candidate_payload(candidate: ProbeCandidate, status: int, content_type: str, body: str) -> Optional[Dict]:
    if status != 200 or not body or len(body.strip()) < 20:
        return None

    lowered_type = (content_type or "").lower()
    trimmed = body.strip()

    if candidate.endpoint_type == "robots":
        sitemaps = []
        for line in trimmed.splitlines():
            if line.lower().startswith("sitemap:"):
                sitemap_url = line.split(":", 1)[1].strip()
                if sitemap_url.startswith("http"):
                    sitemaps.append(sitemap_url)
        if not sitemaps:
            return None
        return {
            "content_type": content_type,
            "http_status": status,
            "confidence": 0.65,
            "sitemaps": sitemaps,
        }

    if candidate.endpoint_type == "json_endpoint":
        if "json" not in lowered_type and not trimmed.startswith(("{", "[")):
            return None
        try:
            payload = json.loads(trimmed)
        except Exception:
            return None
        flattened = _flatten_json(payload)
        if len(flattened.strip()) < 80:
            return None
        return {
            "content_type": content_type,
            "http_status": status,
            "confidence": 0.90,
            "char_count": len(flattened),
        }

    if candidate.endpoint_type == "prefix_transform":
        try:
            root = ET.fromstring(trimmed)
        except Exception:
            return None
        tag = root.tag.rsplit("}", 1)[-1].lower()
        if tag not in ("urlset", "sitemapindex", "rss", "feed"):
            return None
        return {
            "content_type": content_type,
            "http_status": status,
            "confidence": 0.92,
            "root_tag": tag,
        }

    if "xml" not in lowered_type and not trimmed.startswith("<"):
        return None
    try:
        root = ET.fromstring(trimmed)
    except Exception:
        return None
    tag = root.tag.rsplit("}", 1)[-1].lower()
    expected = _XML_EXPECTED_TAGS.get(candidate.endpoint_type, ())
    if expected and tag not in expected:
        return None
    return {
        "content_type": content_type,
        "http_status": status,
        "confidence": 0.88 if candidate.endpoint_type == "sitemap" else 0.84,
        "root_tag": tag,
    }

# Overlay storage.
class EndpointOverlayStore:
    """Persist discovered endpoint strategies and their validation state."""

    # Construction helpers.
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
        db_dir = os.path.dirname(os.path.abspath(self.db_path))
        if db_dir and self.db_path != ":memory:":
            os.makedirs(db_dir, exist_ok=True)
        self._init_db()

    # SQLite helpers.
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # SQLite helpers.
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

    # SQLite helpers.
    def _fetch_existing(self, conn: sqlite3.Connection, candidate: ProbeCandidate) -> Optional[sqlite3.Row]:
        return conn.execute(
            """
            SELECT * FROM endpoint_overlay
            WHERE domain = ? AND endpoint_url = ? AND scope = ? AND path_pattern = ? AND transform_kind = ?
            """,
            candidate.key(),
        ).fetchone()

    # Lookup helpers.
    def get_entry(self, candidate: ProbeCandidate) -> Optional[Dict]:
        with self._connect() as conn:
            row = self._fetch_existing(conn, candidate)
        return dict(row) if row is not None else None

    # Lookup helpers.
    def get_due_candidates(self, domain: str, sample_url: str = "") -> List[ProbeCandidate]:
        candidates = build_probe_candidates(domain, sample_url=sample_url)
        if not candidates:
            return []
        now = time.time()
        due: List[ProbeCandidate] = []
        with self._connect() as conn:
            for candidate in candidates:
                row = self._fetch_existing(conn, candidate)
                if row is None:
                    due.append(candidate)
                    continue
                last_checked = float(row["last_checked_at"] or 0.0)
                status = str(row["status"] or "candidate")
                if status == "validated" and candidate.scope == "domain":
                    continue
                if now - last_checked >= self.recheck_ttl_sec:
                    due.append(candidate)
        return due

    # Persistence helpers.
    def record_probe_result(
        self,
        domain: str,
        candidate: ProbeCandidate,
        success: bool,
        metadata: Optional[Dict] = None,
    ) -> None:
        metadata = metadata or {}
        normalized_domain = normalize_domain(domain or candidate.domain)
        now = time.time()
        with self._connect() as conn:
            row = self._fetch_existing(conn, candidate)
            if not success and row is None:
                return

            existing_success = int(row["success_count"]) if row else 0
            existing_failure = int(row["failure_count"]) if row else 0
            new_success = existing_success + (1 if success else 0)
            new_failure = existing_failure + (0 if success else 1)
            consecutive_failures = 0 if success else int((row["consecutive_failures"] if row else 0) or 0) + 1

            status = "candidate"
            if success and new_success >= self.promotion_success_count:
                status = "validated"
            elif not success and consecutive_failures >= self.deactivate_failure_count:
                status = "inactive"
            elif row is not None:
                status = str(row["status"] or "candidate")

            conn.execute(
                """
                INSERT INTO endpoint_overlay (
                    domain, endpoint_url, endpoint_type, scope, path_pattern, transform_kind,
                    confidence, success_count, failure_count, consecutive_failures, status,
                    discovered_from_url, content_type, http_status,
                    last_checked_at, last_success_at, last_failure_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(domain, endpoint_url, scope, path_pattern, transform_kind)
                DO UPDATE SET
                    endpoint_type = excluded.endpoint_type,
                    confidence = excluded.confidence,
                    success_count = excluded.success_count,
                    failure_count = excluded.failure_count,
                    consecutive_failures = excluded.consecutive_failures,
                    status = excluded.status,
                    discovered_from_url = excluded.discovered_from_url,
                    content_type = excluded.content_type,
                    http_status = excluded.http_status,
                    last_checked_at = excluded.last_checked_at,
                    last_success_at = excluded.last_success_at,
                    last_failure_at = excluded.last_failure_at
                """,
                (
                    normalized_domain,
                    candidate.endpoint_url,
                    candidate.endpoint_type,
                    candidate.scope,
                    candidate.path_pattern,
                    candidate.transform_kind,
                    float(metadata.get("confidence", row["confidence"] if row else 0.0) or 0.0),
                    new_success,
                    new_failure,
                    consecutive_failures,
                    status,
                    candidate.discovered_from_url or metadata.get("discovered_from_url", ""),
                    str(metadata.get("content_type", row["content_type"] if row else "") or ""),
                    int(metadata.get("http_status", 0) or 0),
                    now,
                    now if success else float(row["last_success_at"] if row else 0.0),
                    now if not success else float(row["last_failure_at"] if row else 0.0),
                ),
            )

    # Lookup helpers.
    def lookup_validated(self, domain: str, url: Optional[str] = None) -> Optional[EndpointStrategy]:
        normalized_domain = normalize_domain(domain)
        if not normalized_domain:
            return None
        path = normalize_path(url or "")
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
            return EndpointStrategy(
                domain=normalized_domain,
                endpoint_url=str(row["endpoint_url"]),
                endpoint_type=str(row["endpoint_type"]),
                scope=scope,
                path_pattern=path_pattern,
                transform_kind=str(row["transform_kind"] or ""),
                confidence=float(row["confidence"] or 0.0),
                rewritten_url=rewritten_url,
            )
        return None

    # Lookup helpers.
    def get_validated_seed_urls(self, domain: str) -> List[str]:
        normalized_domain = normalize_domain(domain)
        if not normalized_domain:
            return []
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
        return [str(row["endpoint_url"]) for row in rows]

    # Persistence helpers.
    def mark_endpoint_failure(self, domain: str, endpoint_url: str) -> None:
        normalized_domain = normalize_domain(domain)
        if not normalized_domain or not endpoint_url:
            return
        now = time.time()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM endpoint_overlay
                WHERE domain = ? AND endpoint_url = ? AND status IN ('candidate', 'validated')
                ORDER BY success_count DESC
                LIMIT 1
                """,
                (normalized_domain, endpoint_url),
            ).fetchone()
            if row is None:
                return
            failure_count = int(row["failure_count"] or 0) + 1
            consecutive_failures = int(row["consecutive_failures"] or 0) + 1
            status = "inactive" if consecutive_failures >= self.deactivate_failure_count else str(row["status"] or "candidate")
            conn.execute(
                """
                UPDATE endpoint_overlay
                SET failure_count = ?, consecutive_failures = ?, status = ?, last_failure_at = ?, last_checked_at = ?
                WHERE domain = ? AND endpoint_url = ? AND scope = ? AND path_pattern = ? AND transform_kind = ?
                """,
                (
                    failure_count,
                    consecutive_failures,
                    status,
                    now,
                    now,
                    normalized_domain,
                    endpoint_url,
                    str(row["scope"]),
                    str(row["path_pattern"] or ""),
                    str(row["transform_kind"] or ""),
                ),
            )

    # Reporting helpers.
    def list_all(self) -> List[Dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM endpoint_overlay ORDER BY domain, endpoint_url").fetchall()
        return [dict(row) for row in rows]


_overlay_store: Optional[EndpointOverlayStore] = None

# Singleton access helpers.
def get_endpoint_overlay(db_path: Optional[str] = None) -> EndpointOverlayStore:
    global _overlay_store
    if _overlay_store is None or (db_path and _overlay_store.db_path != db_path):
        _overlay_store = EndpointOverlayStore(db_path=db_path)
    return _overlay_store
