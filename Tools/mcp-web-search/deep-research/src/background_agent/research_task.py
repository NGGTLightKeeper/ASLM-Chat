# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

import asyncio
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger("background_agent.task")

# Absolute path to deep-research/src.
_SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

# Core background-agent imports.
from .crawl_frontier import (
    URLFrontier, DomainRateLimiter, PersistentCrawlQueue,
    canonicalize_url, url_hash, content_hash,
)
from .crawl_metrics import CrawlMetrics
from .http_cache import HTTPCache
from .robots_checker import RobotsChecker

try:
    from ..domain_registry import get_registry
except (ImportError, ValueError):
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from domain_registry import get_registry

try:
    from ..endpoint_overlay import get_endpoint_overlay
except (ImportError, ValueError):
    from endpoint_overlay import get_endpoint_overlay

try:
    from ..domain_performance import get_domain_performance
except (ImportError, ValueError):
    from domain_performance import get_domain_performance

try:
    from ..config import STEALTH_ENABLE_CAMOUFOX, STEALTH_ENABLE_NODRIVER
except (ImportError, ValueError):
    STEALTH_ENABLE_NODRIVER = False
    STEALTH_ENABLE_CAMOUFOX = True

try:
    from ..extractor import build_page_evidence
except (ImportError, ValueError):
    from extractor import build_page_evidence

_DOMAIN_PERF = get_domain_performance()
_ENDPOINT_OVERLAY = get_endpoint_overlay()

_STATIC_MARKETPLACE_SEEDS: Dict[str, List[str]] = {
    "dns-shop.ru": ["https://www.dns-shop.ru/sitemap.xml"],
}

# Crawl result models.
# Normalized result of crawling one URL.
@dataclass
class CrawlResult:
    """Result of crawling one URL."""
    url: str
    text: Optional[str] = None
    title: Optional[str] = None
    char_count: int = 0
    method: str = ""
    success: bool = False
    blocks: List[Dict[str, Any]] = field(default_factory=list)
    page_evidence: Dict[str, Any] = field(default_factory=dict)

# Research summary models.
# Final metrics for one research task.
@dataclass
class ResearchSummary:
    """Final metrics for one completed research task."""
    task_id: str
    query: str
    domains_requested: int = 0
    urls_crawled: int = 0
    urls_successful: int = 0
    chunks_stored: int = 0
    elapsed_sec: float = 0.0
    backend: str = ""

# Seed discovery helpers.
def _known_seed_urls_for_domain(domain: str) -> List[str]:
    bare = domain.replace("https://", "").replace("http://", "").split("/")[0].lower()
    seeds: List[str] = []
    for known, static_seeds in _STATIC_MARKETPLACE_SEEDS.items():
        if bare.endswith(known) or known.endswith(bare):
            seeds.extend(static_seeds)
    seeds.extend(get_registry().get_seed_urls(bare))
    deduped: List[str] = []
    seen = set()
    for item in seeds:
        if not item or item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped

# Seed discovery helpers.
def _discover_urls(domains: List[str], depth: int = 1) -> List[str]:
    """Static fallback used when async BFS discovery cannot start."""
    urls = []
    for domain in domains:
        domain = domain.strip().rstrip("/")
        bare = domain.replace("https://", "").replace("http://", "").split("/")[0]
        root_url = ("https://" if not domain.startswith("http") else domain.split("://")[0] + "://") + bare
        urls.append(root_url)
        if depth >= 2:
            known_seeds = _known_seed_urls_for_domain(bare)
            if known_seeds:
                urls.extend(known_seeds)
            else:
                for path in ["/about", "/blog", "/news", "/catalog", "/sale"]:
                    urls.append(root_url + path)
    return list(dict.fromkeys(urls))


# Paths that do not carry useful content.
_SKIP_PATH_PATTERNS = (
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico",
    ".css", ".js", ".woff", ".woff2", ".ttf", ".eot", ".map",
    ".pdf", ".zip",
    "/login", "/signin", "/register", "/cart", "/checkout",
    "/api/", "/cdn-cgi/", "/static/", "javascript:",
    "#", "mailto:", "tel:",
)

# Link extraction helpers.
def _extract_links(html: str, base_url: str) -> List[str]:
    """Extract same-host links from HTML relative to the base URL."""
    from urllib.parse import urljoin, urlparse
    import re
    import xml.etree.ElementTree as ET

    # XML detection helpers.
    def _looks_like_xml_document(payload: str) -> bool:
        snippet = (payload or "").lstrip()[:512].lower()
        if not snippet:
            return False
        if snippet.startswith("<->xml"):
            return True
        if snippet.startswith("<!doctype html") or snippet.startswith("<html"):
            return False
        return any(
            marker in snippet
            for marker in ("<urlset", "<sitemapindex", "<rss", "<feed", "<loc>")
        )

    # XML detection helpers.
    def _extract_xml_links(payload: str) -> List[str]:
        links: List[str] = []
        try:
            root = ET.fromstring(payload)
        except ET.ParseError:
            links.extend(re.findall(r"<loc>\s*(.*->)\s*</loc>", payload, flags=re.IGNORECASE | re.DOTALL))
            links.extend(
                re.findall(r"<link\b[^>]*>\s*(.*->)\s*</link>", payload, flags=re.IGNORECASE | re.DOTALL)
            )
            links.extend(re.findall(r'\bhref=["\']([^"\']+)["\']', payload, flags=re.IGNORECASE))
            return links

        for elem in root.iter():
            if not isinstance(elem.tag, str):
                continue
            local_name = elem.tag.rsplit("}", 1)[-1].lower()
            if local_name not in {"loc", "link", "a"}:
                continue

            href = (elem.attrib.get("href") or "").strip()
            if href:
                links.append(href)

            text = (elem.text or "").strip()
            if text and local_name in {"loc", "link"}:
                links.append(text)

        return links

    base = urlparse(base_url)
    base_host = base.netloc.removeprefix("www.")

    if _looks_like_xml_document(html):
        raw_links = _extract_xml_links(html)
    else:
        # Prefer BeautifulSoup, fall back to regex.
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            raw_links = [tag.get("href", "") for tag in soup.find_all("a", href=True)]
        except ImportError:
            raw_links = re.findall(r'href=["\']([^"\']+)["\']', html)

    seen, result = set(), []
    for href in raw_links:
        href = href.strip()
        if not href:
            continue
        full = urljoin(base_url, href)
        parsed = urlparse(full)
        # Keep HTTP(S) links only.
        if parsed.scheme not in ("http", "https"):
            continue
        # Keep links on the same host only.
        if parsed.netloc.removeprefix("www.") != base_host:
            continue
        # Remove fragments.
        clean = parsed._replace(fragment="", query="").geturl()
        # Skip obvious junk paths.
        path_lower = parsed.path.lower()
        if any(p in path_lower for p in _SKIP_PATH_PATTERNS):
            continue
        if clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result

