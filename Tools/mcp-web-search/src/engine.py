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
import re
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

_trace_browsers_enabled = os.getenv("SEARCH_OVERDRIVE_TRACE_BROWSERS", "true").strip().lower() == "true"


# Write server debug output when enabled.
def _debug_log(message: str) -> None:
    if _server_debug_enabled:
        print(message, file=sys.stderr)


def _trace_browser_log(message: str) -> None:
    if _trace_browsers_enabled:
        print(message, file=sys.stderr, flush=True)

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

try:
    from content_processor import PreviewPayload, build_preview_payload, get_preview_settings, warm_preview_models
except ImportError:
    from .content_processor import PreviewPayload, build_preview_payload, get_preview_settings, warm_preview_models  # type: ignore


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
    """Fetch YouTube transcript: yt-dlp first, youtube-transcript-api as fallback."""
    import re as _re
    video_id = _youtube_video_id(url)
    if not video_id:
        return f"Error: Could not extract video ID from: {url}"

    yt_dlp_error = None

    # --- Attempt 1: yt-dlp ---
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
                yt_dlp_error = f"Video not accessible or no subtitles: {url}"
                _debug_log(f"yt-dlp download failed: {e}")
            else:
                vtt_files = _glob.glob(os.path.join(tmpdir, "*.vtt"))
                if not vtt_files:
                    yt_dlp_error = f"No subtitles available for: {url}"
                    _debug_log(f"No VTT files for {video_id}")
                else:
                    raw = open(vtt_files[0], encoding="utf-8", errors="replace").read()
                    if not raw:
                        yt_dlp_error = f"Subtitle file is empty for: {url}"
                    else:
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

                        if text_lines:
                            text = " ".join(text_lines)
                            return f"YouTube transcript (yt-dlp)\nVideo: {url}\n\n{text}"

                        yt_dlp_error = f"No text extracted from subtitles for: {url}"
    except Exception as e:
        yt_dlp_error = f"Failed to fetch transcript for {url}: {e}"
        _debug_log(f"yt-dlp failed for {video_id}: {e}")

    # --- Attempt 2: youtube-transcript-api ---
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
    if yt_dlp_error:
        return (
            f"Error: yt-dlp failed for {url}. "
            f"Fallback via youtube-transcript-api also failed. "
            f"yt-dlp detail: {yt_dlp_error}"
        )
    return f"Error: Failed to fetch transcript for {url}"


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

# Single-marker phrases that alone indicate a JS-only / no-content response.
_ANTIBOT_SINGLE = (
    "your browser does not support javascript",
    "javascript is required",
    "please enable javascript",
    "this site requires javascript",
    "you need to enable javascript",
)


# Detect anti-bot response text.
def _is_antibot(text: str) -> bool:
    t = text[:2000].lower()
    if any(m in t for m in _ANTIBOT_SINGLE):
        return True
    return sum(1 for m in _ANTIBOT_MARKERS if m in t) >= 2


