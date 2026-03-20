# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

# Search result model.
from dataclasses import dataclass

# Unified search result record.
@dataclass
class SearchResult:
    url:     str   = ""
    title:   str   = ""
    snippet: str   = ""
    engine:  str   = ""
    score:   float = 0.0


# YaCy client.
import html
import sys
import os
import asyncio
import warnings

warnings.filterwarnings(
    "ignore",
    message="urllib3 .* doesn't match a supported version!",
    category=Warning,
)

import requests
from requests.auth import HTTPBasicAuth, HTTPDigestAuth
from typing import List, Optional

YACY_URL  = "http://localhost:8090"
YACY_USER = "admin"
YACY_PASS = "admin123"


# Local YaCy client.
class YaCyClient:
    # Configure YaCy connection settings.
    def __init__(self, base_url=YACY_URL, user=YACY_USER, password=YACY_PASS):
        self.base_url = base_url.rstrip("/")
        self.auth     = HTTPBasicAuth(user, password)
        self._digest  = HTTPDigestAuth(user, password)

    # Search YaCy and map the response into SearchResult objects.
    def search(self, query: str, max_results: int = 10, collection: Optional[str] = None, resource: str = "global") -> List[SearchResult]:
        params = {
            "query":          query,
            "resource":       resource,
            "maximumRecords": max_results,
            "verify":         "false",
            "contentdom":     "text",
        }
        if collection:
            params["collection"] = collection
        try:
            r = requests.get(f"{self.base_url}/yacysearch.json", params=params, auth=self.auth, timeout=10)
            if r.status_code == 401:
                r = requests.get(f"{self.base_url}/yacysearch.json", params=params, auth=self._digest, timeout=10)
            r.raise_for_status()
            data = r.json()
        except Exception:
            return []

        results = []
        for item in (data.get("channels") or [{}])[0].get("items", []):
            link = item.get("link", "")
            if link:
                results.append(SearchResult(
                    url     = link,
                    title   = html.unescape(item.get("title",       "")),
                    snippet = html.unescape(item.get("description", "")),
                    engine  = f"yacy_{resource}",
                ))
        return results


# Run YaCy search in a worker thread.
async def async_yacy_search(query: str, max_results: int = 10) -> List[SearchResult]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: YaCyClient().search(query, max_results))

# Submit one URL to YaCy indexing.
def _yacy_add_url(url: str) -> bool:
    params = {
        "crawlingstart": "",
        "crawlingURL": url,
        "crawlingDepth": "1",
        "crawlingDomMaxPages": "5",
        "indexText": "on",
        "indexMedia": "off",
        "storeHTCache": "on",
        "cachePolicy": "iffresh",
    }
    client = YaCyClient()
    try:
        r = requests.get(f"{client.base_url}/QuickCrawlLink_p.html", params=params, auth=client.auth, timeout=5)
        if r.status_code == 401:
            r = requests.get(f"{client.base_url}/QuickCrawlLink_p.html", params=params, auth=client._digest, timeout=5)
        r.raise_for_status()
        _debug_log(f"YaCy Auto-learn {url}")
        return True
    except Exception as e:
        _debug_log(f"YaCy Auto-learn failed for {url}: {e}")
        return False

# Run YaCy indexing in a worker thread.
async def async_add_to_yacy_index(url: str) -> bool:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _yacy_add_url, url)


# DDGS client.
import hashlib
import json
import logging
import random
import sqlite3
import time
from threading import Lock
from typing import Tuple

logger = logging.getLogger("ddgs_client")

# StdIO MCP servers should stay silent unless explicitly configured otherwise.
os.environ["RUST_LOG"] = os.getenv("MCP_WEB_SEARCH_RUST_LOG", "off")

try:
    from ddgs import DDGS
    from ddgs.exceptions import RatelimitException, TimeoutException, DDGSException
    _EXC = (RatelimitException, TimeoutException, DDGSException)
except ImportError:
    try:
        from duckduckgo_search import DDGS
        _EXC = (Exception,)
    except ImportError:
        DDGS  = None
        _EXC  = (Exception,)

