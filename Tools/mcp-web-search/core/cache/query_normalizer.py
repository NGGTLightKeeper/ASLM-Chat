# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""
Query normalizer: canonical form of a search query for cache-key generation.

Goal: semantically similar queries → same cache key, so results are reused
without hitting the search engine again.

Algorithm (lightweight, no external deps):
  1. Lowercase all characters
  2. Extract word tokens via Unicode-aware regex (min 2 chars)
  3. Remove multilingual stopwords
  4. Deduplicate tokens
  5. Sort alphabetically

Result: "what is python asyncio tutorial" → "asyncio python tutorial"
        "tutorial python async"          → "async python tutorial"  ← same key

Intentional trade-off: term ORDER is discarded, so "not python" and "python not"
map to the same key. This is acceptable because:
  a) "not" is a stopword and is removed anyway
  b) For queries where word order is semantically critical, the cache TTL is
     short (journalistic queries) and cache misses are acceptable

Public API
----------
QUERY_STOPWORDS         frozenset[str]    — shared by services and core
COMPOSITE_TOKENS        dict[str, str]    — tech token normalizations (e.g. ".net" → "dotnet")
normalize_query_key(q)  str               — canonical form for hashing
"""

from __future__ import annotations

import re


# ---------------------------------------------------------------------------
# Stopwords (multilingual)
# ---------------------------------------------------------------------------

QUERY_STOPWORDS: frozenset[str] = frozenset({
    # English
    "the", "this", "that", "with", "from", "into", "about", "what", "which",
    "when", "where", "how", "why", "who", "does", "is", "are", "was", "were",
    "for", "and", "or", "not", "be", "been", "has", "have", "had", "do",
    "did", "will", "would", "could", "should", "may", "might", "can",
    "its", "their", "your", "our", "my", "his", "her",
    "an", "in", "on", "at", "to", "of", "by", "as", "up",
    # Russian
    "что", "такое", "это", "как", "зачем", "почему", "где", "когда", "кто",
    "для", "или", "про", "об", "от", "из", "на", "по", "ли", "а", "и",
    "не", "но", "же", "бы", "то", "ведь", "тоже", "также",
    # German
    "der", "die", "das", "ein", "eine", "und", "ist", "mit", "von", "wie",
    "was", "wer", "für", "oder", "nicht", "dem", "den", "des", "im", "zum",
    # French
    "les", "des", "une", "qui", "que", "dans", "est", "avec", "par", "sur",
    "pas", "mais", "plus", "très", "aux", "ces", "son", "leur", "leur",
    # Spanish
    "los", "las", "una", "que", "con", "por", "para", "del", "más", "como",
    "pero", "este", "esta", "estos", "sus", "ser", "han", "hay",
    # Arabic (common function words)
    "في", "من", "إلى", "على", "هو", "هي", "ما", "لا", "أن", "كان",
    # Japanese (common particles)
    "の", "に", "は", "が", "を", "と", "で", "も", "から", "まで",
    # Chinese (common function words)
    "的", "了", "在", "是", "和", "有", "不", "也", "都", "这",
    # Korean (common particles)
    "의", "을", "를", "이", "가", "에", "와", "과", "도", "은", "는",
})


# ---------------------------------------------------------------------------
# Normalizer
# ---------------------------------------------------------------------------

_WORD_RE = re.compile(r"\w+", re.UNICODE)

COMPOSITE_TOKENS: dict[str, str] = {
    "c++": "cpp",
    "c#": "csharp",
    "f#": "fsharp",
    "r&d": "rnd",
    "at&t": "att",
    "node.js": "nodejs",
    "vue.js": "vuejs",
    "next.js": "nextjs",
    "nuxt.js": "nuxtjs",
    ".net": "dotnet",
    "asp.net": "aspnet",
    ".env": "dotenv",
}


def normalize_query_key(query: str) -> str:
    """Return the canonical cache key for *query*.

    Strips stopwords, deduplicates, sorts terms alphabetically.
    Falls back to ``query.strip().lower()`` when normalization produces an
    empty string (e.g. a query that consists entirely of stopwords).
    """
    if not query or not query.strip():
        return ""

    lowered = query.lower()
    # Replace known composite tokens before applying \w+ regex so that
    # "C#" isn't reduced to empty and "C++" isn't reduced to "c".
    for token, replacement in COMPOSITE_TOKENS.items():
        lowered = lowered.replace(token, replacement)

    tokens = _WORD_RE.findall(lowered)
    content = sorted({t for t in tokens if len(t) >= 2 and t not in QUERY_STOPWORDS})

    # If every term was a stopword, fall back to lowercased original so the
    # query still gets a unique (exact) key rather than collapsing to "".
    return " ".join(content) if content else lowered.strip()