# Normalize a URL for dedup/cache (strip tracking params, trailing slash).
def _normalize_url(url: str) -> str:
    from urllib.parse import urlparse as _up, urlunparse as _uu, urlencode as _ue, parse_qsl as _pqs
    _TRACKING = frozenset({
        "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
        "utm_id", "fbclid", "gclid", "msclkid", "mc_cid", "mc_eid",
        "ref", "referrer", "source", "_ga", "yclid", "ysclid",
    })
    try:
        p = _up(url)
        clean_qs = _ue([(k, v) for k, v in _pqs(p.query) if k.lower() not in _TRACKING])
        norm = _uu((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/") or "/", p.params, clean_qs, ""))
        return norm
    except Exception:
        return url


# Cheap lexical relevance score: query term overlap in title/snippet/url.
def _lexical_score(query: str, title: str, snippet: str, url: str) -> float:
    terms = _query_terms(query)
    if not terms:
        return 0.0
    from urllib.parse import urlparse as _up
    url_path = (_up(url).path or "").lower()
    title_l   = title.lower()
    snippet_l = snippet.lower()
    n = len(terms)
    title_hits   = sum(1 for t in terms if t in title_l)   / n
    snippet_hits = sum(1 for t in terms if t in snippet_l) / n
    url_hits     = sum(1 for t in terms if t in url_path)  / n
    return min(1.0, 0.6 * title_hits + 0.3 * snippet_hits + 0.1 * url_hits)


def _text_signature(text: str) -> str:
    compact = _TEXT_SIG_RE.sub(" ", (text or "").lower()).strip()
    return " ".join(compact.split())


def _preview_adds_value(snippet: str, preview: str) -> bool:
    sig_snippet = _text_signature(snippet)
    sig_preview = _text_signature(preview)
    if not sig_preview:
        return False
    if not sig_snippet:
        return True
    if sig_preview == sig_snippet:
        return False
    if sig_preview.startswith(sig_snippet) or sig_snippet.startswith(sig_preview):
        shorter = min(len(sig_preview), len(sig_snippet))
        longer = max(len(sig_preview), len(sig_snippet))
        if longer > 0 and (shorter / longer) >= 0.85:
            return False
    return True


def _query_term_match_count(query: str, *texts: str) -> int:
    terms = _query_terms(query)
    if not terms:
        return 0
    haystack = " ".join(_text_signature(text) for text in texts if text).strip()
    if not haystack:
        return 0
    return sum(1 for term in terms if term in haystack)


# Deduplicate a list of SearchResults by normalized URL, domain+title, and snippet.
def _dedup_results(results: List[SearchResult]) -> List[SearchResult]:
    seen_urls: set = set()
    seen_keys: set = set()
    out: List[SearchResult] = []
    for r in results:
        nu = _normalize_url(r.url)
        if nu in seen_urls:
            continue
        seen_urls.add(nu)
        from urllib.parse import urlparse as _up
        domain = _up(r.url).netloc.lower()
        title_key = f"{domain}||{r.title.strip().lower()[:60]}"
        # First 12 words of snippet as near-dup signature.
        snip_key = " ".join((r.snippet or "").lower().split()[:12])
        if title_key in seen_keys or (snip_key and snip_key in seen_keys):
            continue
        seen_keys.add(title_key)
        if snip_key:
            seen_keys.add(snip_key)
        out.append(r)
    return out


# In-process preview cache.
_preview_cache: dict = {}   # normalized_url -> (PreviewPayload, timestamp)

# Session anti-repeat state.
_session_urls: dict    = {}  # normalized_url -> last_shown timestamp
_session_domains: dict = {}  # domain -> shown count (rolling session)
_SESSION_URL_TTL    = 3600.0
_SESSION_DOMAIN_TTL = 3600.0


def _session_cleanup() -> None:
    """Remove stale session entries older than TTL."""
    now = time.time()
    for k in list(_session_urls.keys()):
        if now - _session_urls[k] > _SESSION_URL_TTL:
            del _session_urls[k]
    # Domain counts decay: rebuild from remaining urls.
    _session_domains.clear()
    from urllib.parse import urlparse as _up
    for u in _session_urls:
        d = _up(u).netloc.lower()
        _session_domains[d] = _session_domains.get(d, 0) + 1


def _session_penalty(normalized_url: str) -> float:
    """Return a score penalty for already-shown URLs/domains."""
    penalty = 0.0
    if normalized_url in _session_urls:
        penalty += 0.15
    from urllib.parse import urlparse as _up
    domain = _up(normalized_url).netloc.lower()
    count = _session_domains.get(domain, 0)
    if count >= 2:
        penalty += 0.08 * (count - 1)
    return min(penalty, 0.40)


def _session_update(results: List[SearchResult]) -> None:
    """Mark results as shown in session state."""
    now = time.time()
    from urllib.parse import urlparse as _up
    _session_cleanup()
    for r in results:
        nu = _normalize_url(r.url)
        _session_urls[nu] = now
        domain = _up(nu).netloc.lower()
        _session_domains[domain] = _session_domains.get(domain, 0) + 1


# Convert raw HTML into plain text.
def _html_to_text(raw_html: str) -> str:
    import re as _re

    no_js = _re.sub(r"<(script|style)[^>]*>.*?</\1>", "", raw_html, flags=_re.IGNORECASE | _re.DOTALL)
    no_js = _re.sub(r'\s+on\w+="[^"]*"', "", no_js)
    return _re.sub(r"\s{2,}", " ", _re.sub(r"<[^>]+>", " ", no_js)).strip()


# Preview fetching helpers.

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
_YACY_SEARCH_TIMEOUT = 10.0
_DDGS_SEARCH_TIMEOUT = 9.0
_TIER_TRUST_SCORES = {
    "friendly": 1.0,
    "moderate": 0.75,
    "hardened": 0.35,
    "fortress": 0.05,
    "unknown": 0.50,
}
_QUERY_STOPWORDS = {
    "the", "this", "that", "with", "from", "into", "about", "what", "which",
    "when", "where", "how", "why", "who", "does", "is", "are", "was", "were",
    "for", "and", "or", "not", "what's", "whats",
    "что", "такое", "это", "как", "зачем", "почему", "где", "когда", "кто",
    "для", "или", "про", "об", "от", "из", "на", "по", "ли", "а", "и",
}
_TEXT_SIG_RE = re.compile(r"[\W_]+", re.UNICODE)


def _query_terms(query: str) -> list[str]:
    raw_terms = [t.strip().lower() for t in (query or "").split() if len(t.strip()) > 2]
    filtered = [t for t in raw_terms if t not in _QUERY_STOPWORDS]
    return filtered or raw_terms


def _preview_settings() -> dict:
    settings = get_preview_settings()
    return {
        "preview_limit": max(0, int(settings.get("preview_limit", 10) or 0)),
        "fetch_timeout": float(settings.get("fetch_timeout", 6.0) or 6.0),
        "total_timeout": float(settings.get("total_timeout", 12.0) or 12.0),
        "concurrency": max(1, int(settings.get("concurrency", 4) or 1)),
        "mode": str(settings.get("mode", "semantic") or "semantic").lower(),
        "rerank": str(settings.get("rerank", "soft") or "soft").lower(),
        "processor": settings,
    }


def _result_domain_info(url: str):
    if _domain_registry is None:
        return None
    try:
        return _domain_registry.lookup(url)
    except Exception:
        return None


def _rank_domain_trust(result: SearchResult, payload: PreviewPayload | None) -> float:
    if payload is None or not payload.text:
        return 0.0
    info = _result_domain_info(result.url)
    tier = str(getattr(info, "tier", "unknown") or "unknown").lower()
    return _TIER_TRUST_SCORES.get(tier, _TIER_TRUST_SCORES["unknown"])


def _result_usefulness_score(
    result: SearchResult,
    payload: PreviewPayload | None,
    settings: dict,
    *,
    index: int,
    total: int,
) -> float:
    original_rank = 1.0 if total <= 1 else 1.0 - (index / max(total - 1, 1))
    active_payload = payload if payload is not None else PreviewPayload()
    query_str = str(settings.get("_query", ""))
    lex = _lexical_score(query_str, result.title or "", result.snippet or "", result.url)
    sess = _session_penalty(_normalize_url(result.url))
    score = (
        (0.25 * original_rank)
        + (0.25 * lex)
        + (0.25 * max(0.0, min(active_payload.semantic_score, 1.0)))
        + (0.15 * _rank_domain_trust(result, active_payload))
        + (0.10 * max(0.0, min(active_payload.quality_score, 1.0)))
        - sess
    )
    return max(0.0, score)


def _compact_preview_fallback(text: str) -> str:
    compact = " ".join((text or "").replace("\r", " ").replace("\n", " ").split()).strip(" -|,;")
    return compact


def _adaptive_preview_text(
    result: SearchResult,
    payload: PreviewPayload | None,
    settings: dict,
    *,
    index: int,
    total: int,
) -> str:
    usefulness = _result_usefulness_score(result, payload, settings, index=index, total=total)
    processor = settings.get("processor", {}) if isinstance(settings, dict) else {}
    max_chars = max(240, int(processor.get("output_chars", 1400) or 1400))
    min_chars = min(240, max_chars)
    source_text = _compact_preview_fallback((payload.text if payload else "") or "")
    if not source_text:
        source_text = _compact_preview_fallback(result.snippet or "")
    if not source_text:
        return ""

    # More useful sources get a larger text budget instead of a hard preview cutoff.
    ratio = max(0.12, min(usefulness, 1.0))
    char_budget = int(min_chars + ((max_chars - min_chars) * ratio))
    if usefulness < 0.16:
        char_budget = min(char_budget, 220)
    elif usefulness < 0.28:
        char_budget = min(char_budget, 420)
    preview = source_text[:char_budget].rstrip(" ,;:|-")
    if not _preview_adds_value(result.snippet or "", preview):
        return ""
    return preview


def _soft_rerank_results(
    results: List[SearchResult],
    payloads: List[PreviewPayload],
    settings: dict,
) -> tuple[List[SearchResult], List[PreviewPayload]]:
    if not results:
        return [], []
    if settings.get("mode") != "semantic" or settings.get("rerank") != "soft":
        padded = list(payloads) + [PreviewPayload() for _ in range(max(0, len(results) - len(payloads)))]
        return list(results), padded[:len(results)]

    total = len(results)
    padded = list(payloads) + [PreviewPayload() for _ in range(max(0, total - len(payloads)))]
    scored = []
    for index, result in enumerate(results):
        payload = padded[index]
        score = _result_usefulness_score(result, payload, settings, index=index, total=total)
        scored.append((score, index, result, payload))

    scored.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in scored], [item[3] for item in scored]


async def _fetch_preview_payloads(
    results: List[SearchResult],
    query: str = "",
    overrides: dict | None = None,
) -> List[PreviewPayload]:
    import aiohttp
    import math
    try:
        from config import WEB_SEARCH_PREVIEW_CACHE_ENABLED, WEB_SEARCH_PREVIEW_CACHE_TTL, WEB_SEARCH_FETCH_STEALTH, OVERDRIVE as _OVERDRIVE_PREVIEW, MIMIC_USER_AGENT as _MIMIC_USER_AGENT, OVERDRIVE_HUMAN_BEHAVIOR as _OD_HUMAN_BEHAVIOR, OVERDRIVE_PARALLEL_TIMEOUT as _OD_PARALLEL_TIMEOUT, OVERDRIVE_OCR_TIMEOUT as _OD_OCR_TIMEOUT, OVERDRIVE_BROWSER_START_DELAY as _OD_BROWSER_START_DELAY, OVERDRIVE_BROWSER_CONCURRENCY as _OD_BROWSER_CONCURRENCY, OVERDRIVE_BROWSER_FANOUT as _OD_BROWSER_FANOUT, OVERDRIVE_BROWSER_IDLE_TIMEOUT as _OD_BROWSER_IDLE_TIMEOUT, OVERDRIVE_TRACE_BROWSERS as _OD_TRACE_BROWSERS
    except ImportError:
        WEB_SEARCH_PREVIEW_CACHE_ENABLED = True
        WEB_SEARCH_PREVIEW_CACHE_TTL     = 1800
        _OVERDRIVE_PREVIEW = False
        _MIMIC_USER_AGENT = True
        _OD_HUMAN_BEHAVIOR = True
        _OD_PARALLEL_TIMEOUT = 20.0
        _OD_OCR_TIMEOUT = 30.0
        _OD_BROWSER_START_DELAY = 0.75
        _OD_BROWSER_CONCURRENCY = 4
        _OD_BROWSER_FANOUT = 4
        _OD_BROWSER_IDLE_TIMEOUT = 30.0
        _OD_TRACE_BROWSERS = True
        WEB_SEARCH_FETCH_STEALTH         = True

    settings = _preview_settings()

    # Apply caller overrides (deep mode passes higher limits, timeouts, quality profile).
    if overrides:
        for k in ("preview_limit", "fetch_timeout", "total_timeout", "concurrency"):
            if k in overrides:
                settings[k] = overrides[k]
        if "output_chars" in overrides or "min_clean_chars" in overrides:
            settings["processor"] = dict(settings["processor"])
            if "output_chars" in overrides:
                settings["processor"]["output_chars"] = overrides["output_chars"]
            if "min_clean_chars" in overrides:
                settings["processor"]["min_clean_chars"] = overrides["min_clean_chars"]

    use_camoufox: bool = bool(overrides.get("use_camoufox", False)) if overrides else False
    use_wayback:  bool = bool(overrides.get("use_wayback",  False)) if overrides else False

    targets = list(results)
    if not targets:
        return []

    now = time.time()
    sem = asyncio.Semaphore(settings["concurrency"])
    timeout = aiohttp.ClientTimeout(total=settings["fetch_timeout"])
    connector = aiohttp.TCPConnector(
        limit=settings["concurrency"] * 4,
        limit_per_host=2,
        ttl_dns_cache=120,
    )
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(None, lambda: warm_preview_models(settings["processor"]))
    except Exception:
        pass

    async def fetch_one(session: aiohttp.ClientSession, r: SearchResult) -> PreviewPayload:
        info = _result_domain_info(r.url)
        skip_check = _is_skippable(r.url)
        allow_skip_fallbacks = bool(
            _MIMIC_USER_AGENT and getattr(info, "try_preview_bot", False)
        )
        # In deep mode with camoufox, don't skip fortress domains; allow registry-managed rescue paths.
        if skip_check and not use_camoufox and not allow_skip_fallbacks:
            return PreviewPayload()

        # Check preview cache first.
        nu = _normalize_url(r.url)
        if WEB_SEARCH_PREVIEW_CACHE_ENABLED:
            cached = _preview_cache.get(nu)
            if cached and (time.time() - cached[1]) < WEB_SEARCH_PREVIEW_CACHE_TTL:
                return cached[0]

        async with sem:
            raw_html: str | None = None
            tier = str(getattr(info, "tier", "unknown") or "unknown").lower()

            async def _try_overdrive_browser_fetch() -> str | None:
                if not _OVERDRIVE_PREVIEW:
                    return None
                if _OD_TRACE_BROWSERS:
                    _trace_browser_log(f"[web_search] escalating_to_overdrive_browser url={r.url}")
                try:
                    from overdrive import read_url_overdrive as _read_url_overdrive
                except ImportError:
                    try:
                        from .overdrive import read_url_overdrive as _read_url_overdrive  # type: ignore
                    except ImportError:
                        _read_url_overdrive = None  # type: ignore
                if _read_url_overdrive is None:
                    return None
                try:
                    browser_text = await _read_url_overdrive(
                        r.url,
                        human_behavior=_OD_HUMAN_BEHAVIOR,
                        ocr_fallback=False,
                        parallel_timeout=max(float(settings["fetch_timeout"]) + 2.0, float(_OD_PARALLEL_TIMEOUT)),
                        ocr_timeout=float(_OD_OCR_TIMEOUT),
                        browser_start_delay=float(_OD_BROWSER_START_DELAY),
                        browser_concurrency=int(_OD_BROWSER_CONCURRENCY),
                        browser_fanout=int(_OD_BROWSER_FANOUT),
                        browser_idle_timeout=float(_OD_BROWSER_IDLE_TIMEOUT),
                        char_budget=max(int(settings["processor"].get("output_chars", 1400)) * 2, 4000),
                    )
                    if browser_text and not _is_antibot(browser_text):
                        if _OD_TRACE_BROWSERS:
                            _trace_browser_log(f"[web_search] overdrive_browser_success url={r.url} chars={len(browser_text)}")
                        return browser_text
                except Exception:
                    pass
                if _OD_TRACE_BROWSERS:
                    _trace_browser_log(f"[web_search] overdrive_browser_failed url={r.url}")
                return None

            # ----- Overdrive path: single call does httpx + curl_cffi + browsers in parallel -----
            if raw_html is None and _OVERDRIVE_PREVIEW:
                raw_html = await _try_overdrive_browser_fetch()
                if not raw_html:
                    return PreviewPayload()

            # ----- Non-overdrive legacy path -----
            if raw_html is None and not _OVERDRIVE_PREVIEW:
                # Deep mode: camoufox for fortress domains.
                if use_camoufox and tier == "fortress":
                    try:
                        raw_html = await _fetch_with_camoufox(r.url, timeout_sec=int(settings["fetch_timeout"]))
                    except Exception:
                        return PreviewPayload()
                    if not raw_html or _is_antibot(raw_html):
                        return PreviewPayload()

                # Tier 1: preview-bot UA probe for flagged domains.
                if raw_html is None and _MIMIC_USER_AGENT and getattr(info, "try_preview_bot", False):
                    try:
                        from preview_bot_fetcher import probe_with_preview_bots as _bot_fetch
                    except ImportError:
                        from .preview_bot_fetcher import probe_with_preview_bots as _bot_fetch  # type: ignore
                    try:
                        bot_text = await _bot_fetch(r.url, timeout=int(settings["fetch_timeout"]))
                        if bot_text and not _is_antibot(bot_text):
                            raw_html = bot_text
                    except Exception:
                        pass

                # For hardened domains use curl_cffi directly when stealth is enabled.
                if raw_html is None and WEB_SEARCH_FETCH_STEALTH and tier == "hardened":
                    try:
                        raw_html = await _fetch_with_curl_cffi(r.url, timeout=int(settings["fetch_timeout"] + 3))
                    except Exception:
                        pass

                if raw_html is None:
                    if skip_check:
                        return PreviewPayload()
                    else:
                        try:
                            async with session.get(r.url, allow_redirects=True) as resp:
                                if resp.status >= 400:
                                    return PreviewPayload()
                                content_type = (resp.headers.get("Content-Type") or "").lower()
                                if content_type and all(marker not in content_type for marker in ("html", "xml", "text")):
                                    return PreviewPayload()
                                raw_html = await resp.text(errors="replace")
                        except Exception:
                            return PreviewPayload()

                # Stealth fallback when anti-bot detected.
                if _is_antibot(raw_html):
                    if use_camoufox:
                        try:
                            raw_html = await _fetch_with_camoufox(r.url, timeout_sec=int(settings["fetch_timeout"]))
                        except Exception:
                            raw_html = None
                        if not raw_html or _is_antibot(raw_html):
                            return PreviewPayload()
                    elif WEB_SEARCH_FETCH_STEALTH:
                        try:
                            raw_html = await _fetch_with_curl_cffi(r.url, timeout=int(settings["fetch_timeout"] + 3))
                        except Exception:
                            return PreviewPayload()
                        if _is_antibot(raw_html):
                            return PreviewPayload()
                    else:
                        return PreviewPayload()

                # Wayback Machine fallback: only in deep/camoufox mode (use_wayback passed via overrides).
                if (not raw_html or _is_antibot(raw_html)) and use_wayback:
                    _wb_timeout = 30
                    try:
                        from config import WAYBACK_TIMEOUT as _WB_TO
                        _wb_timeout = _WB_TO
                    except ImportError:
                        pass
                    try:
                        wb_text = await _fetch_via_wayback(r.url, timeout=_wb_timeout)
                        if wb_text and not _is_antibot(wb_text):
                            raw_html = wb_text
                    except Exception:
                        pass

                if not raw_html:
                    return PreviewPayload()

            try:
                payload = await loop.run_in_executor(
                    None,
                    lambda: build_preview_payload(
                        r.url,
                        raw_html,
                        query=query,
                        domain_info=info,
                        settings=settings["processor"],
                    ),
                )
            except Exception:
                return PreviewPayload()

            # Store in preview cache.
            if WEB_SEARCH_PREVIEW_CACHE_ENABLED and payload.text:
                _preview_cache[nu] = (payload, time.time())
            return payload

    tasks = []
    try:
        async with aiohttp.ClientSession(
            timeout=timeout,
            connector=connector,
            headers={"User-Agent": _UA},
        ) as session:
            tasks = [asyncio.create_task(fetch_one(session, r)) for r in targets]
            effective_total_timeout = max(
                settings["total_timeout"],
                (settings["fetch_timeout"] * max(1, math.ceil(len(targets) / max(settings["concurrency"], 1)))) + 2.0,
            )
            done, pending = await asyncio.wait(tasks, timeout=effective_total_timeout)
            for task in pending:
                task.cancel()
            raw = []
            for index, task in enumerate(tasks):
                if task in done:
                    try:
                        raw.append(task.result())
                    except Exception:
                        raw.append(PreviewPayload())
                else:
                    raw.append(PreviewPayload())
    except Exception:
        return [PreviewPayload() for _ in targets]

    return [item if isinstance(item, PreviewPayload) else PreviewPayload() for item in raw]


# Fetch lightweight previews for search results.
async def _fetch_previews(results: List[SearchResult], query: str = "") -> List[str]:
    payloads = await _fetch_preview_payloads(results, query=query)
    return [payload.text for payload in payloads]


async def _prepare_results_with_previews(
    results: List[SearchResult],
    query: str = "",
    overrides: dict | None = None,
) -> tuple[List[SearchResult], List[str]]:
    if not results:
        return [], []

    # Dedup by domain+title and snippet similarity before fetching.
    results = _dedup_results(results)
    # Semantic dedup on snippets (lightweight MinHash pass).
    try:
        from deep_research.src.semantic_dedup import minhash_dedup
        results = minhash_dedup(results, lambda r: r.snippet)
    except Exception:
        pass  # datasketch not installed or import path differs
    if not results:
        return [], []

    # Resolve effective preview_limit (may be overridden by deep mode).
    base_settings = _preview_settings()
    effective_limit = int(overrides["preview_limit"]) if overrides and "preview_limit" in overrides else base_settings["preview_limit"]
    fetch_limit = min(len(results), max(effective_limit, min(24, effective_limit * 2)))

    def _cheap_score(r: SearchResult) -> float:
        lex = _lexical_score(query, r.title or "", r.snippet or "", r.url)
        info = _result_domain_info(r.url)
        tier = str(getattr(info, "tier", "unknown") or "unknown").lower()
        trust = _TIER_TRUST_SCORES.get(tier, _TIER_TRUST_SCORES["unknown"])
        return lex + trust

    fetch_indices = []
    if fetch_limit > 0:
        ranked_indices = sorted(
            range(len(results)),
            key=lambda idx: _cheap_score(results[idx]),
            reverse=True,
        )
        fetch_indices = ranked_indices[:fetch_limit]

    # Build settings dict with query for lexical scoring in rerank.
    rerank_settings = dict(base_settings)
    rerank_settings["_query"] = query

    payloads_by_index: dict[int, PreviewPayload] = {}
    if fetch_indices:
        fetched_results = [results[idx] for idx in fetch_indices]
        fetched_payloads = await _fetch_preview_payloads(fetched_results, query=query, overrides=overrides)
        for idx, payload in zip(fetch_indices, fetched_payloads):
            payloads_by_index[idx] = payload if isinstance(payload, PreviewPayload) else PreviewPayload()

    payloads = [payloads_by_index.get(idx, PreviewPayload()) for idx in range(len(results))]
    reranked_results, reranked_payloads = _soft_rerank_results(results, payloads, rerank_settings)

    scored_rows: list[tuple[SearchResult, PreviewPayload, float, float]] = []
    for index, (result, payload) in enumerate(zip(reranked_results, reranked_payloads)):
        usefulness = _result_usefulness_score(
            result,
            payload,
            rerank_settings,
            index=index,
            total=len(reranked_results),
        )
        lex = _lexical_score(query, result.title or "", result.snippet or "", result.url)
        scored_rows.append((result, payload, usefulness, lex))

    if len(scored_rows) > effective_limit:
        kept_rows: list[tuple[SearchResult, PreviewPayload, float, float]] = []
        tail_cap = max(4, effective_limit // 2)
        for index, row in enumerate(scored_rows):
            result, payload, usefulness, lex = row
            if index < effective_limit:
                kept_rows.append(row)
                continue
            query_terms = _query_terms(query)
            term_matches = _query_term_match_count(
                query,
                result.title or "",
                result.snippet or "",
                result.url,
                payload.text if payload else "",
            )
            title_url_matches = _query_term_match_count(
                query,
                result.title or "",
                result.url,
            )
            payload_signal = bool(
                (payload.text or "").strip()
                and (
                    payload.semantic_score >= 0.18
                    or payload.quality_score >= 0.25
                    or len((payload.text or "").strip()) >= 220
                )
            )
            single_term_guard_ok = True
            if len(query_terms) == 1:
                single_term_guard_ok = title_url_matches > 0
            if usefulness >= 0.28 and term_matches > 0 and single_term_guard_ok and (lex >= 0.12 or payload_signal or _is_downloadable_ext(result.url)):
                kept_rows.append(row)
            if len(kept_rows) >= effective_limit + tail_cap:
                break
        scored_rows = kept_rows

    # Update session state with shown results.
    _session_update([row[0] for row in scored_rows[:effective_limit]])

    previews = [
        _adaptive_preview_text(result, payload, rerank_settings, index=index, total=len(scored_rows))
        for index, (result, payload, _, _) in enumerate(scored_rows)
    ]
    filtered_results = [row[0] for row in scored_rows]
    previews += [""] * (len(filtered_results) - len(previews))
    return filtered_results, previews[:len(filtered_results)]


# Merge and allotment helpers.

# Merge YaCy and DDGS results proportionally.
def _proportional_merge(yacy: list, ddgs: list, cap: int) -> list:
    """Merge YaCy and DDGS results proportionally up to cap total, deduping by normalized URL."""
    yn, dn = len(yacy), len(ddgs)
    if yn == 0:
        raw = ddgs[:cap * 2]
    elif dn == 0:
        raw = yacy[:cap * 2]
    else:
        yr_take = max(1, round(cap * yn / (yn + dn)))
        dr_take = cap - yr_take
        if yr_take > yn:
            yr_take = yn
            dr_take = min(cap - yr_take, dn)
        elif dr_take > dn:
            dr_take = dn
            yr_take = min(cap - dr_take, yn)
        yr_s, dr_s = yacy[:yr_take + 4], ddgs[:dr_take + 4]
        raw = [x for pair in zip(yr_s, dr_s) for x in pair]
        raw += yr_s[len(dr_s):] + dr_s[len(yr_s):]

    # Dedup by normalized URL.
    seen: set = set()
    out = []
    for r in raw:
        nu = _normalize_url(getattr(r, "url", ""))
        if nu and nu not in seen:
            seen.add(nu)
            out.append(r)
        if len(out) >= cap:
            break
    return out


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
async def _fetch_curl_cffi_raw(u: str, timeout: int = 15) -> str:
    """Fetch URL using curl_cffi (Chrome TLS fingerprint), return raw HTML."""
    loop = asyncio.get_running_loop()

    def _do_fetch():
        from curl_cffi import requests as cffi_req
        r = cffi_req.get(u, impersonate="chrome124", timeout=timeout,
                         headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        r.raise_for_status()
        return r.text

    return await loop.run_in_executor(None, _do_fetch)


def _strip_html_to_text(raw: str) -> str:
    """Strip HTML tags and collapse whitespace into plain text."""
    import re
    raw = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', raw, flags=re.IGNORECASE | re.DOTALL)
    return re.sub(r"\s{2,}", "\n", re.sub(r"<[^>]+>", " ", raw)).strip()


async def _fetch_with_curl_cffi(u: str, timeout: int = 15) -> str:
    """Fetch URL using curl_cffi (Chrome TLS fingerprint), return text."""
    raw = await _fetch_curl_cffi_raw(u, timeout)
    return _strip_html_to_text(raw)


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


# Fetch a page via Wayback Machine (web.archive.org).
async def _fetch_via_wayback(u: str, timeout: int = 30) -> str:
    """
    Fetch a page via Wayback Machine as a last-resort fallback.

    Steps:
    1. Query CDX API to find the closest available snapshot.
    2. Download the raw snapshot using the /web/<ts>id_/<url> path
       (the `id_` flag strips the Archive.org toolbar and injected JS).
    3. Strip HTML and return plain text.

    Returns empty string on any failure.
    """
    import json as _json
    from urllib.parse import quote as _quote

    loop = asyncio.get_running_loop()

    def _do():
        import requests as _req

        # Step 1: find latest available snapshot via CDX API.
        cdx_url = (
            "https://web.archive.org/cdx/search/cdx"
            f"?url={_quote(u, safe='')}"
            "&output=json&limit=1&fl=timestamp,statuscode&filter=statuscode:200&fastLatest=true"
        )
        try:
            cdx_resp = _req.get(
                cdx_url,
                timeout=timeout,
                headers={"User-Agent": "Mozilla/5.0 (compatible; WaybackFetcher/1.0)"},
            )
            cdx_resp.raise_for_status()
            rows = cdx_resp.json()
        except Exception:
            return ""

        # rows[0] is the header ["timestamp","statuscode"], rows[1] is first result
        if not rows or len(rows) < 2:
            return ""
        ts = rows[1][0]  # e.g. "20240315123045"

        # Step 2: download the raw snapshot (id_ skips Archive.org toolbar).
        snap_url = f"https://web.archive.org/web/{ts}id_/{u}"
        try:
            snap_resp = _req.get(
                snap_url,
                timeout=timeout,
                headers={"User-Agent": "Mozilla/5.0 (compatible; WaybackFetcher/1.0)"},
                allow_redirects=True,
            )
            snap_resp.raise_for_status()
            return snap_resp.text
        except Exception:
            return ""

    raw_html = await loop.run_in_executor(None, _do)
    if not raw_html:
        return ""
    return _strip_html_to_text(raw_html)


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