BACKEND_PRESETS = {
    "technical":    "google,brave",
    "academic":     "google,brave",
    "general":      "auto",
    "journalistic": "auto",
    "finance":      "google,bing",
    "medical":      "google,brave",
    "ru":           "yandex,google",
}
BACKEND_FALLBACK = ["google,brave", "yandex,bing", "duckduckgo,mojeek", "auto"]


# DDGS search client.
class DDGSClient:
    # Configure DDGS runtime settings.
    def __init__(self, proxies=None, cache_db=None, cache_ttl=3600,
                 request_delay=(1.0, 3.0), timeout=15, max_retries=3):
        self.proxies       = proxies or []
        self.cache_ttl     = cache_ttl
        self.request_delay = request_delay
        self.timeout       = timeout
        self.max_retries   = max_retries
        self._blocked: dict = {}
        self._lock     = Lock()
        self._cache_db = cache_db
        if cache_db:
            self._init_cache()

    # Return one currently available proxy.
    def _get_proxy(self):
        if not self.proxies: return None
        with self._lock:
            now = time.time()
            ok  = [p for p in self.proxies if now - self._blocked.get(p, 0) > 3600]
            return random.choice(ok) if ok else None

    # Initialize the local DDGS cache.
    def _init_cache(self):
        with sqlite3.connect(self._cache_db) as c:
            c.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, data TEXT, ts REAL, ttl INT)")

    # Build a stable DDGS cache key.
    def _cache_key(self, q, **kw):
        return hashlib.sha256(f"{q.lower()}|{json.dumps(kw,sort_keys=True)}".encode()).hexdigest()

    # Load DDGS results from cache.
    def _cache_get(self, key):
        if not self._cache_db: return None
        try:
            with sqlite3.connect(self._cache_db) as c:
                row = c.execute("SELECT data,ts,ttl FROM cache WHERE key=?", (key,)).fetchone()
                if row and time.time() - row[1] < row[2]:
                    return json.loads(row[0])
        except Exception: pass
        return None

    # Store DDGS results in cache.
    def _cache_set(self, key, data):
        if not self._cache_db: return
        try:
            with sqlite3.connect(self._cache_db) as c:
                c.execute("INSERT OR REPLACE INTO cache VALUES (?,?,?,?)",
                          (key, json.dumps(data, ensure_ascii=False), time.time(), self.cache_ttl))
        except Exception: pass

    # Normalize a DDGS query string.
    @staticmethod
    def _sanitize(q: str) -> str:
        q = " ".join(q.split())
        if len(q) > 100: q = " ".join(q.split()[:10])
        return q[:120]

    # Run one synchronous DDGS search.
    def search_sync(self, query: str, max_results=10, backend="auto", region="wt-wt") -> list:
        if not DDGS: return []
        query = self._sanitize(query)
        if not query: return []

        key    = self._cache_key(query, n=max_results, b=backend, r=region)
        cached = self._cache_get(key)
        if cached is not None: return cached

        for attempt in range(self.max_retries):
            proxy = self._get_proxy()
            try:
                delay = random.uniform(*self.request_delay) if attempt == 0 else min(3*(2**attempt)+random.uniform(0,2), 60)
                time.sleep(delay)
                ddgs = DDGS(proxy=proxy, timeout=self.timeout)
                results = ddgs.text(
                    query,
                    max_results=max_results,
                    backend=backend,
                    region=region,
                ) or []
                if results: self._cache_set(key, results)
                return results
            except _EXC as e:
                logger.warning(f"DDGS attempt {attempt+1}: {e}")
            except Exception as e:
                logger.warning(f"DDGS error: {e}")
        return []

    # Convert raw DDGS rows into SearchResult objects.
    def search_results(self, query, max_results=10, backend="auto", region="wt-wt") -> List[SearchResult]:
        return [
            SearchResult(url=r.get("href",""), title=r.get("title",""),
                         snippet=r.get("body",""), engine=f"ddgs:{backend}")
            for r in self.search_sync(query, max_results, backend, region)
            if r.get("href")
        ]

    # Try multiple DDGS backends until one succeeds.
    def search_fallback(self, query, max_results=10, query_type="general", lang="en") -> List[SearchResult]:
        if lang == "ru":
            backends = ["yandex,google", "auto", "brave,bing"]
        else:
            first    = BACKEND_PRESETS.get(query_type, "auto")
            backends = [first] + [b for b in BACKEND_FALLBACK if b != first]
        for b in backends:
            r = self.search_results(query, max_results, b)
            if r: return r
        return []