# Seed discovery helpers.
async def _ddgs_site_seeds(domains: List[str], query: str, max_per_domain: int = 3) -> List[str]:
    """Find relevant seed URLs per domain with DDGS site: queries."""
    # Thread-executor helpers.
    def _search_sync() -> List[str]:
        found = []
        try:
            try:
                from ddgs import DDGS
            except ImportError:
                from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                for domain in domains:
                    bare = domain.replace("https://", "").replace("http://", "").split("/")[0]
                    bare_nodot = bare.split(".")[-2] if bare.count(".") >= 1 else bare  # e.g. "github"
                    import re as _re
                    latin_query = " ".join(
                        w
                        for w in query.split()
                        if not any(0x0400 <= ord(ch) <= 0x04FF for ch in w)
                    ) or query
                    site_query = f"site:{bare} {latin_query}"
                    try:
                        hits = list(ddgs.text(site_query, max_results=max_per_domain))
                        logger.info(f"DDGS site:{bare} got {len(hits)} hits")
                        for hit in hits:
                            url = hit.get("href") or hit.get("url", "")
                            if not url:
                                continue
                            # Accept URL if it contains the domain OR the second-level domain name
                            if bare in url or bare_nodot in url:
                                found.append(url)
                                logger.info(f"DDGS site seed: {url[:80]}")
                            else:
                                logger.debug(f"DDGS filtered out: {url[:80]} (expected {bare})")
                    except Exception as e:
                        logger.debug(f"DDGS site search failed for {bare}: {e}")
        except ImportError:
            logger.debug("ddgs/duckduckgo_search not available, skipping site seeds")
        return found

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _search_sync)

