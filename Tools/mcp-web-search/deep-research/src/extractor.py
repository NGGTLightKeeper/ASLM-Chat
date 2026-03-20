# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""
Deep research content extraction pipeline.

Five-stage cascade:
  1. curl_cffi (~200-800ms) as the primary Chrome-like fetcher
  2. Stealth Browser Swarm (Nodriver/Camoufox, ~3-15s) for hardened sites
  3. Playwright (~3-10s) for JavaScript-heavy pages
  4. SeleniumBase CDP (~15-20s) for Cloudflare JS challenges
  5. Early skip for domains known to be effectively inaccessible

Anti-bot detection avoids silently returning challenge pages as content.
"""

import asyncio
import hashlib
import logging
import os
import re
import warnings
from typing import Optional, Dict, Callable
from urllib.parse import urlparse

import aiohttp
warnings.filterwarnings(
    "ignore",
    message=r".*urllib3 .* doesn't match a supported version.*",
    category=Warning,
    module=r"requests",
)

try:
    from .domain_performance import get_domain_performance
except (ImportError, ValueError):
    get_domain_performance = None  # type: ignore

try:
    from .config import STEALTH_ENABLE_CAMOUFOX, STEALTH_ENABLE_NODRIVER
except (ImportError, ValueError):
    STEALTH_ENABLE_NODRIVER = False
    STEALTH_ENABLE_CAMOUFOX = True

# Domains that are skipped immediately.
HOPELESS_DOMAINS = {
    "ozon.ru", "ozon.by", "ozon.com",
    "dns-shop.ru",
    "aliexpress.ru", "aliexpress.com",
    "temu.com",
    "newegg.com",
    "banggood.com",
}

# Domains where Playwright is preferred immediately.
PLAYWRIGHT_DOMAINS = {
    "dzen.ru",
    "vk.com",
}

# Domains with structured JSON access.
REDDIT_DOMAINS = {"reddit.com", "old.reddit.com", "www.reddit.com"}

# Anti-bot page markers.
ANTBOT_MARKERS = [
    "verify you are not a bot",
    "security verification",
    "blocked by network security",
    "enable javascript and cookies",
    "checking your browser",
    "just a moment",
    "please wait while we verify",
    "performing security verification",
    "network policy",
    "you've been blocked",
    "access denied",
    "robot or human",
    "are you a robot",
]

# Error and dead-page markers.
ERROR_PAGE_MARKERS = [
    "404",
    "page not found",
    "not found",
    "not available",
    "sorry, this page",
    "the page you requested cannot be found",
    "product not found",
    "product is unavailable",
    "item is unavailable",
    "this item is no longer available",
    "product has been removed",
]

# Fast dead-page check on the response head (before heavy parsing).
FAST_DEAD_PAGE_MARKERS = [
    "404",
    "page not found",
    "not available",
]

DEFAULT_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

ALLOWED_CONTENT_TYPES = (
    "text/html",
    "application/xhtml+xml",
    "text/plain",
)

_BLOCK_MIN_CHARS = 80
_BLOCK_MAX_CHARS = 1200
_MAX_BLOCKS_PER_PAGE = 24
_BOILERPLATE_PATTERNS = (
    re.compile(
        r"\b("
        r"cookie|privacy policy|terms of service|all rights reserved|"
        r"sign in|log in|subscribe|newsletter|share this|related posts|"
        r"advertisement|sponsored|follow us|create account|register|comments"
        r")\b",
        re.IGNORECASE,
    ),
)

# TLS helpers.
def _tls_verify_enabled() -> bool:
    """
    TLS verification is ON by default.
    Set MCP_WEB_SEARCH_INSECURE_SKIP_TLS_VERIFY=1 only for debugging.
    """
    raw = os.getenv("MCP_WEB_SEARCH_INSECURE_SKIP_TLS_VERIFY", "").strip().lower()
    return raw not in {"1", "true", "yes", "on"}

# Domain routing helpers.
def _is_hopeless(url: str) -> bool:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    return any(host == d or host.endswith("." + d) for d in HOPELESS_DOMAINS)

# Domain routing helpers.
def _needs_playwright(url: str) -> bool:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    return any(host == d or host.endswith("." + d) for d in PLAYWRIGHT_DOMAINS)

# Domain routing helpers.
def _is_reddit(url: str) -> bool:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    return host in REDDIT_DOMAINS or host.endswith(".reddit.com")

# Anti-bot helpers.
def _is_antbot(text: str) -> bool:
    """Return whether the fetched text looks like an anti-bot page."""
    t = text.lower()
    return any(marker in t for marker in ANTBOT_MARKERS)

# Error detection helpers.
def _extract_error_signals(html: str) -> str:
    """Extract compact error signals from title, h1, and the page head."""
    import re

    signals = []
    title = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    if title:
        signals.append(title.group(1))

    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", html, flags=re.IGNORECASE | re.DOTALL)
    if h1:
        signals.append(h1.group(1))

    # Short fragment from the page head with HTML stripped.
    snippet = re.sub(r"<[^>]+>", " ", html[:2500])
    signals.append(snippet)

    return " ".join(" ".join(signals).lower().split())

# Error detection helpers.
def _is_error_page(html: str, text: str = "") -> bool:
    """Detect pages that look like product-not-found or generic error pages."""

    page_signals = _extract_error_signals(html)
    text_signals = " ".join(text.lower().split())[:800] if text else ""
    blob = f"{page_signals} {text_signals}".strip()
    if not blob:
        return False
    return any(marker in blob for marker in ERROR_PAGE_MARKERS)

# Error detection helpers.
def _has_fast_dead_page_marker(raw_content: str) -> bool:
    """Run a fast early dead-page check on the response head."""

    snippet = re.sub(r"<[^>]+>", " ", raw_content[:2500]).lower()
    snippet = " ".join(snippet.split())[:700]
    if not snippet:
        return False
    return any(marker in snippet for marker in FAST_DEAD_PAGE_MARKERS)


# Block normalization helpers.
def _normalize_block_text(text: str) -> str:
    return " ".join((text or "").replace(chr(0x00A0), " ").split()).strip(" -|\t\r\n")


# Block normalization helpers.
def _is_boilerplate_block(text: str) -> bool:
    """Filter blocks that are too short or match boilerplate patterns."""

    compact = _normalize_block_text(text).lower()
    if not compact:
        return True
    if len(compact) < _BLOCK_MIN_CHARS:
        return True
    return any(pattern.search(compact) for pattern in _BOILERPLATE_PATTERNS)


# Block classification helpers.
def _classify_block(raw_text: str) -> str:
    """Classify a block as title, list, narrative, or unknown."""

    raw = (raw_text or "").strip()
    if not raw:
        return "unknown"
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if len(lines) >= 2 and sum(1 for line in lines if line[:2] in {"- ", "* "}) >= max(1, len(lines) // 2):
        return "list"
    compact = _normalize_block_text(raw)
    if len(compact) <= 90 and compact[-1:] not in {".", "!", ":"}:
        return "title"
    return "narrative"


# Block classification helpers.
def _split_long_block(text: str, max_chars: int = _BLOCK_MAX_CHARS) -> list[str]:
    """Split oversized text blocks into sentence-aligned chunks."""

    compact = _normalize_block_text(text)
    if len(compact) <= max_chars:
        return [compact] if compact else []

    parts = re.split(r"(?<=[.!?])\s+", compact)
    chunks: list[str] = []
    current = ""

    for part in parts:
        part = part.strip()
        if not part:
            continue
        candidate = f"{current} {part}".strip() if current else part
        if current and len(candidate) > max_chars:
            chunks.append(current)
            current = part
        elif len(part) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            for i in range(0, len(part), max_chars):
                piece = part[i:i + max_chars].strip()
                if piece:
                    chunks.append(piece)
        else:
            current = candidate

    if current:
        chunks.append(current)
    return chunks


# Page evidence helpers.
def _guess_page_type(url: str, title: Optional[str] = None) -> str:
    """Infer a coarse page type from the URL path and title."""

    blob = f"{urlparse(url).path.lower()} {(title or '').lower()}"
    if any(token in blob for token in ("/product", "/catalog", "/item", "/offer", "/dp/")):
        return "product"
    if any(token in blob for token in ("/docs/", "/documentation", "/reference", "/manual")):
        return "docs"
    if any(token in blob for token in ("/forum/", "/thread/", "/discussion/", "reddit")):
        return "forum"
    if any(token in blob for token in ("/blog/", "/news/", "/article/", "/posts/")):
        return "article"
    return "unknown"


# Page evidence helpers.
def build_page_evidence(
    url: str,
    text: str,
    *,
    title: Optional[str] = None,
    author: Optional[str] = None,
    date: Optional[str] = None,
    method: str = "",
) -> Dict:
    """Build structured evidence blocks from extracted page text."""

    raw_blocks = re.split(r"\n\s*\n+", text or "")
    seen = set()
    blocks = []
    removed_boilerplate = 0
    removed_duplicates = 0

    # Keep stable, deduplicated blocks so downstream ranking has compact evidence.
    for raw in raw_blocks:
        block_type = _classify_block(raw)
        for piece in _split_long_block(raw):
            if _is_boilerplate_block(piece):
                removed_boilerplate += 1
                continue
            dedupe_key = piece.lower()
            if dedupe_key in seen:
                removed_duplicates += 1
                continue
            seen.add(dedupe_key)
            blocks.append(
                {
                    "id": f"b{len(blocks) + 1}",
                    "type": block_type,
                    "text": piece,
                    "chars": len(piece),
                }
            )
            if len(blocks) >= _MAX_BLOCKS_PER_PAGE:
                break
        if len(blocks) >= _MAX_BLOCKS_PER_PAGE:
            break

    return {
        "url": url,
        "domain": urlparse(url).netloc.lower(),
        "title": title,
        "author": author,
        "date": date,
        "page_type": _guess_page_type(url, title),
        "method": method,
        "blocks": blocks,
        "signals": {
            "block_count": len(blocks),
            "boilerplate_blocks_removed": removed_boilerplate,
            "duplicate_blocks_removed": removed_duplicates,
        },
    }


# HTML parsing helpers.

# HTML parsing helpers.
def _extract_text(html: str) -> Optional[str]:
    """Extract cleaned article text from HTML or return None."""

    import trafilatura
    if _is_error_page(html):
        return None
    # XML with a declaration causes lxml to raise ValueError inside trafilatura.
    # Such content is not useful HTML anyway - skip it early.
    if html.lstrip()[:6].lower().startswith("<?xml"):
        return None
    text = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=True,
        favor_precision=True,
        deduplicate=True,
        output_format="txt",
    )
    if not text or len(text) < 100:
        return None
    if _is_antbot(text):
        return None
    if _is_error_page(html, text):
        return None
    return text


# HTML parsing helpers.
def _get_metadata(html: str) -> dict:
    """Extract title, author, and date metadata from HTML."""

    import trafilatura
    meta = trafilatura.extract_metadata(html)
    return {
        "title": meta.title if meta else None,
        "author": meta.author if meta else None,
        "date": meta.date if meta else None,
    }


# HTML parsing helpers.
def _hash_content(text: str) -> str:
    """Return a short stable hash for extracted text."""

    return hashlib.sha256(text.encode()).hexdigest()[:16]


# HTML parsing helpers.
def _extract_from_html_sync(url: str, html: str, method: str) -> Optional[Dict]:
    """Parse HTML into the normalized extraction payload."""

    text = _extract_text(html)
    if not text:
        return None

    meta = _get_metadata(html)
    page_evidence = build_page_evidence(
        url,
        text,
        title=meta["title"],
        author=meta["author"],
        date=meta["date"],
        method=method,
    )
    return {
        "text": text,
        "title": meta["title"],
        "author": meta["author"],
        "date": meta["date"],
        "url": url,
        "char_count": len(text),
        "method": method,
        "blocks": page_evidence["blocks"],
        "page_evidence": page_evidence,
    }


# HTTP extraction helpers.
async def _aiohttp_extract(
    url: str,
    session: aiohttp.ClientSession,
    timeout_sec: float = 15.0,
) -> Optional[Dict]:
    """Fetch and parse a page through aiohttp."""

    verify_tls = _tls_verify_enabled()
    ssl_ctx = None if verify_tls else False

    try:
        timeout = aiohttp.ClientTimeout(total=timeout_sec)
        async with session.get(
            url,
            headers=DEFAULT_HTTP_HEADERS,
            timeout=timeout,
            ssl=ssl_ctx,
            allow_redirects=True,
        ) as resp:
            if resp.status >= 400:
                return None

            content_type = (resp.headers.get("Content-Type") or "").lower()
            if content_type and not any(t in content_type for t in ALLOWED_CONTENT_TYPES):
                return None

            html = await resp.text(errors="ignore")
            if not html:
                return None
            if _has_fast_dead_page_marker(html):
                return None
    except (aiohttp.ClientError, asyncio.TimeoutError, UnicodeDecodeError):
        return None

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _extract_from_html_sync, url, html, "aiohttp")


# Reddit JSON API helpers.

async def _reddit_extract(url: str) -> Optional[Dict]:
    """
    Reddit parser.

    It prefers the `.json` endpoint through Camoufox, but also handles the case
    where Reddit returns a full SPA page instead of raw JSON.
    """
    import re
    import json

    clean = url.split("?")[0].rstrip("/")
    json_url = clean + ".json?raw_json=1&limit=100"
    data = None
    html_text = ""

    # First try Camoufox.
    try:
        pool = _get_stealth_pool(enable_nodriver=False, enable_camoufox=True)
        if pool:
            res = await pool.extract(json_url, method_hint="camoufox")
            if res and res.success and res.html:
                html_text = res.html.strip()
                
                # Try parsing as raw Reddit API JSON first.
                if html_text.startswith("[") or html_text.startswith("{"):
                    try:
                        data = json.loads(html_text)
                    except Exception:
                        pass
                
                # Firefox JSON Viewer output and Reddit SPA pages arrive as HTML.
                if not data and "<html" in html_text.lower():
                    # Handle the legacy Firefox JSON viewer wrapper.
                    pre_match = re.search(r"<pre[^>]*>(.*?)</pre>", html_text, flags=re.IGNORECASE | re.DOTALL)
                    if pre_match:
                        import html
                        try:
                            maybe_json = html.unescape(pre_match.group(1))
                            data = json.loads(maybe_json)
                        except Exception:
                            pass
    except Exception as e:
        import logging
        logging.getLogger("extractor").debug(f"Reddit camoufox extract error: {e}")

    # If JSON parsing succeeded, normalize the JSON response.
    if isinstance(data, list) and len(data) >= 2:
        try:
            post = data[0]["data"]["children"][0]["data"]
            title = post.get("title", "")
            selftext = post.get("selftext", "").strip()
            subreddit = post.get("subreddit", "")
            author = post.get("author", "")
            
            # Collect Reddit comments recursively.
            def collect_comments(children, depth=0, max_depth=4):
                lines = []
                for child in children:
                    kind = child.get("kind")
                    d = child.get("data", {})
                    if kind == "t1":
                        body = d.get("body", "").strip()
                        c_auth = d.get("author", "")
                        if body and body not in ("[deleted]", "[removed]"):
                            lines.append(f"{'  ' * depth}u/{c_auth}: {body}")
                        replies = d.get("replies")
                        if replies and isinstance(replies, dict):
                            nested = replies.get("data", {}).get("children", [])
                            lines.extend(collect_comments(nested, depth + 1, max_depth))
                return lines
            
            comments = collect_comments(data[1]["data"]["children"])
            parts = [f"r/{subreddit}: {title}"]
            if selftext: parts.append(selftext)
            if comments: 
                parts.append("Comments:")
                parts.extend(comments[:200])
            text = "\n".join(parts)
            if len(text) > 50:
                return {"text": text, "title": title, "author": author, "url": url, "char_count": len(text), "method": "reddit_json"}
        except Exception:
            pass

    # If JSON parsing failed, extract text directly from the HTML SPA.
    if html_text and "<" in html_text:
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_text, "html.parser")
            
            post_node = soup.find("shreddit-post")
            if post_node:
                title = post_node.get("post-title") or soup.title.string or ""
                author = post_node.get("author") or ""
                subreddit = post_node.get("subreddit-prefixed-name") or ""
                
                parts = [f"{subreddit}: {title}"]
                
                # Extract the post body.
                text_body = post_node.find(attrs={"slot": "text-body"})
                if text_body:
                    parts.append(text_body.get_text(separator="\n", strip=True))
                
                # Collect comments.
                comments = []
                for comm in soup.find_all("shreddit-comment"):
                    c_auth = comm.get("author", "unknown")
                    c_body = comm.find(attrs={"slot": "comment"})
                    if c_body:
                        c_text = c_body.get_text(separator=" ", strip=True)
                        comments.append(f"u/{c_auth}: {c_text}")
                
                if comments:
                    parts.append("Comments:")
                    parts.extend(comments[:200])
                    
                text = "\n".join(parts)
                if len(text) > 50:
                    return {"text": text, "title": title, "author": author, "url": url, "char_count": len(text), "method": "reddit_html"}
        except ImportError:
            # Regex fallback when bs4 is unavailable.
            title_m = re.search(r'post-title="([^"]+)"', html_text)
            title = title_m.group(1) if title_m else ""
            if title:
                text = title + "\n"
                return {"text": text, "title": title, "author": "", "url": url, "char_count": len(text), "method": "reddit_html_regex"}
        except Exception:
            pass

    # curl_cffi fallback for older clients.
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0", "Accept": "application/json"}
    try:
        from curl_cffi import requests as curl_req
        r2 = curl_req.get(json_url, headers=headers, timeout=15, impersonate="firefox")
        if r2.status_code == 200:
            data = r2.json()
    except Exception:
        pass

    if isinstance(data, list) and len(data) >= 2:
        try:
            post = data[0]["data"]["children"][0]["data"]
            title = post.get("title", "")
            return {"text": f"r/{post.get('subreddit')}: {title}\n{post.get('selftext')}", "title": title, "author": post.get("author"), "url": url, "char_count": len(title), "method": "reddit_curl"}
        except Exception:
            pass

    return None


# Stage 1: curl_cffi.
def _curl_cffi_extract(url: str) -> Optional[Dict]:
    html = None
    verify_tls = _tls_verify_enabled()
    try:
        from curl_cffi import requests as cffi_requests
        r = cffi_requests.get(url, impersonate="chrome124", timeout=15, verify=verify_tls)
        r.raise_for_status()
        html = r.text
    except ImportError:
        import requests
        r = requests.get(url, headers=DEFAULT_HTTP_HEADERS, timeout=15, verify=verify_tls)
        r.raise_for_status()
        html = r.text
    except Exception:
        return None

    if not html:
        return None
    if _has_fast_dead_page_marker(html):
        return None

    return _extract_from_html_sync(url, html, "curl_cffi")


# Stage 2: Playwright fallback.
async def _playwright_extract(url: str, timeout_ms: int = 20000) -> Optional[str]:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return None

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            ctx = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800},
                locale="en-US",
            )
            page = await ctx.new_page()
            await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            html = await page.content()
            await browser.close()

        return _extract_text(html)
    except Exception:
        return None


# Stage 2.5: Stealth Browser Swarm (Nodriver / Camoufox).
_stealth_pool = None
_stealth_pool_opts = None
_stealth_logger = logging.getLogger("extractor.stealth")
_domain_perf_store = None


# Return the shared domain-performance store.
def _get_domain_perf_store():
    global _domain_perf_store
    if _domain_perf_store is not None:
        return _domain_perf_store
    if get_domain_performance is None:
        return None
    try:
        _domain_perf_store = get_domain_performance()
    except Exception:
        _domain_perf_store = None
    return _domain_perf_store


# Record one domain extraction attempt.
def _record_domain_attempt(url: str, method: str, success: bool, char_count: int = 0):
    store = _get_domain_perf_store()
    if store is None:
        return
    try:
        store.record_attempt(
            domain_or_url=url,
            method=method or "unknown",
            success=success,
            char_count=char_count,
        )
    except Exception:
        pass


# Return the shared stealth browser pool.
def _get_stealth_pool(
    enable_nodriver: bool = STEALTH_ENABLE_NODRIVER,
    enable_camoufox: bool = STEALTH_ENABLE_CAMOUFOX,
):
    """Lazy-initialize the shared stealth browser pool."""
    global _stealth_pool, _stealth_pool_opts
    options = (bool(enable_nodriver), bool(enable_camoufox))
    if _stealth_pool is not None and _stealth_pool_opts == options:
        return _stealth_pool
    try:
        from .stealth_browser import BrowserPool
        _stealth_pool = BrowserPool(
            max_concurrency=4,
            memory_threshold_percent=85.0,
            enable_nodriver=options[0],
            enable_camoufox=options[1],
        )
        _stealth_pool_opts = options
        _stealth_logger.info(
            f"Stealth pool initialized: "
            f"nodriver={_stealth_pool._nodriver_ready()}, "
            f"camoufox={_stealth_pool._camoufox_ready()}"
        )
        return _stealth_pool
    except Exception as e:
        _stealth_logger.debug(f"Stealth browser pool not available: {e}")
        return None


# Extract content through the stealth browser pool.
async def _stealth_extract(
    url: str,
    method_hint: Optional[str] = None,
    enable_nodriver: bool = STEALTH_ENABLE_NODRIVER,
    enable_camoufox: bool = STEALTH_ENABLE_CAMOUFOX,
) -> Optional[Dict]:
    """Extract content through the stealth browser swarm."""
    pool = _get_stealth_pool(
        enable_nodriver=enable_nodriver,
        enable_camoufox=enable_camoufox,
    )
    if pool is None:
        return None

    try:
        result = await pool.extract(url, method_hint=method_hint)
        if result.success and result.html:
            # Parse HTML through trafilatura, same as other extraction stages.
            parsed = _extract_from_html_sync(url, result.html, result.method)
            if parsed:
                return parsed
    except Exception as e:
        _stealth_logger.warning(f"Stealth extract failed for {url}: {e}")

    return None


# Stage 3: SeleniumBase CDP fallback.
def _seleniumbase_extract_sync(url: str) -> Optional[str]:
    """Synchronous SeleniumBase UC + CDP fallback for heavy JS challenges."""
    try:
        from seleniumbase import SB
    except ImportError:
        return None

    try:
        with SB(uc=True, test=True, headless=True) as sb:
            sb.activate_cdp_mode(url)
            sb.sleep(4)
            try:
                sb.uc_gui_click_captcha()
                sb.sleep(2)
            except Exception:
                pass
            html = sb.get_page_source()
        return _extract_text(html)
    except Exception:
        return None


# Run the SeleniumBase fallback in a worker thread.
async def _seleniumbase_extract(url: str) -> Optional[str]:
    """Run the synchronous SeleniumBase fallback in a worker thread."""

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _seleniumbase_extract_sync, url)


# Unified extraction helpers.
async def extract_content(
    url: str,
    min_length: int = 200,
    use_playwright: bool = False,
    use_seleniumbase: bool = False,
    use_stealth: bool = True,
    enable_nodriver: Optional[bool] = None,
    enable_camoufox: Optional[bool] = None,
    session: Optional[aiohttp.ClientSession] = None,
    request_timeout: float = 15.0,
    method_hint: Optional[str] = None,
    http_stage_timeout: float = 12.0,
    stealth_stage_timeout: float = 18.0,
    browser_stage_timeout: float = 20.0,
    selenium_stage_timeout: float = 25.0,
    progress_callback: Optional[Callable[[str, float], None]] = None,
) -> Optional[Dict]:
    """Extract content from URL with HTTP -> stealth -> browser cascade."""

    hint = (method_hint or "").strip().lower()
    nodriver_enabled = (
        STEALTH_ENABLE_NODRIVER if enable_nodriver is None else bool(enable_nodriver)
    )
    camoufox_enabled = (
        STEALTH_ENABLE_CAMOUFOX if enable_camoufox is None else bool(enable_camoufox)
    )
    non_browser_hints = {"http", "xml_feed", "json_api", "official_api"}
    allow_stealth = use_stealth and hint not in non_browser_hints
    allow_browser_fallback = (use_playwright or use_seleniumbase) and hint not in non_browser_hints
    http_stage_timeout = max(3.0, float(http_stage_timeout or request_timeout))
    stealth_stage_timeout = max(5.0, float(stealth_stage_timeout or max(request_timeout, 12.0)))
    browser_stage_timeout = max(5.0, float(browser_stage_timeout or max(request_timeout + 5.0, 20.0)))
    selenium_stage_timeout = max(5.0, float(selenium_stage_timeout or max(browser_stage_timeout + 5.0, 25.0)))

    # Validate and normalize a successful extraction payload.
    def _finalize_success(data: Optional[Dict]) -> Optional[Dict]:
        if not data:
            return None
        if int(data.get("char_count", 0)) < min_length:
            return None
        if not data.get("content_hash"):
            data["content_hash"] = _hash_content(data.get("text", ""))
        _record_domain_attempt(
            url=url,
            method=data.get("method", "unknown"),
            success=True,
            char_count=int(data.get("char_count", 0)),
        )
        return data

    # Report the current extraction stage.
    def _report_stage(stage: str, timeout_sec: float) -> None:
        if progress_callback:
            progress_callback(stage, timeout_sec)

    # Run one extraction stage under an optional timeout.
    async def _run_stage(stage: str, awaitable, timeout_sec: float):
        _report_stage(stage, timeout_sec)
        try:
            if timeout_sec <= 0:
                return await awaitable
            return await asyncio.wait_for(awaitable, timeout=timeout_sec)
        except asyncio.TimeoutError:
            _report_stage(f"{stage}:timeout", timeout_sec)
            return None

    if _is_hopeless(url):
        _record_domain_attempt(url=url, method=hint or "hopeless", success=False, char_count=0)
        return None

    if session is None:
        async with aiohttp.ClientSession(headers=DEFAULT_HTTP_HEADERS) as local_session:
            return await extract_content(
                url=url,
                min_length=min_length,
                use_playwright=use_playwright,
                use_seleniumbase=use_seleniumbase,
                use_stealth=use_stealth,
                enable_nodriver=nodriver_enabled,
                enable_camoufox=camoufox_enabled,
                session=local_session,
                request_timeout=request_timeout,
                method_hint=method_hint,
                http_stage_timeout=http_stage_timeout,
                stealth_stage_timeout=stealth_stage_timeout,
                browser_stage_timeout=browser_stage_timeout,
                selenium_stage_timeout=selenium_stage_timeout,
                progress_callback=progress_callback,
            )

    loop = asyncio.get_running_loop()

    if _is_reddit(url):
        result = await _reddit_extract(url)
        success = _finalize_success(result)
        if success:
            return success
        _record_domain_attempt(url=url, method="reddit_json", success=False, char_count=0)
        return None

    # Forced stealth-first start when hint asks for browser path.
    if allow_stealth and hint in {"camoufox", "nodriver", "stealth", "browser"}:
        result = await _run_stage(
            f"stealth:{hint}",
            _stealth_extract(
                url,
                method_hint=hint,
                enable_nodriver=nodriver_enabled,
                enable_camoufox=camoufox_enabled,
            ),
            stealth_stage_timeout,
        )
        success = _finalize_success(result)
        if success:
            return success
        _record_domain_attempt(url=url, method=hint, success=False, char_count=0)

    # Known JS-heavy domains -> browser-first branch.
    if use_playwright and _needs_playwright(url):
        text = await _run_stage("playwright", _playwright_extract(url), browser_stage_timeout)
        if text and len(text) >= min_length:
            return _finalize_success(
                {
                    "text": text,
                    "title": None,
                    "url": url,
                    "char_count": len(text),
                    "content_hash": _hash_content(text),
                    "method": "playwright",
                }
            )

        if use_seleniumbase:
            text = await _run_stage("seleniumbase", _seleniumbase_extract(url), selenium_stage_timeout)
            if text and len(text) >= min_length:
                return _finalize_success(
                    {
                        "text": text,
                        "title": None,
                        "url": url,
                        "char_count": len(text),
                        "content_hash": _hash_content(text),
                        "method": "seleniumbase",
                    }
                )

        _record_domain_attempt(url=url, method="playwright", success=False, char_count=0)
        return None

    # HTTP branch: curl_cffi then aiohttp fallback.
    result = await _run_stage("curl_cffi", loop.run_in_executor(None, _curl_cffi_extract, url), http_stage_timeout)
    success = _finalize_success(result)
    if success:
        return success
    _record_domain_attempt(url=url, method="curl_cffi", success=False, char_count=0)

    result = await _run_stage(
        "aiohttp",
        _aiohttp_extract(url=url, session=session, timeout_sec=request_timeout),
        http_stage_timeout,
    )
    success = _finalize_success(result)
    if success:
        return success
    _record_domain_attempt(url=url, method="aiohttp", success=False, char_count=0)

    # Stealth browser branch.
    if allow_stealth:
        result = await _run_stage(
            f"stealth:{hint or 'auto'}",
            _stealth_extract(
                url,
                method_hint=hint or None,
                enable_nodriver=nodriver_enabled,
                enable_camoufox=camoufox_enabled,
            ),
            stealth_stage_timeout,
        )
        success = _finalize_success(result)
        if success:
            return success
        _record_domain_attempt(url=url, method=hint or "stealth", success=False, char_count=0)

    # Browser fallbacks.
    if allow_browser_fallback and use_playwright:
        text = await _run_stage("playwright", _playwright_extract(url), browser_stage_timeout)
        if text and len(text) >= min_length:
            return _finalize_success(
                {
                    "text": text,
                    "title": None,
                    "url": url,
                    "char_count": len(text),
                    "content_hash": _hash_content(text),
                    "method": "playwright",
                }
            )
        _record_domain_attempt(url=url, method="playwright", success=False, char_count=0)

    if allow_browser_fallback and use_seleniumbase:
        text = await _run_stage("seleniumbase", _seleniumbase_extract(url), selenium_stage_timeout)
        if text and len(text) >= min_length:
            return _finalize_success(
                {
                    "text": text,
                    "title": None,
                    "url": url,
                    "char_count": len(text),
                    "content_hash": _hash_content(text),
                    "method": "seleniumbase",
                }
            )
        _record_domain_attempt(url=url, method="seleniumbase", success=False, char_count=0)

    _record_domain_attempt(url=url, method=hint or "all", success=False, char_count=0)
    return None
