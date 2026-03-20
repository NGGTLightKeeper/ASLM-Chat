# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

import asyncio
import hashlib
import json
import logging
import os
import re
import sqlite3
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

logger = logging.getLogger("background_agent.frontier")


# URL canonicalization helpers.

# Tracking-only parameters.
_TRACKING_PARAMS = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "utm_source_platform", "utm_creative_format", "utm_marketing_tactic",
    "fbclid", "gclid", "gclsrc", "dclid", "gbraid", "wbraid",
    "msclkid", "twclid", "li_fat_id", "_ga", "_gl",
    "mc_cid", "mc_eid",
    "yclid", "ymclid", "_openstat",
    "ref", "referer", "referrer",
    "spm", "scm", "pvid",
    "cmpid", "cid", "source", "medium",
})


# Normalize a URL for deduplication.
def canonicalize_url(url: str) -> str:
    """Normalize a URL into a stable representation for deduplication."""
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return url.strip()

    # 1. Lowercase scheme and host.
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()

    # 6. Upgrade http to https.
    if scheme == "http":
        scheme = "https"

    # 7. Drop the www. prefix.
    if netloc.startswith("www."):
        netloc = netloc[4:]

    # 2. Strip a trailing slash except on the root path.
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    # 3. Remove the fragment.
    # 4. Remove tracking parameters and 5. sort the query string.
    query_params = parse_qs(parsed.query, keep_blank_values=False)
    filtered = {
        k: v
        for k, v in query_params.items()
        if k.lower() not in _TRACKING_PARAMS
    }
    # Sort parameters for a stable canonical representation.
    sorted_query = urlencode(
        sorted(filtered.items()),
        doseq=True,
    )

    canonical = urlunparse((scheme, netloc, path, "", sorted_query, ""))
    return canonical


# Hash a normalized URL.
def url_hash(url: str) -> str:
    """Return the SHA-256 hash of the canonical URL."""
    return hashlib.sha256(canonicalize_url(url).encode()).hexdigest()


# Hash extracted content.
def content_hash(text: str) -> str:
    """Return the SHA-256 hash of content for idempotency checks."""
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


# Per-domain rate limiter helpers.

# Token bucket for one domain.
@dataclass
class _TokenBucket:
    """Simple token bucket for a single domain."""

    rate: float
    max_tokens: float
    tokens: float = 0.0
    last_refill: float = field(default_factory=time.time)

    # Refill tokens based on elapsed time.
    def _refill(self):
        now = time.time()
        elapsed = now - self.last_refill
        self.tokens = min(self.max_tokens, self.tokens + elapsed * self.rate)
        self.last_refill = now

    # Wait for the next available token.
    async def acquire(self):
        """Wait until the next token becomes available."""
        while True:
            self._refill()
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return
            # Wait only until the next token would be available.
            wait = (1.0 - self.tokens) / self.rate
            await asyncio.sleep(min(wait, 2.0))


# Per-domain rate limiter.
class DomainRateLimiter:
    # Configure default rate limits.
    def __init__(
        self,
        default_rps: float = 1.0,
        default_burst: float = 3.0,
        domain_overrides: Optional[Dict[str, float]] = None,
    ):
        self._default_rps = default_rps
        self._default_burst = default_burst
        self._domain_overrides = domain_overrides or {}
        self._buckets: Dict[str, _TokenBucket] = {}
        self._lock = asyncio.Lock()

    # Extract a normalized domain from a URL or host.
    def _get_domain(self, url_or_domain: str) -> str:
        """Extract the domain from a URL or accept a raw domain string."""
        if "://" in url_or_domain:
            return urlparse(url_or_domain).netloc.lower().removeprefix("www.")
        return url_or_domain.lower().removeprefix("www.")

    # Wait until a domain can issue the next request.
    async def acquire(self, url_or_domain: str):
        """Wait until the domain is allowed to issue another request."""
        domain = self._get_domain(url_or_domain)
        async with self._lock:
            if domain not in self._buckets:
                rps = self._domain_overrides.get(domain, self._default_rps)
                self._buckets[domain] = _TokenBucket(
                    rate=rps,
                    max_tokens=self._default_burst,
                    tokens=self._default_burst,
                )
        bucket = self._buckets[domain]
        # Wait outside the lock so other domains are not blocked.
        await bucket.acquire()