# Frontier crawling helpers.
async def _bfs_discover_urls(
    domains: List[str],
    max_depth: int = 2,
    max_urls_per_domain: int = 10,
    fetch_timeout: float = 8.0,
    robots_checker: Optional["RobotsChecker"] = None,
    rate_limiter: Optional["DomainRateLimiter"] = None,
    http_cache: Optional["HTTPCache"] = None,
    metrics: Optional["CrawlMetrics"] = None,
    query: Optional[str] = None,
    deadline: float = 0.0,
) -> List[str]:
    """
    Frontier-driven BFS with URL normalization, deduplication, robots checks,
    per-domain rate limiting, and HTTP caching.

    High-level flow:
      1. Use normalized domain roots as seeds
      2. Continuously dispatch frontier URLs to workers
      3. Fetch pages, extract links, and requeue discoveries
      4. Check robots.txt before each fetch
      5. Reuse conditional GET through HTTPCache
      6. Enforce per-domain token buckets

    Known marketplaces receive additional verified API endpoint seeds.
    """
    # Build the frontier.
    frontier = URLFrontier(
        max_per_domain=max_urls_per_domain,
        max_depth=max_depth,
        priority_mode="short_path",
    )

    # Huge aggregator sites where crawling the root gives unrelated content.
    # For these, skip root BFS and rely only on DDGS site: seeds instead.
    _NO_ROOT_BFS_DOMAINS = frozenset({
        "arxiv.org", "github.com", "huggingface.co",
        "reddit.com", "twitter.com", "x.com", "youtube.com",
        "scholar.google.com", "semanticscholar.org",
    })

    root_seeds: List[str] = []        # root domain seeds (BFS will explore neighbours)
    specific_seeds: List[str] = []    # concrete page URLs (BFS will NOT follow their links)

    for domain in domains:
        domain = domain.strip().rstrip("/")
        parsed_d = urlparse(domain if "://" in domain else "https://" + domain)
        bare = parsed_d.netloc.removeprefix("www.")
        scheme = parsed_d.scheme + "://" if parsed_d.scheme else "https://"

        has_path = bool(parsed_d.path and parsed_d.path not in ("/", ""))
        if has_path:
            # Specific page - seed at max_depth so BFS won't follow its outgoing links
            specific_seeds.append(domain if "://" in domain else scheme + domain)
            continue

        # Aggregator/hub domains: root BFS produces irrelevant results.
        # Skip root seed - DDGS site: search below will provide relevant specific pages.
        if any(bare == nb or bare.endswith("." + nb) for nb in _NO_ROOT_BFS_DOMAINS):
            logger.info(f"Skipping root BFS for aggregator domain: {bare} (will use DDGS site: seeds)")
            continue

        root_url = scheme + bare
        root_seeds.append(root_url)

        # Add extra seeds for known marketplaces.
        root_seeds.extend(_known_seed_urls_for_domain(bare))

    # If a query exists, search for relevant pages through DDGS site: queries.
    all_root_domains = [d for d in domains
                        if not (urlparse(d if "://" in d else "https://" + d).path or "").strip("/")]
    if query and all_root_domains:
        site_seed_cap = max(3, min(8, max_urls_per_domain))
        site_seeds = await _ddgs_site_seeds(all_root_domains, query, max_per_domain=site_seed_cap)
        if site_seeds:
            specific_seeds = site_seeds + specific_seeds
            logger.info(f"BFS added {len(site_seeds)} DDGS site seeds for query={query[:40]!r}")

    # Specific pages first - guarantee their slots before root seeds fill the per-domain limit
    frontier.add_seeds(specific_seeds, depth=max_depth)
    # Root domains: BFS explores neighbours
    frontier.add_seeds(root_seeds, depth=0)
    logger.info(
        f"BFS frontier seeded: {frontier.size} URLs "
        f"({len(root_seeds)} roots + {len(specific_seeds)} specific) "
        f"from {len(domains)} domains"
    )

    # Main BFS loop.
    while frontier.has_next():
        if deadline > 0.0 and time.time() >= deadline:
            logger.info(
                f"BFS deadline reached: {frontier.seen_count} URLs discovered, "
                f"stopping early to preserve crawl budget"
            )
            break
        entry = frontier.pop()
        if entry is None:
            break

        url = entry.url
        domain = entry.domain

        # Specific seeds (depth=max_depth) are already known URLs - skip BFS fetch,
        # they will be crawled in the main crawl phase.
        if entry.depth >= max_depth:
            continue

        reg = get_registry()
        if reg.should_skip(url):
            logger.info(f"Skipping fortress or blocked domain: {url}")
            continue
        
        strategy = reg.resolve_access_strategy(url)
        if strategy.seed_urls and entry.depth == 0:
            frontier.add_seeds(strategy.seed_urls, depth=0)
        if strategy.rewritten_url:
            url = strategy.rewritten_url

        # Check robots.txt before each fetch.
        if robots_checker:
            allowed = await robots_checker.is_allowed(url)
            if not allowed:
                logger.debug(f"BFS robots.txt disallows: {url[:60]}")
                continue

        # [2] Per-domain rate limiting
        if rate_limiter:
            await rate_limiter.acquire(url)

        # [5] HTTP Cache: conditional headers
        cond_headers: Dict = {}
        if http_cache:
            cond_headers = http_cache.get_conditional_headers(url)

        t_start = time.time()
        html: Optional[str] = None
        status_code = 0

        # TTL freshness checks are sufficient during discovery.
        if http_cache and http_cache.is_fresh(url, max_age_sec=1800):
            cached = http_cache.get_cached(url)
            if cached:
                html = cached.html
                status_code = 304
                if metrics:
                    metrics.record_cache(domain, hit=True)

        if html is None:
            # Fetch through curl_cffi first.
            html = await _try_curl_cffi_simple(url, timeout=fetch_timeout)
            status_code = 200 if html else 0

            # Fall back to BrowserPool if curl_cffi fails.
            if not html:
                try:
                    _stealth_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    if _stealth_dir not in sys.path:
                        sys.path.insert(0, _stealth_dir)
                    from stealth_browser import BrowserPool
                    pool = BrowserPool(
                        max_concurrency=1,
                        memory_threshold_percent=88.0,
                        enable_nodriver=STEALTH_ENABLE_NODRIVER,
                        enable_camoufox=STEALTH_ENABLE_CAMOUFOX,
                    )
                    method_hint = reg.choose_method(url)
                    sr = await pool.extract(url, method_hint=method_hint)
                    html = sr.html if sr and sr.success else None
                    status_code = 200 if html else 0
                    logger.info(f"BFS BrowserPool fallback: {'OK' if html else 'FAIL'} {url[:60]}")
                except Exception as e:
                    logger.debug(f"BFS BrowserPool error: {e}")

            # Save successful fetches into the HTTP cache.
            if html and http_cache:
                http_cache.store(url, html, status=200)
                if metrics:
                    metrics.record_cache(domain, hit=False)

        # Record request metrics.
        if metrics and status_code > 0:
            metrics.record_request(
                domain,
                status=status_code if status_code != 304 else 200,
                latency=time.time() - t_start,
                bytes_=len(html) if html else 0,
            )

        if not html:
            continue

        # Extract links and add them back into the frontier.
        links = _extract_links(html, url)
        added = frontier.add_discovered(links, parent_depth=entry.depth)
        logger.debug(
            f"BFS [{entry.depth}] {url[:60]} -> {len(links)} links, {added} new in frontier"
        )

    # Return discovered URLs with specific seeds first.
    all_seeds = specific_seeds + root_seeds
    seed_canonicals = {canonicalize_url(u) for u in all_seeds}
    result_urls: List[str] = list(all_seeds)
    for canonical in frontier._seen:
        if canonical not in seed_canonicals:
            result_urls.append(canonical)
    all_urls = list(dict.fromkeys(result_urls))  # deduplicate preserving order
    logger.info(f"BFS finished: {frontier.seen_count} total, {len(all_urls)} unique URLs")
    return all_urls



# Lightweight HTTP client for easier domains.

# Anti-bot markers applied to both HTML and extracted text.
_ANTBOT_HTML_MARKERS = [
    # English
    "cloudflare", "captcha", "just a moment", "checking your browser",
    "ddos-guard", "bot detected", "access denied", "enable javascript",
    "403 forbidden", "attention required", "ray id",
]
_ANTBOT_TEXT_MARKERS = [
    # English (in clean text after trafilatura)
    "enable javascript", "checking your browser", "just a moment",
    "ddos-guard", "bot detected", "access denied", "403 forbidden",
    "err_too_many_redirects", "too many redirects",
    "page not found", "404 not found",
    "fab_chlg_",       # Ozon challenge token
    "such page",
]

# Fetch classification helpers.
def _is_antbot_text(text: str) -> bool:
    """Check plain text for anti-bot markers."""
    t = text.lower()
    return any(m in t for m in _ANTBOT_TEXT_MARKERS)

