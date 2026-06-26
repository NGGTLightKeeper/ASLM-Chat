# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Model-free SERP quality signals.

Everything here is deterministic, allocation-light, and budgeted for sub-millisecond
per-source evaluation so triage can run inline with the live result stream.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from core.extract.scoring import query_terms

# --- lexical -----------------------------------------------------------------

_WORD_CACHE_MAX = 256
_pattern_cache: dict[str, re.Pattern[str]] = {}


# Compile a word-boundary pattern for a term ("rust" must not match "trust").
# Terms with non-word edges (e.g. "c++") are already normalized away by
# query_terms, so plain \b is sufficient here.
def _term_pattern(term: str) -> re.Pattern[str]:
    pattern = _pattern_cache.get(term)
    if pattern is None:
        if len(_pattern_cache) >= _WORD_CACHE_MAX:
            _pattern_cache.clear()
        pattern = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
        _pattern_cache[term] = pattern
    return pattern


# BM25-lite relevance in [0,1] over title/snippet/URL path with word-boundary
# matching. Same shape as core.extract.scoring.lexical_score, minus its substring
# false-positives ("java" in "javascript").
def lexical_score(query: str, title: str, snippet: str, url: str) -> float:
    terms = query_terms(query)
    if not terms:
        return 0.0
    url_path = (urlparse(url).path or "").replace("-", " ").replace("_", " ").replace("/", " ")
    n = len(terms)
    title_hits = sum(1 for t in terms if _term_pattern(t).search(title))
    snippet_hits = sum(1 for t in terms if _term_pattern(t).search(snippet))
    path_hits = sum(1 for t in terms if _term_pattern(t).search(url_path))
    return min(1.0, 0.6 * title_hits / n + 0.3 * snippet_hits / n + 0.1 * path_hits / n)


# --- hub / garbage detection ---------------------------------------------------

_HUB_URL_SEGMENTS = frozenset({
    "category", "categories", "tag", "tags", "topic", "topics",
    "theme", "themes", "rubric", "rubrics", "section", "sections",
    "label", "labels", "archive", "archives", "feed", "rss",
    "search", "results", "page", "index", "catalog",
})
_HUB_TITLE_PHRASES = (
    "all news", "all articles", "all posts", "news feed", "tag page",
    "category page", "topic page", "browse", "archive",
    "все новости", "последние новости", "все статьи",
)
_SKIP_TITLE_PATTERNS = frozenset({
    "login", "log in", "sign up", "signup", "sign in", "register",
    "create account", "subscribe", "404", "403", "not found",
    "access denied", "page not found", "permission denied",
})


# Penalty in [0,1] for hub/listing pages that parse into link soup, not content.
def hub_penalty(url: str, title: str, snippet: str) -> float:
    penalty = 0.0
    path = (urlparse(url).path or "").lower().strip("/")
    if set(path.split("/")) & _HUB_URL_SEGMENTS:
        penalty += 0.5
    if not path or path in {"index", "index.html", "index.php"}:
        penalty += 0.3
    title_l = (title or "").lower()
    if any(phrase in title_l for phrase in _HUB_TITLE_PHRASES):
        penalty += 0.4
    snippet = snippet or ""
    if snippet.count(" | ") >= 4 or snippet.count(" · ") >= 3 or snippet.count(" • ") >= 3:
        penalty += 0.25
    return min(penalty, 1.0)


# True for titles that scream non-content (login walls, error pages).
def is_skip_title(title: str) -> bool:
    title_l = (title or "").lower()
    return any(pattern in title_l for pattern in _SKIP_TITLE_PATTERNS)


# --- SEO-slug penalty (identity-blind) -----------------------------------------

# No domain favouritism: the ranker must not carry a list of "good" hosts — that would
# reintroduce the curated trust registry consensus was built to replace, and bias the
# system toward whoever the author hand-picked. The only domain-shaped signal we allow
# is a penalty on the *structure* of a URL, never on its identity: year-stuffed,
# heavily hyphenated slugs are a reliable SEO-content-farm tell regardless of who owns
# the domain. Authority itself comes from cross-engine consensus (see triage), which is
# earned from the live result stream, not declared here.

_SEO_SLUG_RE = re.compile(r"\b(19|20)\d{2}\b")


# Non-positive penalty for SEO-farm-shaped slugs. Identity-blind: keys only off the URL
# slug's shape (hyphen density + a year), so it generalises to any host and plays no
# favourites. Deliberately gentle — it nudges, never filters.
def seo_slug_penalty(url: str) -> float:
    last = (urlparse(url).path or "").rstrip("/").rsplit("/", 1)[-1].lower()
    if last.count("-") >= 6 and _SEO_SLUG_RE.search(last):
        return -0.06
    return 0.0


# --- dates (policy: soft signal only, never a hard filter) ---------------------

_YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")
_DATE_SIGNAL_RE = re.compile(
    r"\b(20\d{2}|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b",
    re.IGNORECASE,
)


# Years the caller explicitly wrote into the query. Only these may influence
# scoring — hard date limits are forbidden by policy (they cut good content).
def query_years(query: str) -> list[str]:
    return _YEAR_RE.findall(query or "")


# Soft year alignment: +1 when source text mentions a queried year, small negative
# when it carries other years only, 0 when it has no year signal at all.
def year_match_score(text: str, years: list[str]) -> float:
    if not years or not text:
        return 0.0
    found = set(_YEAR_RE.findall(text))
    if not found:
        return 0.0
    return 1.0 if set(years) & found else -0.3


# True when a snippet carries any date marker (slight freshness/context signal).
def has_date_signal(snippet: str) -> bool:
    return bool(_DATE_SIGNAL_RE.search(snippet or ""))


# --- query language (legacy port: services/web_search.py::infer_query_language) -

# Unicode-block counters; ≥15% of characters in-script qualifies the language.
_SCRIPT_RANGES: tuple[tuple[str, int, int], ...] = (
    ("ru", 0x0400, 0x04FF),  # Cyrillic
    ("ar", 0x0600, 0x06FF),  # Arabic
    ("he", 0x0590, 0x05FF),  # Hebrew
    ("ja", 0x3040, 0x30FF),  # Hiragana/Katakana (unambiguous Japanese)
    ("zh", 0x4E00, 0x9FFF),  # CJK Unified (zh unless Japanese kana present)
    ("ko", 0xAC00, 0xD7AF),  # Hangul
    ("th", 0x0E00, 0x0E7F),  # Thai
    ("hi", 0x0900, 0x097F),  # Devanagari
    ("el", 0x0370, 0x03FF),  # Greek
)


# Detect the dominant script of a query → 2-letter language code (default "en").
# Used to route region/language per engine (e.g. Yandex for Cyrillic queries).
def infer_query_language(query: str) -> str:
    text = str(query or "")
    if not text:
        return "en"
    threshold = max(1, len(text)) * 0.15
    counts = {lang: 0 for lang, _, _ in _SCRIPT_RANGES}
    for ch in text:
        cp = ord(ch)
        for lang, lo, hi in _SCRIPT_RANGES:
            if lo <= cp <= hi:
                counts[lang] += 1
                break
    if counts["ja"] > 0:
        counts["zh"] = 0  # kana present → the CJK block is Japanese, not Chinese
    for lang, _, _ in _SCRIPT_RANGES:
        if counts[lang] >= threshold:
            return lang
    return "en"