# URL frontier helpers.

# Single frontier queue entry.
@dataclass
class FrontierEntry:
    """Single frontier entry."""
    url: str
    canonical: str
    domain: str
    depth: int = 0
    priority: float = 0.0
    discovered_at: float = field(default_factory=time.time)


# In-memory URL frontier.
class URLFrontier:
    # Configure queue limits and prioritization.
    def __init__(
        self,
        max_per_domain: int = 20,
        max_depth: int = 3,
        priority_mode: str = "bfs",  # "bfs" | "short_path"
    ):
        self.max_per_domain = max_per_domain
        self.max_depth = max_depth
        self.priority_mode = priority_mode

        self._seen: Set[str] = set()
        self._queue: list = []
        self._domain_counts: Dict[str, int] = defaultdict(int)
        self._lock = asyncio.Lock()

    # Extract the normalized domain from a URL.
    def _get_domain(self, url: str) -> str:
        return urlparse(url).netloc.lower().removeprefix("www.")

    # Compute queue priority for a URL.
    def _compute_priority(self, url: str, depth: int) -> float:
        if self.priority_mode == "short_path":
            return len(urlparse(url).path) + depth * 100
        return float(depth)  # BFS

    # Add seed URLs to the frontier.
    def add_seeds(self, urls: List[str], depth: int = 0) -> int:
        """Add seed URLs and return the number of newly enqueued items."""
        import heapq
        added = 0
        for url in urls:
            canonical = canonicalize_url(url)
            if canonical in self._seen:
                continue
            domain = self._get_domain(canonical)
            if self._domain_counts[domain] >= self.max_per_domain:
                continue
            self._seen.add(canonical)
            self._domain_counts[domain] += 1
            entry = FrontierEntry(
                url=url,
                canonical=canonical,
                domain=domain,
                depth=depth,
                priority=self._compute_priority(url, depth),
            )
            heapq.heappush(self._queue, (entry.priority, id(entry), entry))
            added += 1
        return added

    # Add discovered URLs to the frontier.
    def add_discovered(
        self,
        urls: List[str],
        parent_depth: int,
    ) -> int:
        """Add discovered URLs and return the number actually enqueued."""
        import heapq
        new_depth = parent_depth + 1
        if new_depth > self.max_depth:
            return 0

        added = 0
        for url in urls:
            canonical = canonicalize_url(url)
            if canonical in self._seen:
                continue
            domain = self._get_domain(canonical)
            if self._domain_counts[domain] >= self.max_per_domain:
                continue
            self._seen.add(canonical)
            self._domain_counts[domain] += 1
            entry = FrontierEntry(
                url=url,
                canonical=canonical,
                domain=domain,
                depth=new_depth,
                priority=self._compute_priority(url, new_depth),
            )
            heapq.heappush(self._queue, (entry.priority, id(entry), entry))
            added += 1
        return added

    # Pop the next frontier entry.
    def pop(self) -> Optional[FrontierEntry]:
        """Pop the highest-priority URL from the frontier."""
        import heapq
        while self._queue:
            _, _, entry = heapq.heappop(self._queue)
            return entry
        return None

    # Return whether the frontier has queued items.
    def has_next(self) -> bool:
        return bool(self._queue)

    # Return the queued item count.
    @property
    def size(self) -> int:
        return len(self._queue)

    # Return the number of seen URLs.
    @property
    def seen_count(self) -> int:
        return len(self._seen)

    # Return per-domain queue counts.
    def domain_stats(self) -> Dict[str, int]:
        return dict(self._domain_counts)

    # Return whether a URL is already known.
    def is_seen(self, url: str) -> bool:
        return canonicalize_url(url) in self._seen


# Persistent crawl queue helpers.

# Crawl task status constants.
class CrawlTaskStatus:
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