# Fetch fallback helpers.
async def _try_json_api(url: str, timeout: float = 8.0) -> Optional[str]:
    """Fetch public JSON or XML endpoints and flatten them into readable text."""
    if not any(x in url for x in [".json", ".xml", "/api/", "/v2/", "/v4/", "/catalog", "/search", "sitemap"]):
        return None
    try:
        import aiohttp
        import json
        async with aiohttp.ClientSession() as sess:
            async with sess.get(
                url, timeout=aiohttp.ClientTimeout(total=timeout),
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            ) as resp:
                if resp.status != 200:
                    return None
                ct = resp.headers.get("Content-Type", "")
                # JSON response.
                if "json" in ct or url.endswith(".json"):
                    data = await resp.json(content_type=None)
                    return _flatten_json(data)
                # XML (sitemap) - now returns List[str] of product/category URLs
                if "xml" in ct or url.endswith(".xml"):
                    text = await resp.text()
                    product_urls = _parse_sitemap(text)
                    if not product_urls:
                        return None
                    # Follow product URLs: fetch up to 5 in parallel, return combined text
                    sem = asyncio.Semaphore(5)
                    # Fetch one linked product page.
                    async def _fetch_one(u: str) -> str:
                        async with sem:
                            html = await _try_curl_cffi_simple(u, timeout=timeout)
                            if not html:
                                return ""
                            import trafilatura
                            t = trafilatura.extract(html, url=u, include_tables=True, no_fallback=False)
                            return t or ""
                    texts = await asyncio.gather(*[_fetch_one(u) for u in product_urls[:8]])
                    combined = "\n\n".join(t for t in texts if t and len(t) > 100)
                    return combined if len(combined) > 200 else None
                return None
    except Exception as e:
        logger.debug(f"JSON API error {url}: {e}")
        return None

# Payload helpers.
def _flatten_json(obj, depth: int = 0, max_depth: int = 5) -> str:
    """Recursively flatten JSON into readable text."""
    if depth > max_depth:
        return ""
    lines = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                sub = _flatten_json(v, depth + 1, max_depth)
                if sub:
                    lines.append(f"{k}: {sub}")
            elif isinstance(v, str) and len(v) > 2:
                lines.append(f"{k}: {v}")
    elif isinstance(obj, list):
        for item in obj[:50]:
            lines.append(_flatten_json(item, depth + 1, max_depth))
    elif isinstance(obj, str):
        return obj
    return "\n".join(filter(None, lines))

# Payload helpers.
def _parse_sitemap(xml_text: str) -> Optional[List[str]]:
    """Extract product and category URLs from sitemap.xml."""
    import re
    all_urls = re.findall(r"<loc>(.*->)</loc>", xml_text)
    # Filter out low-value sitemap branches.
    _SKIP_SITEMAP = ("image", "opinion", "rating", "accessories", "buy-together",
                     "old_product", "analog", "character")
    product_urls = [
        u for u in all_urls
        if not any(s in u.lower() for s in _SKIP_SITEMAP)
    ]
    return product_urls[:50] if product_urls else None

# Fetch fallback helpers.
async def _try_google_cache(url: str, timeout: float = 10.0) -> Optional[str]:
    """Load the Google cached version of a page."""
    import aiohttp
    from urllib.parse import quote
    cache_url = f"https://webcache.googleusercontent.com/search->q=cache:{quote(url)}"
    try:
        html = await _try_curl_cffi_simple(cache_url, timeout=timeout)
        if html and len(html) > 500:
            return html
    except Exception as e:
        logger.debug(f"Google cache error {url}: {e}")
    return None

# Fetch fallback helpers.
async def _try_curl_cffi(
    url: str,
    timeout: float = 10.0,
    extra_headers: Optional[Dict] = None,
) -> Optional[Tuple[Optional[str], int, Dict]]:
    """Run curl_cffi with optional conditional headers support."""
    try:
        import curl_cffi.requests as _curl
        headers = {"Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"}
        if extra_headers:
            headers.update(extra_headers)

        resp = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: _curl.get(
                url, impersonate="chrome124",
                timeout=timeout, verify=False,
                headers=headers,
            )
        )

        resp_headers = dict(resp.headers) if hasattr(resp, "headers") else {}

        # 304 Not Modified means the cached content is still valid.
        if resp.status_code == 304:
            return (None, 304, resp_headers)

        if resp.status_code not in (200, 201, 203):
            return (None, resp.status_code, resp_headers)

        html = resp.text
        html_lower = html.lower()
        if any(m in html_lower for m in _ANTBOT_HTML_MARKERS):
            return (None, resp.status_code, resp_headers)

        return (html, resp.status_code, resp_headers)
    except Exception:
        return None

# Fetch fallback helpers.
async def _try_curl_cffi_simple(url: str, timeout: float = 10.0) -> Optional[str]:
    """Backward-compatible wrapper that returns only html or None."""
    result = await _try_curl_cffi(url, timeout=timeout)
    if result is None:
        return None
    html, status, _ = result
    return html if status in (200, 201, 203) else None