_ddgs_client: Optional[DDGSClient] = None

# Return the shared DDGS client.
def _get_ddgs() -> DDGSClient:
    global _ddgs_client
    if _ddgs_client is None:
        _ddgs_client = DDGSClient(request_delay=(0.15, 0.45), timeout=8, max_retries=2)
    return _ddgs_client


# Run DDGS search in a worker thread.
async def async_ddgs_search(query: str, max_results=10, query_type="general", lang="en") -> List[SearchResult]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None,
        lambda: _get_ddgs().search_fallback(query, max_results, query_type, lang))


# Paths, logging, and configuration.
from pathlib import Path
from urllib.parse import unquote, urlparse

logging.getLogger("mcp").setLevel(logging.CRITICAL)
logging.getLogger("fastmcp").setLevel(logging.CRITICAL)
logging.getLogger("duckduckgo_search").setLevel(logging.CRITICAL)
logging.getLogger("ddgs").setLevel(logging.CRITICAL)
logging.getLogger("ddgs.http_client").setLevel(logging.CRITICAL)
logging.getLogger("urllib3").setLevel(logging.CRITICAL)
logging.getLogger("httpx").setLevel(logging.CRITICAL)
logging.getLogger("background_agent.domain_registry").setLevel(logging.CRITICAL)
logging.getLogger("endpoint_overlay").setLevel(logging.CRITICAL)
logging.getLogger("primp").setLevel(logging.CRITICAL)