# Persistent crawl task record.
@dataclass
class CrawlTaskRecord:
    """Task record stored in the persistent crawl queue."""
    url: str
    url_hash: str
    domain: str
    depth: int
    status: str = CrawlTaskStatus.PENDING
    attempt: int = 0
    max_retries: int = 3
    content_hash: Optional[str] = None
    error: Optional[str] = None
    created_at: float = 0.0
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    next_retry_at: Optional[float] = None


# SQLite-backed persistent crawl queue.
class PersistentCrawlQueue:
    # Configure queue storage and retry settings.
    def __init__(
        self,
        db_path: str = ":memory:",
        max_retries: int = 3,
        retry_base_delay: float = 5.0,
    ):
        self._db_path = db_path
        self._max_retries = max_retries
        self._retry_base_delay = retry_base_delay
        self._init_db()

    # Create the queue schema.
    def _init_db(self):
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS crawl_tasks (
                url_hash    TEXT PRIMARY KEY,
                url         TEXT NOT NULL,
                domain      TEXT NOT NULL,
                depth       INTEGER DEFAULT 0,
                status      TEXT DEFAULT 'pending',
                attempt     INTEGER DEFAULT 0,
                max_retries INTEGER DEFAULT 3,
                content_hash TEXT,
                error       TEXT,
                created_at  REAL,
                started_at  REAL,
                finished_at REAL,
                next_retry_at REAL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_status ON crawl_tasks(status)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_domain ON crawl_tasks(domain)
        """)
        # Recovery: move interrupted running tasks back to pending.
        conn.execute("""
            UPDATE crawl_tasks SET status = 'pending', attempt = attempt
            WHERE status = 'running'
        """)
        conn.commit()
        conn.close()
        logger.info(f"PersistentCrawlQueue initialized: {self._db_path}")

    # Enqueue one URL.
    def enqueue(
        self,
        url: str,
        domain: str = "",
        depth: int = 0,
    ) -> bool:
        """Add a URL to the queue and return whether it was newly inserted."""
        uhash = url_hash(url)
        if not domain:
            domain = urlparse(url).netloc.lower().removeprefix("www.")
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute(
                """INSERT OR IGNORE INTO crawl_tasks 
                   (url_hash, url, domain, depth, status, attempt, max_retries, created_at)
                   VALUES (?, ?, ?, ?, 'pending', 0, ?, ?)""",
                (uhash, url, domain, depth, self._max_retries, time.time()),
            )
            conn.commit()
            return conn.total_changes > 0
        finally:
            conn.close()

    # Enqueue multiple URLs.
    def enqueue_batch(self, urls: List[Tuple[str, str, int]]) -> int:
        """Batch insert URLs as `(url, domain, depth)` tuples."""
        conn = sqlite3.connect(self._db_path)
        added = 0
        try:
            for url, domain, depth in urls:
                uhash = url_hash(url)
                try:
                    conn.execute(
                        """INSERT OR IGNORE INTO crawl_tasks
                           (url_hash, url, domain, depth, status, attempt, max_retries, created_at)
                           VALUES (?, ?, ?, ?, 'pending', 0, ?, ?)""",
                        (uhash, url, domain, depth, self._max_retries, time.time()),
                    )
                    if conn.total_changes > 0:
                        added += 1
                except sqlite3.IntegrityError:
                    pass
            conn.commit()
        finally:
            conn.close()
        return added

    # Dequeue pending tasks for processing.
    def dequeue(self, limit: int = 1) -> List[CrawlTaskRecord]:
        """Dequeue pending tasks and mark them as running."""
        conn = sqlite3.connect(self._db_path)
        now = time.time()
        try:
            rows = conn.execute(
                """SELECT url_hash, url, domain, depth, attempt, max_retries
                   FROM crawl_tasks
                   WHERE status = 'pending'
                     AND (next_retry_at IS NULL OR next_retry_at <= ?)
                   ORDER BY depth ASC, created_at ASC
                   LIMIT ?""",
                (now, limit),
            ).fetchall()

            tasks = []
            for row in rows:
                uhash, url, domain, depth, attempt, max_retries = row
                conn.execute(
                    "UPDATE crawl_tasks SET status = 'running', started_at = ? WHERE url_hash = ?",
                    (now, uhash),
                )
                tasks.append(CrawlTaskRecord(
                    url=url,
                    url_hash=uhash,
                    domain=domain,
                    depth=depth,
                    status=CrawlTaskStatus.RUNNING,
                    attempt=attempt,
                    max_retries=max_retries,
                    started_at=now,
                ))
            conn.commit()
            return tasks
        finally:
            conn.close()

    # Mark a task as completed.
    def ack(self, url_hash_val: str, content_hash_val: Optional[str] = None):
        """Acknowledge successful completion and optionally store content hash."""
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute(
                """UPDATE crawl_tasks
                   SET status = 'done', finished_at = ?, content_hash = ?
                   WHERE url_hash = ?""",
                (time.time(), content_hash_val, url_hash_val),
            )
            conn.commit()
        finally:
            conn.close()

    # Mark a task as failed and reschedule if allowed.
    def nack(self, url_hash_val: str, error: str = ""):
        """Mark a task as failed and schedule exponential-backoff retry."""
        conn = sqlite3.connect(self._db_path)
        try:
            row = conn.execute(
                "SELECT attempt, max_retries FROM crawl_tasks WHERE url_hash = ?",
                (url_hash_val,),
            ).fetchone()
            if not row:
                return

            attempt, max_retries = row
            new_attempt = attempt + 1

            if new_attempt > max_retries:
                conn.execute(
                    """UPDATE crawl_tasks
                       SET status = 'failed', error = ?, finished_at = ?, attempt = ?
                       WHERE url_hash = ?""",
                    (error, time.time(), new_attempt, url_hash_val),
                )
            else:
                delay = self._retry_base_delay * (2 ** attempt)
                next_retry = time.time() + delay
                conn.execute(
                    """UPDATE crawl_tasks
                       SET status = 'pending', error = ?, attempt = ?, next_retry_at = ?
                       WHERE url_hash = ?""",
                    (error, new_attempt, next_retry, url_hash_val),
                )
                logger.info(f"Task {url_hash_val[:8]} retry #{new_attempt} in {delay:.0f}s")
            conn.commit()
        finally:
            conn.close()

    # Return whether a URL is already done.
    def is_done(self, url: str) -> bool:
        """Return whether the URL was already processed successfully."""
        uhash = url_hash(url)
        conn = sqlite3.connect(self._db_path)
        try:
            row = conn.execute(
                "SELECT status FROM crawl_tasks WHERE url_hash = ?",
                (uhash,),
            ).fetchone()
            return row is not None and row[0] == CrawlTaskStatus.DONE
        finally:
            conn.close()

    # Return whether matching content is already stored.
    def has_content(self, url: str, expected_content_hash: str) -> bool:
        """Return whether the expected content hash was already stored."""
        uhash = url_hash(url)
        conn = sqlite3.connect(self._db_path)
        try:
            row = conn.execute(
                "SELECT content_hash FROM crawl_tasks WHERE url_hash = ? AND status = 'done'",
                (uhash,),
            ).fetchone()
            return row is not None and row[0] == expected_content_hash
        finally:
            conn.close()

    # Return the pending task count.
    def pending_count(self) -> int:
        conn = sqlite3.connect(self._db_path)
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM crawl_tasks WHERE status = 'pending'"
            ).fetchone()
            return row[0] if row else 0
        finally:
            conn.close()

    # Return queue counts by status.
    def stats(self) -> Dict[str, int]:
        """Return queue counts grouped by task status."""
        conn = sqlite3.connect(self._db_path)
        try:
            rows = conn.execute(
                "SELECT status, COUNT(*) FROM crawl_tasks GROUP BY status"
            ).fetchall()
            return {r[0]: r[1] for r in rows}
        finally:
            conn.close()

    # Remove old finished tasks.
    def cleanup(self):
        """Delete finished tasks older than one hour."""
        conn = sqlite3.connect(self._db_path)
        try:
            cutoff = time.time() - 3600
            conn.execute(
                "DELETE FROM crawl_tasks WHERE status IN ('done', 'failed') AND finished_at < ?",
                (cutoff,),
            )
            conn.commit()
        finally:
            conn.close()