# Crawl execution helpers.
async def _crawl_url(
    url: str,
    use_stealth: bool = True,
    use_playwright: bool = False,
    timeout: float = 30.0,
    # Extended architecture parameters.
    robots_checker: Optional["RobotsChecker"] = None,
    rate_limiter: Optional["DomainRateLimiter"] = None,
    http_cache: Optional["HTTPCache"] = None,
    metrics: Optional["CrawlMetrics"] = None,
    queue: Optional["PersistentCrawlQueue"] = None,
) -> "CrawlResult":
    """Extract content from a URL through the configured fetch cascade."""
    import trafilatura
    
    reg = get_registry()
    if reg.should_skip(url):
        logger.info(f"Skipping fortress: {url}")
        uhash = url_hash(url)
        if queue:
            queue.ack(uhash)
        try:
            _DOMAIN_PERF.record_attempt(
                domain_or_url=url,
                method="skip",
                success=False,
                char_count=0,
            )
        except Exception:
            pass
        return CrawlResult(url=url, success=False)
        
    access_strategy = reg.resolve_access_strategy(url)
    if access_strategy.rewritten_url:
        url = access_strategy.rewritten_url
    info = reg.lookup(url)

    domain = urlparse(url).netloc.lower().removeprefix("www.")
    uhash = url_hash(url)
    overlay_failure_target = (
        access_strategy.endpoint_url
        if access_strategy.source == "overlay" and (
            access_strategy.rewritten_url
            or access_strategy.method == "json_api"
            or url == access_strategy.endpoint_url
        )
        else ""
    )

    # Metrics helpers.
    # Record one crawl attempt in the domain-performance store.
    def _record_attempt(method: str, success: bool, char_count: int = 0):
        try:
            _DOMAIN_PERF.record_attempt(
                domain_or_url=url,
                method=method or "unknown",
                success=success,
                char_count=char_count,
            )
        except Exception:
            pass

    # Overlay helpers.
    # Mark one overlay endpoint failure.
    def _record_overlay_failure() -> None:
        if not overlay_failure_target:
            return
        try:
            _ENDPOINT_OVERLAY.mark_endpoint_failure(domain=access_strategy.domain or domain, endpoint_url=overlay_failure_target)
        except Exception:
            pass

    # HTML parsing helpers.
    # Parse HTML into a normalized crawl result.
    def _parse_html(html: str, src_url: str) -> CrawlResult:
        """Parse HTML through trafilatura and filter anti-bot pages."""
        text = trafilatura.extract(
            html,
            url=src_url,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
        )
        if not text or len(text) < 200:
            if metrics:
                metrics.record_parse(domain, success=False)
            return CrawlResult(url=src_url, success=False)
        if _is_antbot_text(text):
            logger.debug(f"Antbot text detected, skipping: {src_url}")
            if metrics:
                metrics.record_parse(domain, success=False)
            return CrawlResult(url=src_url, success=False)
        meta = trafilatura.extract_metadata(html)
        page_evidence = build_page_evidence(
            src_url,
            text,
            title=meta.title if meta else None,
            author=meta.author if meta else None,
            date=meta.date if meta else None,
        )
        if metrics:
            metrics.record_parse(domain, success=True)
        return CrawlResult(
            url=src_url,
            text=text,
            title=meta.title if meta else None,
            char_count=len(text),
            success=True,
            blocks=page_evidence.get("blocks", []),
            page_evidence=page_evidence,
        )

    # Check robots.txt before any fetch.
    if robots_checker:
        allowed = await robots_checker.is_allowed(url)
        if not allowed:
            logger.info(f"robots.txt blocks: {url[:70]}")
            if queue:
                queue.ack(uhash)
            _record_attempt(method="robots_blocked", success=False, char_count=0)
            _record_overlay_failure()
            return CrawlResult(url=url, success=False, method="robots_blocked")

    # [2] Per-domain rate limiting
    if rate_limiter:
        await rate_limiter.acquire(url)

    t_crawl_start = time.time()

    # Step 1: JSON API / XML sitemap.
    json_text = await _try_json_api(url, timeout=8.0)
    if json_text and len(json_text) > 200 and not _is_antbot_text(json_text):
        elapsed = time.time() - t_crawl_start
        if metrics:
            metrics.record_request(domain, status=200, latency=elapsed, bytes_=len(json_text))
            metrics.record_parse(domain, success=True)
        result = CrawlResult(url=url, text=json_text, char_count=len(json_text),
                             method="json_api", success=True)
        if queue:
            queue.ack(uhash, content_hash_val=content_hash(json_text))
        _record_attempt(method="json_api", success=True, char_count=len(json_text))
        return result

    # Step 2: HTTP cache freshness.
    if http_cache and http_cache.is_fresh(url):
        cached = http_cache.get_cached(url)
        if cached and cached.html:
            logger.debug(f"HTTPCache fresh hit: {url[:60]}")
            if metrics:
                metrics.record_cache(domain, hit=True)
                metrics.record_request(domain, status=200, latency=0.0, bytes_=cached.size_bytes)
            result = _parse_html(cached.html, url)
            if result.success:
                result.method = "http_cache"
                if queue:
                    queue.ack(uhash, content_hash_val=content_hash(cached.html))
                _record_attempt(method="http_cache", success=True, char_count=result.char_count)
                return result

    # Step 3: curl_cffi with conditional headers.
    cond_headers: Dict = {}
    if http_cache:
        cond_headers = http_cache.get_conditional_headers(url)
        if metrics and cond_headers:
            metrics.record_cache(domain, hit=False)  # cache miss (stale)

    curl_result = await _try_curl_cffi(url, timeout=min(timeout, 10.0),
                                       extra_headers=cond_headers or None)
    if curl_result is not None:
        html, status_code, resp_headers = curl_result
        elapsed = time.time() - t_crawl_start

        if status_code == 304:
            # Content did not change, so use the cache.
            logger.debug(f"304 Not Modified, using cache: {url[:60]}")
            if http_cache:
                http_cache.mark_304(url)
            if metrics:
                metrics.record_cache(domain, hit=True)
                metrics.record_request(domain, status=200, latency=elapsed)
            cached = http_cache.get_cached(url) if http_cache else None
            if cached and cached.html:
                result = _parse_html(cached.html, url)
                if result.success:
                    result.method = "http_cache_304"
                    if queue:
                        queue.ack(uhash)
                    _record_attempt(method="http_cache_304", success=True, char_count=result.char_count)
                    return result

        elif html and status_code in (200, 201, 203):
            if metrics:
                metrics.record_request(domain, status=status_code,
                                       latency=elapsed, bytes_=len(html))
            # Store the response with ETag/Last-Modified metadata.
            if http_cache:
                http_cache.store(
                    url, html,
                    status=status_code,
                    etag=resp_headers.get("ETag") or resp_headers.get("etag"),
                    last_modified=resp_headers.get("Last-Modified") or resp_headers.get("last-modified"),
                    content_type=resp_headers.get("Content-Type"),
                )
            result = _parse_html(html, url)
            if result.success:
                result.method = "curl_cffi"
                if queue:
                    queue.ack(uhash, content_hash_val=content_hash(html))
                _record_attempt(method="curl_cffi", success=True, char_count=result.char_count)
                return result

        elif status_code == 429:
            if metrics:
                metrics.record_request(domain, status=429, latency=elapsed)
            logger.warning(f"WARN 429 rate-limited in crawl: {url[:60]}")
            if queue:
                queue.nack(uhash, error="429 rate limited")
            _record_attempt(method="curl_cffi", success=False, char_count=0)
            _record_overlay_failure()
            return CrawlResult(url=url, success=False, method="rate_limited")

        elif status_code == 403:
            if metrics:
                metrics.record_request(domain, status=403, latency=elapsed)
            if queue:
                queue.nack(uhash, error="403 forbidden")

        elif status_code >= 500:
            if metrics:
                metrics.record_request(domain, status=status_code, latency=elapsed)
            if queue:
                queue.nack(uhash, error=f"{status_code} server error")

    # Step 4: Google Cache.
    if not any(x in url for x in [".json", ".xml", "/api/", "/search", "wbbasket"]):
        t_gc = time.time()
        cache_html = await _try_google_cache(url, timeout=10.0)
        if cache_html:
            if metrics:
                metrics.record_request(domain, status=200,
                                       latency=time.time() - t_gc, bytes_=len(cache_html))
            cache_result = _parse_html(cache_html, url)
            if cache_result.success:
                cache_result.method = "google_cache"
                if queue:
                    queue.ack(uhash, content_hash_val=content_hash(cache_html))
                _record_attempt(method="google_cache", success=True, char_count=cache_result.char_count)
                return cache_result

    # Step 5: Stealth Browser Swarm (Nodriver -> Camoufox).
    if not use_stealth:
        if queue:
            queue.nack(uhash, error="no_stealth_available")
        _record_attempt(method=info.method or "no_stealth", success=False, char_count=0)
        _record_overlay_failure()
        return CrawlResult(url=url, success=False)

    t_stealth = time.time()
    try:
        _stealth_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if _stealth_dir not in sys.path:
            sys.path.insert(0, _stealth_dir)

        from stealth_browser import BrowserPool
        pool = BrowserPool(
            max_concurrency=4,
            memory_threshold_percent=88.0,
            enable_nodriver=STEALTH_ENABLE_NODRIVER,
            enable_camoufox=STEALTH_ENABLE_CAMOUFOX,
        )
        stealth_result = await pool.extract(url, method_hint=info.method)
        pool._nodriver.timeout_sec = 6.0
        pool._camoufox.timeout_sec = 8.0

        if stealth_result.success and stealth_result.html:
            elapsed_s = time.time() - t_stealth
            if metrics:
                metrics.record_request(domain, status=200,
                                       latency=elapsed_s,
                                       bytes_=len(stealth_result.html))
            if http_cache:
                http_cache.store(url, stealth_result.html)
            result = _parse_html(stealth_result.html, url)
            if result.success:
                result.method = stealth_result.method
                if queue:
                    queue.ack(uhash, content_hash_val=content_hash(stealth_result.html))
                _record_attempt(method=stealth_result.method or "stealth", success=True, char_count=result.char_count)
                return result

    except asyncio.TimeoutError:
        logger.warning(f"Stealth timeout: {url}")
        if queue:
            queue.nack(uhash, error="stealth_timeout")
        _record_attempt(method="stealth", success=False, char_count=0)
    except Exception as e:
        logger.warning(f"Crawl error {url}: {e}")
        if queue:
            queue.nack(uhash, error=str(e)[:120])
        _record_attempt(method="stealth", success=False, char_count=0)

    _record_attempt(method=info.method or "crawl", success=False, char_count=0)
    _record_overlay_failure()
    return CrawlResult(url=url, success=False)