_server_debug_enabled = os.getenv("MCP_WEB_SEARCH_DEBUG", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


# Write server debug output when enabled.
def _debug_log(message: str) -> None:
    if _server_debug_enabled:
        print(message, file=sys.stderr)

_HERE       = Path(__file__).resolve().parent
PROJECT_DIR = _HERE.parent
SCRIPTS_DIR = PROJECT_DIR / "deep-research" / "scripts"
OUT_DIR     = PROJECT_DIR.parent.parent / "task" / "deep-research"

DEEP_RESEARCH_DIR = PROJECT_DIR / "deep-research"

# Make deep-research importable as top-level package root (`src.config`, `src.semantic`).
if DEEP_RESEARCH_DIR.exists():
    deep_research_path = str(DEEP_RESEARCH_DIR)
    if deep_research_path not in sys.path:
        sys.path.insert(0, deep_research_path)

# Domain registry helpers.
try:
    from src.domain_registry import DomainRegistry as _DomainRegistry
    _domain_registry = _DomainRegistry()
except Exception as _e:
    _domain_registry = None


# Formatting helpers.

# Shorten a URL for display.
def _short_url(url: str, n: int = 80) -> str:
    d = unquote(url)
    if len(d) <= n: return d
    p = urlparse(url)
    return f"{p.netloc}{p.path[:40]}..."

# Extensions that can't be scraped as text but may be downloadable via import_web_file
DOWNLOADABLE_EXTS = ('.pdf', '.mp4', '.mp3', '.avi', '.mov', '.zip', '.docx', '.xlsx',
                     '.csv', '.wav', '.webm', '.mkv', '.7z', '.tar', '.gz', '.sqlite')
# Extensions that are always skipped (executables, OS-specific binaries)
SKIP_ONLY_EXTS = ('.exe', '.dmg', '.msi', '.bin', '.dll')
SKIP_EXTS  = DOWNLOADABLE_EXTS + SKIP_ONLY_EXTS
SKIP_HOSTS = ('twitter.com', 'x.com', 'vimeo.com', 'tiktok.com')
YT_HOSTS   = ('youtube.com', 'youtu.be', 'www.youtube.com', 'm.youtube.com')

# Return whether a URL points to YouTube.
def _is_youtube(url: str) -> bool:
    h = urlparse(url).netloc.lower().removeprefix("www.").removeprefix("m.")
    return h in ("youtube.com", "youtu.be")


# Extract the YouTube video id from a URL.
def _youtube_video_id(url: str) -> str | None:
    import re as _re
    patterns = [
        r"(?:v=|/v/|youtu\.be/|/embed/|/shorts/)([A-Za-z0-9_-]{11})",
    ]
    for p in patterns:
        m = _re.search(p, url)
        if m:
            return m.group(1)
    return None


# Fetch transcript text for a YouTube URL.
def _youtube_transcript(url: str) -> str:
    """Fetch YouTube transcript: youtube-transcript-api first, yt-dlp as fallback."""
    import re as _re
    video_id = _youtube_video_id(url)
    if not video_id:
        return f"Error: Could not extract video ID from: {url}"

    # --- Attempt 1: youtube-transcript-api ---
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        api = YouTubeTranscriptApi()
        langs = ["ru", "en", "uk", "de", "fr", "es"]
        transcript = None

        try:
            for lang in langs:
                try:
                    transcript = api.fetch(video_id, languages=[lang])
                    _debug_log(f"Got transcript in {lang}")
                    break
                except Exception as lang_err:
                    _debug_log(f"Language {lang} not available")
                    continue

        except Exception as e:
            _debug_log(f"youtube-transcript-api fetch error: {e}")

        if transcript:
            text_parts = []
            for e in transcript:
                if isinstance(e, dict):
                    text_parts.append(e.get("text", ""))
                else:
                    text_parts.append(getattr(e, "text", ""))
            text = " ".join(p for p in text_parts if p)
            if text:
                return f"YouTube transcript (youtube-transcript-api)\nVideo: {url}\n\n{text}"
    except Exception as e:
        _debug_log(f"youtube-transcript-api import/init failed: {e}")

    # --- Attempt 2: yt-dlp ---
    try:
        import yt_dlp, tempfile, os, glob as _glob
        with tempfile.TemporaryDirectory() as tmpdir:
            ydl_opts = {
                "skip_download": True,
                "writesubtitles": True,
                "writeautomaticsub": True,
                "subtitleslangs": ["ru", "en"],
                "subtitlesformat": "vtt",
                "outtmpl": os.path.join(tmpdir, "sub"),
                "quiet": False,
                "no_warnings": False,
                "logger": type("Logger", (), {"debug": lambda x: None, "info": lambda x: None, "warning": _debug_log, "error": _debug_log})(),
            }
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
            except Exception as e:
                _debug_log(f"yt-dlp download failed: {e}")
                return f"Error: Video not accessible or no subtitles: {url}"

            vtt_files = _glob.glob(os.path.join(tmpdir, "*.vtt"))
            if not vtt_files:
                _debug_log(f"No VTT files for {video_id}")
                return f"Error: No subtitles available for: {url}"

            raw = open(vtt_files[0], encoding="utf-8", errors="replace").read()
            if not raw:
                return f"Error: Subtitle file is empty for: {url}"

            lines = raw.splitlines()
            text_lines = []
            seen = set()
            for line in lines:
                line = line.strip()
                if not line or line.startswith("WEBVTT") or "-->" in line or _re.match(r"^\d+$", line):
                    continue
                clean = _re.sub(r"<[^>]+>", "", line).strip()
                if clean and clean not in seen:
                    seen.add(clean)
                    text_lines.append(clean)

            if not text_lines:
                return f"Error: No text extracted from subtitles for: {url}"

            text = " ".join(text_lines)
            return f"YouTube transcript (yt-dlp)\nVideo: {url}\n\n{text}"
    except Exception as e:
        _debug_log(f"yt-dlp failed for {video_id}: {e}")
        return f"Error: Failed to fetch transcript for {url}: {e}"


# Return whether a URL should be skipped for text extraction.
def _is_skippable(url: str) -> bool:
    """Returns True for URLs we can't usefully scrape (binary, video, social, fortress)."""
    u = url.lower()
    if any(u.endswith(e) or f'/{e[1:]}/' in u or f'.{e[1:]}?' in u for e in SKIP_EXTS):
        return True
    h = urlparse(url).netloc.lower()
    if any(h == s or h.endswith('.' + s) for s in SKIP_HOSTS):
        return True
    if _domain_registry is not None and _domain_registry.should_skip(url):
        return True
    return False

# Return whether a URL points to a downloadable file.
def _is_downloadable_ext(url: str) -> bool:
    """Returns True if the URL points to a downloadable file (not executable)."""
    u = url.lower().split("?")[0]
    return any(u.endswith(e) for e in DOWNLOADABLE_EXTS)

# Build a type badge for a result URL.
def _badge_type(url: str) -> str:
    u = url.lower()
    if "youtube.com" in u or "youtu.be" in u: return "VIDEO"
    if ".pdf" in u or "/pdf/" in u:           return "PDF FILE"
    if "wikipedia.org" in u:                  return "WIKI"
    if "github.com" in u:                     return "GITHUB"
    if "arxiv.org" in u:                      return "ARXIV"
    if _is_downloadable_ext(u):               return "FILE"
    return "WEB"

# Build an engine badge for a result.
def _badge_engine(engine: str) -> str:
    e = engine.lower()
    if "yacy"   in e: return "YaCy"
    if "yandex" in e: return "Yandex"
    if "brave"  in e: return "Brave"
    if "bing"   in e: return "Bing"
    return "DDGS"


_ANTIBOT_MARKERS = (
    "antibot", "challenge", "captcha", "cf-browser-verification",
    "ray id", "just a moment", "checking your browser", "please wait",
    "enable javascript", "ddos-guard", "robot or human",
)


# Detect anti-bot response text.
def _is_antibot(text: str) -> bool:
    t = text[:2000].lower()
    return sum(1 for m in _ANTIBOT_MARKERS if m in t) >= 2


# Convert raw HTML into plain text.
def _html_to_text(raw_html: str) -> str:
    import re as _re

    no_js = _re.sub(r"<(script|style)[^>]*>.*?</\1>", "", raw_html, flags=_re.IGNORECASE | _re.DOTALL)
    no_js = _re.sub(r'\s+on\w+="[^"]*"', "", no_js)
    return _re.sub(r"\s{2,}", " ", _re.sub(r"<[^>]+>", " ", no_js)).strip()


# Preview fetching helpers.

_PREVIEW_LIMIT       = 6
_PREVIEW_CHARS       = 600
_FETCH_TIMEOUT       = 4.0
_FETCH_TOTAL_TIMEOUT = 4.5
_FETCH_CONCURRENCY   = 4
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
_YACY_SEARCH_TIMEOUT = 10.0
_DDGS_SEARCH_TIMEOUT = 9.0


# Fetch lightweight previews for search results.
async def _fetch_previews(results: List[SearchResult]) -> List[str]:
    import aiohttp

    targets = results[:_PREVIEW_LIMIT]
    if not targets:
        return []

    sem       = asyncio.Semaphore(_FETCH_CONCURRENCY)
    timeout   = aiohttp.ClientTimeout(total=_FETCH_TIMEOUT)
    connector = aiohttp.TCPConnector(limit=_FETCH_CONCURRENCY * 4, limit_per_host=2, ttl_dns_cache=120)

    # Fetch one preview snippet.
    async def fetch_one(session: aiohttp.ClientSession, r: SearchResult) -> str:
        if _is_skippable(r.url):
            return ""
        async with sem:
            try:
                async with session.get(r.url, allow_redirects=True) as resp:
                    raw_html = await resp.text(errors="replace")
                    if _is_antibot(raw_html):
                        return ""
                    return _html_to_text(raw_html)[:_PREVIEW_CHARS]
            except Exception:
                return ""

    try:
        async with aiohttp.ClientSession(
            timeout=timeout, connector=connector, headers={"User-Agent": _UA},
        ) as session:
            raw = await asyncio.wait_for(
                asyncio.gather(*[fetch_one(session, r) for r in targets], return_exceptions=True),
                timeout=_FETCH_TOTAL_TIMEOUT,
            )
    except Exception:
        return [""] * len(targets)

    return [p if isinstance(p, str) else "" for p in raw]


# Merge and allotment helpers.

# Merge YaCy and DDGS results proportionally.
def _proportional_merge(yacy: list, ddgs: list, cap: int) -> list:
    """Merge YaCy and DDGS results proportionally up to cap total."""
    yn, dn = len(yacy), len(ddgs)
    if yn == 0:
        return ddgs[:cap]
    if dn == 0:
        return yacy[:cap]
    yr_take = max(1, round(cap * yn / (yn + dn)))
    dr_take = cap - yr_take
    if yr_take > yn:
        yr_take = yn
        dr_take = min(cap - yr_take, dn)
    elif dr_take > dn:
        dr_take = dn
        yr_take = min(cap - dr_take, yn)
    yr_s, dr_s = yacy[:yr_take], ddgs[:dr_take]
    merged = [x for pair in zip(yr_s, dr_s) for x in pair]
    merged += yr_s[len(dr_s):] + dr_s[len(yr_s):]
    return merged


# Distribute slots across result groups proportionally.
def _proportional_allot(found_counts: list[int], total: int) -> list[int]:
    """Distribute total slots across buckets proportional to found_counts."""
    total_found = sum(found_counts)
    if total_found == 0:
        return [0] * len(found_counts)
    allots = [max(1, round(total * fc / total_found)) if fc > 0 else 0
              for fc in found_counts]
    diff = total - sum(allots)
    indices = sorted(range(len(found_counts)), key=lambda i: found_counts[i], reverse=True)
    for i in indices:
        if diff == 0:
            break
        if diff > 0:
            add = min(diff, found_counts[i] - allots[i])
            allots[i] += add
            diff -= add
        else:
            sub = min(-diff, max(0, allots[i] - (1 if found_counts[i] > 0 else 0)))
            allots[i] -= sub
            diff += sub
    return allots


# URL parsing and fetching helpers.

# Parse a URL argument into a list.
def _parse_url_arg(url) -> list[str]:
    """Parse url argument: string, JSON list string, or list."""
    import json as _json
    if isinstance(url, str):
        s = url.strip()
        if s.startswith('['):
            try:
                parsed = _json.loads(s)
                return [u.strip() for u in parsed if isinstance(u, str)]
            except Exception:
                inner = s.strip('[]')
                return [u.strip().strip('"').strip("'") for u in inner.split(',') if u.strip()]
        return [s]
    elif isinstance(url, list):
        return [u for u in url if isinstance(u, str)]
    return []


# Fetch a Reddit thread through the JSON endpoint.
async def _fetch_reddit_json(u: str) -> str:
    """Fetch Reddit post/comments via .json endpoint using Firefox TLS fingerprint."""
    import json as _json
    from urllib.parse import urlparse as _up, urlunparse as _uu
    loop = asyncio.get_running_loop()

    p = _up(u)
    path = p.path.rstrip("/")
    if not path.endswith(".json"):
        path += ".json"
    json_url = _uu((p.scheme, p.netloc, path, "", "limit=50&depth=3", ""))

    # Perform the Reddit JSON request.
    def _do():
        from curl_cffi import requests as _r
        resp = _r.get(json_url, impersonate="firefox133", timeout=15, headers={
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
        })
        resp.raise_for_status()
        return resp.json()

    data = await loop.run_in_executor(None, _do)

    lines = []
    post_listing = data[0]["data"]["children"][0]["data"] if data else {}
    title = post_listing.get("title", "")
    selftext = post_listing.get("selftext", "")
    subreddit = post_listing.get("subreddit", "")
    author = post_listing.get("author", "")
    score = post_listing.get("score", 0)

    lines.append(f"r/{subreddit} | u/{author} | score: {score}")
    lines.append(f"# {title}")
    if selftext:
        lines.append(selftext)
    lines.append("")

    # Collect Reddit comments recursively.
    def _extract_comments(children, depth=0):
        for child in children:
            if child.get("kind") != "t1":
                continue
            d = child["data"]
            indent = "  " * depth
            body = d.get("body", "").strip()
            if body and body != "[deleted]":
                lines.append(f"{indent}[{d.get('author','?')} | +{d.get('score',0)}] {body}")
            replies = d.get("replies")
            if isinstance(replies, dict):
                _extract_comments(replies["data"]["children"], depth + 1)

    if len(data) > 1:
        _extract_comments(data[1]["data"]["children"])

    return "\n".join(lines)[:15000]


# Fetch page text through Camoufox.
async def _fetch_with_camoufox(u: str, timeout_sec: int = 30) -> str:
    """Fetch URL using camoufox (patched Firefox + anti-fingerprinting). Thread-safe."""
    import sys as _sys
    loop = asyncio.get_running_loop()

    # Run Camoufox in a dedicated thread event loop.
    def _run_in_thread():
        import asyncio as _aio
        if _sys.platform == "win32":
            _aio.set_event_loop_policy(_aio.WindowsProactorEventLoopPolicy())

        # Open the page and extract its body text.
        async def _do():
            from camoufox.async_api import AsyncCamoufox
            async with AsyncCamoufox(headless=True) as browser:
                page = await browser.new_page()
                await page.goto(u, wait_until="networkidle", timeout=timeout_sec * 1000)
                return await page.inner_text("body")

        return _aio.run(_do())

    text = await loop.run_in_executor(None, _run_in_thread)
    return text[:15000]


# Fetch page text through curl_cffi.
async def _fetch_with_curl_cffi(u: str, timeout: int = 15) -> str:
    """Fetch URL using curl_cffi (Chrome TLS fingerprint), return text."""
    import re
    loop = asyncio.get_running_loop()

    # Perform the curl_cffi request.
    def _do_fetch():
        from curl_cffi import requests as cffi_req
        r = cffi_req.get(u, impersonate="chrome124", timeout=timeout,
                         headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        r.raise_for_status()
        return r.text

    raw = await loop.run_in_executor(None, _do_fetch)
    raw = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', raw, flags=re.IGNORECASE | re.DOTALL)
    return re.sub(r"\s{2,}", "\n", re.sub(r"<[^>]+>", " ", raw)).strip()


# Fetch and normalize JSON API output.
async def _fetch_json_api(api_url: str, timeout: int = 15) -> str:
    """Fetch JSON API endpoint and return formatted text."""
    import json as _json
    loop = asyncio.get_running_loop()

    # Fetch the API response with requests.
    def _do_fetch():
        import requests as _req
        r = _req.get(api_url, timeout=timeout,
                     headers={"User-Agent": "myparser/1.0", "Accept": "application/json"})
        r.raise_for_status()
        return r.text

    try:
        text = await loop.run_in_executor(None, _do_fetch)
        try:
            obj = _json.loads(text)
            return _json.dumps(obj, ensure_ascii=False, indent=2)[:12000]
        except Exception:
            return text[:12000]
    except Exception:
        from curl_cffi import requests as cffi_req

        # Retry the API request through curl_cffi.
        def _do_curl():
            r = cffi_req.get(api_url, impersonate="chrome124", timeout=timeout,
                             headers={"Accept": "application/json"})
            r.raise_for_status()
            return r.text

        text = await loop.run_in_executor(None, _do_curl)
        try:
            obj = _json.loads(text)
            return _json.dumps(obj, ensure_ascii=False, indent=2)[:12000]
        except Exception:
            return text[:12000]


# Convert a URL into a safe slug.
def _url_to_slug(u: str) -> str:
    """Convert a URL to a safe filename slug."""
    import re as _re
    from urllib.parse import urlparse as _up
    p = _up(u)
    raw = f"{p.netloc}{p.path}".strip("/")
    slug = _re.sub(r"[^a-zA-Z0-9_-]", "_", raw)[:80]
    return slug or "page"


# Extra research pipeline.

_orchestrator = None
_ephemeral_store = None


# Return the shared task orchestrator.
def _get_orchestrator():
    global _orchestrator
    if _orchestrator is None:
        try:
            sys.path.insert(0, str(DEEP_RESEARCH_DIR))
            from background_agent import TaskOrchestrator
            _orchestrator = TaskOrchestrator(max_concurrent=4)
        except Exception as e:
            _debug_log(f"TaskOrchestrator init failed: {e}")
    return _orchestrator


# Return the shared ephemeral store.
def _get_ephemeral_store():
    global _ephemeral_store
    if _ephemeral_store is None:
        try:
            sys.path.insert(0, str(DEEP_RESEARCH_DIR))
            from background_agent import EphemeralStore
            _ephemeral_store = EphemeralStore(
                redis_url="redis://localhost:6379",
                prefer_redis=True,
                default_ttl_sec=600.0,
            )
            _ephemeral_store.start_cleanup_loop(interval_sec=60.0)
        except Exception as e:
            _debug_log(f"EphemeralStore init failed: {e}")
    return _ephemeral_store


# Run the extra background research flow.
async def _extra_research(
    query: str,
    domains: list[str],
    timeout_min: int = 10,
) -> str:
    """
    Extra mode: browser swarm scans domains in background, results go into
    ephemeral vector store, top-K relevant chunks returned via RAG, store auto-cleaned.

    query:       Research question
    domains:     List of domains to scan (["temporal.io", "docs.temporal.io"])
    timeout_min: Max time in minutes (default 10)
    """
    import uuid

    if not query.strip():
        return "Error: Empty query."
    if not domains:
        return "Error: Specify at least one domain."

    task_id = f"extra_{uuid.uuid4().hex[:8]}"
    timeout_sec = timeout_min * 60

    import sys
    import os
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    deep_res_src = os.path.join(parent_dir, "deep-research", "src")
    if deep_res_src not in sys.path:
        sys.path.insert(0, deep_res_src)

    try:
        from background_agent import ResearchTask
    except ImportError as e:
        return f"Error: Module background_agent not found. Error: {e}, Paths: {sys.path[:3]}"

    orchestrator = _get_orchestrator()
    store = _get_ephemeral_store()
    if orchestrator is None or store is None:
        return "Error: Failed to initialize Stage 2 components."

    progress_log: list = []

    # Record progress updates for the background task.
    def _progress(msg: str):
        progress_log.append(msg)
        _debug_log(f"[extra:{task_id}] {msg}")

    research_task = ResearchTask(
        task_id=task_id,
        query=query,
        domains=domains,
        store=store,
        ttl_sec=timeout_sec + 60,
        max_concurrency=6,
        use_stealth=True,
        use_playwright=False,
        progress_callback=_progress,
    )

    submitted_id = await orchestrator.submit(
        research_task.run,
        task_id=task_id,
        max_retries=1,
    )
    _progress(f"Task {submitted_id} started...")

    status = await orchestrator.wait_ready(submitted_id, timeout=timeout_sec)
    summary = orchestrator.get_result(submitted_id)

    if status.value in ("failed", "cancelled") or summary is None:
        return (
            f"Error: Task finished with status: {status.value}\n"
            + "\n".join(progress_log[-5:])
        )

    if summary.chunks_stored == 0:
        return (
            f"Warning: Scraping finished but no useful content obtained.\n"
            f"URLs: {summary.urls_crawled} checked, {summary.urls_successful} successful"
        )

    # RAG: search for top-K relevant chunks
    from background_agent.research_task import _encode_query
    query_emb = await _encode_query(query)
    if query_emb is None:
        await store.purge(task_id)
        return "Error: Query vectorization failed."

    results = await store.search(task_id, query_emb, top_k=12)

    # Immediately clean up store
    await store.purge(task_id)
    orchestrator.cleanup_old_tasks()

    if not results:
        return f"Warning: Content collected ({summary.chunks_stored} chunks), no relevant fragments found."

    header = "\n".join([
        f"Extra Research - {summary.elapsed_sec:.0f}s",
        f"Query     : {query}",
        f"Domains   : {', '.join(domains)}",
        f"URLs      : {summary.urls_successful}/{summary.urls_crawled} successful",
        f"Store     : {summary.chunks_stored} chunks -> {summary.backend} (cleaned)",
        "-" * 60,
    ])
    chunks_text = "\n\n".join(
        f"[{i+1}] score={r.score:.3f}  {r.metadata.get('url','')[:60]}\n{r.chunk}"
        for i, r in enumerate(results)
    )
    return f"{header}\n\n{chunks_text}"