# Embedding helpers.
async def _embed_chunks(chunks: List[str]):
    """
    Vectorize chunks through the existing embedder from semantic.py.
    Run it in an executor because sentence-transformers is synchronous.
    """
    import numpy as np

    loop = asyncio.get_running_loop()

    # Thread-executor helpers.
    def _encode_sync():
        try:
            from semantic import _get_embedder, _encode
            model = _get_embedder()
            prefixed = [f"passage: {c}" for c in chunks]
            embeddings = _encode(model, prefixed, convert_to_tensor=False)
            # Ensure this is a numpy array.
            if hasattr(embeddings, "cpu"):
                embeddings = embeddings.cpu().numpy()
            return np.array(embeddings, dtype=np.float32)
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            return None

    return await loop.run_in_executor(None, _encode_sync)

# Query encoding helpers.
async def _encode_query(query: str):
    """Vectorize the query for retrieval."""
    import numpy as np

    loop = asyncio.get_running_loop()

    # Thread-executor helpers.
    def _encode_sync():
        try:
            from semantic import _get_embedder, _encode
            model = _get_embedder()
            emb = _encode(model, [f"query: {query}"], convert_to_tensor=False)
            if hasattr(emb, "cpu"):
                emb = emb.cpu().numpy()
            return np.array(emb[0], dtype=np.float32)
        except Exception as e:
            logger.error(f"Query embedding failed: {e}")
            return None

    return await loop.run_in_executor(None, _encode_sync)

# Task execution pipeline.
class ResearchTask:
    """
    Full pipeline for one background research task.

    Usage from TaskOrchestrator:
        task = ResearchTask(
            task_id="abc123",
            query="what is a Temporal workflow",
            domains=["temporal.io", "docs.temporal.io"],
            store=ephemeral_store,
        )
        summary = await task.run()
    """

    # Construction helpers.
    def __init__(
        self,
        task_id: str,
        query: str,
        domains: List[str],
        store,                           # EphemeralStore
        ttl_sec: float = 600.0,
        max_urls_per_domain: int = 3,
        max_concurrency: int = 6,
        crawl_timeout: float = 30.0,
        use_stealth: bool = True,
        use_playwright: bool = False,
        discovery_depth: int = 2,
        chunk_size: int = 700,
        chunk_overlap: int = 80,
        chunk_max_chars: int = 12000,
        min_chunk_relevance: float = 0.30,
        max_total_chunks: int = 0,
        progress_callback=None,
        # Extended architecture parameters.
        respect_robots: bool = True,
        default_rps: float = 1.0,
        http_cache_db: Optional[str] = None,
        crawl_queue_db: Optional[str] = None,
        http_cache_max_age: int = 3600,
        # Adaptive time-budget: total wall-clock budget for the whole task.
        # When > 0, BFS is limited to task_timeout_sec * bfs_budget_fraction,
        # leaving the rest for actual crawling.
        task_timeout_sec: float = 0.0,
        bfs_budget_fraction: float = 0.40,
    ):
        self.task_id = task_id
        self.query = query
        self.domains = domains
        self.store = store
        self.ttl_sec = ttl_sec
        self.max_urls_per_domain = max_urls_per_domain
        self.max_concurrency = max_concurrency
        self.crawl_timeout = crawl_timeout
        self.use_stealth = use_stealth
        self.use_playwright = use_playwright
        self.discovery_depth = max(1, int(discovery_depth))
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.chunk_max_chars = chunk_max_chars
        self.min_chunk_relevance = max(0.0, float(min_chunk_relevance))
        self.max_total_chunks = max(0, int(max_total_chunks))
        self.task_timeout_sec = max(0.0, float(task_timeout_sec))
        self.bfs_budget_fraction = max(0.05, min(0.90, float(bfs_budget_fraction)))
        self._progress = progress_callback or (lambda msg: logger.info(f"[{task_id}] {msg}"))

        # Extended architecture components.
        self._robots = RobotsChecker(
            user_agent="MCP-WebSearch/1.0 (research bot)",
            respect_robots=respect_robots,
        )
        self._rate_limiter = DomainRateLimiter(
            default_rps=default_rps,
            default_burst=3.0,
            domain_overrides=get_registry().build_rate_limiter_overrides(),
        )
        self._metrics = CrawlMetrics()
        self._http_cache = HTTPCache(
            db_path=http_cache_db or ":memory:",
            default_max_age=http_cache_max_age,
        )
        self._crawl_queue: Optional[PersistentCrawlQueue] = (
            PersistentCrawlQueue(
                db_path=crawl_queue_db,
                max_retries=2,
                retry_base_delay=5.0,
            )
            if crawl_queue_db
            else None
        )

    # Pipeline entry points.
    async def run(self) -> ResearchSummary:
        """Run the full pipeline and return the final metrics."""
        t0 = time.time()
        self._progress(f"Starting subquery: {self.query[:80]}")
        self._progress(f"Domains: {', '.join(self.domains)}")

        # Step 1: BFS frontier URL discovery.
        # Compute deadline so BFS yields to the crawl phase with enough budget left.
        bfs_deadline = 0.0
        if self.task_timeout_sec > 0:
            bfs_deadline = t0 + self.task_timeout_sec * self.bfs_budget_fraction
            self._progress(
                f"Adaptive budget: total={self.task_timeout_sec:.0f}s "
                f"bfs≤{self.task_timeout_sec * self.bfs_budget_fraction:.0f}s "
                f"crawl≥{self.task_timeout_sec * (1 - self.bfs_budget_fraction):.0f}s"
            )
        try:
            urls = await _bfs_discover_urls(
                self.domains,
                max_depth=self.discovery_depth,
                max_urls_per_domain=self.max_urls_per_domain * 3,
                fetch_timeout=8.0,
                robots_checker=self._robots,
                rate_limiter=self._rate_limiter,
                http_cache=self._http_cache,
                metrics=self._metrics,
                query=self.query,
                deadline=bfs_deadline,
            )
        except Exception as e:
            logger.warning(f"BFS discovery failed ({e}), falling back to static URLs")
            urls = _discover_urls(self.domains, depth=max(2, self.discovery_depth))
        self._progress(f"BFS discovered {len(urls)} URLs for crawling")

        # Load URLs into the persistent queue when configured.
        if self._crawl_queue:
            domain_map = {
                u: urlparse(u).netloc.lower().removeprefix("www.")
                for u in urls
            }
            added = self._crawl_queue.enqueue_batch(
                [(u, domain_map[u], 0) for u in urls]
            )
            self._progress(f"PersistentQueue queued {added} tasks")

        # Step 2: Parallel crawling.
        # Keep only URLs that still belong to the original seed domains.
        seed_domains = {
            urlparse(d).netloc.lower().removeprefix("www.")
            for d in self.domains
        }
        filtered_urls = [
            u for u in urls
            if urlparse(u).netloc.lower().removeprefix("www.") in seed_domains
        ]
        if len(filtered_urls) < len(urls):
            self._progress(
                f"Domain filter removed {len(urls) - len(filtered_urls)} foreign URLs"
            )

        crawl_results = await self._crawl_all(filtered_urls)
        successful = [r for r in crawl_results if r.success and r.text]
        self._progress(
            f"Crawling finished: {len(successful)}/{len(filtered_urls)} successful"
        )

        # Emit crawl metrics.
        metrics_report = self._metrics.format_report()
        for line in metrics_report.splitlines():
            self._progress(line)

        if not successful:
            self._progress("WARN No successful results, stopping early")
            return ResearchSummary(
                task_id=self.task_id,
                query=self.query,
                domains_requested=len(self.domains),
                urls_crawled=len(urls),
                urls_successful=0,
                elapsed_sec=time.time() - t0,
            )

        # Step 3: Chunk text with semantic.chunk_text().
        all_chunks, all_metadata = self._build_chunks(successful)
        self._progress(f"Produced {len(all_chunks)} chunks from {len(successful)} pages")

        # Step 4: Vectorize through the shared embedder.
        self._progress("Vectorizing chunks...")
        embeddings = await _embed_chunks(all_chunks)

        if embeddings is None or len(embeddings) == 0:
            self._progress("WARN Vectorization failed")
            return ResearchSummary(
                task_id=self.task_id,
                query=self.query,
                domains_requested=len(self.domains),
                urls_crawled=len(urls),
                urls_successful=len(successful),
                chunks_stored=0,
                elapsed_sec=time.time() - t0,
            )

        # Step 4.5: Filter chunks by topical relevance.
        _MIN_CHUNK_RELEVANCE = self.min_chunk_relevance
        try:
            import numpy as np
            query_emb = await _encode_query(self.query)
            if query_emb is not None:
                q = query_emb / (np.linalg.norm(query_emb) + 1e-9)
                norms = np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-9
                normed = embeddings / norms
                scores = normed @ q
                keep = scores >= _MIN_CHUNK_RELEVANCE
                n_before = len(all_chunks)
                all_chunks   = [c for c, k in zip(all_chunks, keep) if k]
                all_metadata = [m for m, k in zip(all_metadata, keep) if k]
                embeddings   = embeddings[keep]
                dropped = n_before - len(all_chunks)
                if dropped > 0:
                    self._progress(
                        f"Relevance filter removed {dropped}/{n_before} chunks"
                    )
        except Exception as e:
            logger.warning(f"Chunk relevance filter failed: {e}")

        # Step 5: Load vectors into the ephemeral store.
        await self.store.add(
            task_id=self.task_id,
            chunks=all_chunks,
            embeddings=embeddings,
            metadata=all_metadata,
            ttl_sec=self.ttl_sec,
        )

        elapsed = time.time() - t0
        self._progress(
            f"Stored {len(all_chunks)} vectors in {self.store.backend_name} "
            f"(TTL={self.ttl_sec:.0f}s). Finished in {elapsed:.1f}s!"
        )

        return ResearchSummary(
            task_id=self.task_id,
            query=self.query,
            domains_requested=len(self.domains),
            urls_crawled=len(filtered_urls),
            urls_successful=len(successful),
            chunks_stored=len(all_chunks),
            elapsed_sec=elapsed,
            backend=self.store.backend_name,
        )

    # Crawl helpers.
    async def _crawl_all(self, urls: List[str]) -> List[CrawlResult]:
        """Run parallel crawling through the persistent queue when configured."""
        queue: asyncio.Queue[str] = asyncio.Queue()
        for url in urls:
            queue.put_nowait(url)

        results: List[CrawlResult] = []
        estimated_chunks = 0
        stop_requested = False
        skipped_due_chunk_limit = 0

        async def _one(url: str) -> CrawlResult:
            return await _crawl_url(
                url,
                use_stealth=self.use_stealth,
                use_playwright=self.use_playwright,
                timeout=self.crawl_timeout,
                robots_checker=self._robots,
                rate_limiter=self._rate_limiter,
                http_cache=self._http_cache,
                metrics=self._metrics,
                queue=self._crawl_queue,
            )

        async def _worker() -> None:
            nonlocal estimated_chunks, stop_requested, skipped_due_chunk_limit
            while True:
                try:
                    url = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

                if stop_requested:
                    skipped_due_chunk_limit += 1
                    queue.task_done()
                    continue

                try:
                    result = await _one(url)
                    if result is not None:
                        results.append(result)
                        if (
                            self.max_total_chunks > 0
                            and result.success
                            and result.text
                            and not stop_requested
                        ):
                            estimated_chunks += self._estimate_result_chunk_count(result)
                            if estimated_chunks >= self.max_total_chunks:
                                stop_requested = True
                                self._progress(
                                    f"Chunk limit reached ({estimated_chunks}/{self.max_total_chunks}), "
                                    "stopping crawl intake early"
                                )
                except Exception as e:
                    logger.debug(f"Crawl error in _crawl_all: {e}")
                finally:
                    queue.task_done()

        worker_count = max(1, min(self.max_concurrency, len(urls)))
        workers = [asyncio.create_task(_worker()) for _ in range(worker_count)]
        try:
            await asyncio.wait_for(queue.join(), timeout=70.0)
        except asyncio.TimeoutError:
            self._progress("WARN Crawl timeout reached, returning partial swarm results")
        finally:
            for worker in workers:
                worker.cancel()
            await asyncio.gather(*workers, return_exceptions=True)

        if skipped_due_chunk_limit > 0:
            self._progress(
                f"Chunk-limit stop skipped {skipped_due_chunk_limit} queued URLs"
            )
        return results

    # Chunking helpers.
    def _get_chunk_text_fn(self):
        try:
            from semantic import chunk_text
            return chunk_text
        except ImportError:
            def chunk_text(text, chunk_size=500, overlap=50):
                chunks = []
                step = max(1, chunk_size - overlap)
                for i in range(0, len(text), step):
                    chunks.append(text[i:i + chunk_size])
                return chunks
            return chunk_text

    # Chunk one crawl result and return chunk/meta pairs.
    def _build_chunks_for_result(
        self,
        result: CrawlResult,
    ) -> Tuple[List[str], List[Dict]]:
        chunk_text = self._get_chunk_text_fn()
        all_chunks: List[str] = []
        all_meta: List[Dict] = []

        if not result.text:
            return all_chunks, all_meta

        used_chars = 0
        source_blocks = result.blocks or []
        for block in source_blocks:
            block_text = str(block.get("text") or "").strip()
            if not block_text:
                continue
            remaining = self.chunk_max_chars - used_chars
            if remaining <= 0:
                break
            block_text = block_text[:remaining]
            block_chunks = chunk_text(block_text, self.chunk_size, self.chunk_overlap)
            for chunk_index, chunk in enumerate(block_chunks):
                chunk = chunk.strip()
                if len(chunk) < 50:
                    continue
                all_chunks.append(chunk)
                all_meta.append({
                    "url": result.url,
                    "title": result.title or "",
                    "method": result.method,
                    "block_id": block.get("id", ""),
                    "block_type": block.get("type", "unknown"),
                    "block_chars": block.get("chars", len(block_text)),
                    "page_type": result.page_evidence.get("page_type", "unknown"),
                    "chunk_index": chunk_index,
                })
            used_chars += len(block_text)
        if source_blocks:
            return all_chunks, all_meta

        text = result.text[:self.chunk_max_chars]
        chunks = chunk_text(text, self.chunk_size, self.chunk_overlap)
        for chunk_index, chunk in enumerate(chunks):
            if len(chunk) < 50:
                continue
            all_chunks.append(chunk)
            all_meta.append({
                "url": result.url,
                "title": result.title or "",
                "method": result.method,
                "block_id": "",
                "block_type": "fallback_text",
                "block_chars": len(chunk),
                "page_type": result.page_evidence.get("page_type", "unknown"),
                "chunk_index": chunk_index,
            })

        return all_chunks, all_meta

    # Estimate how many chunks one successful page will contribute.
    def _estimate_result_chunk_count(self, result: CrawlResult) -> int:
        chunks, _ = self._build_chunks_for_result(result)
        return len(chunks)

    # Chunking helpers.
    def _build_chunks(
        self,
        results: List[CrawlResult],
    ) -> Tuple[List[str], List[Dict]]:
        """Chunk text through semantic.chunk_text() and build metadata."""
        all_chunks = []
        all_meta = []
        for result in results:
            chunks, meta = self._build_chunks_for_result(result)
            all_chunks.extend(chunks)
            all_meta.extend(meta)
        return all_chunks, all_meta
