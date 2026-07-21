# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import re


# Multilingual stopwords stripped before cache-key hashing.
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

_WORD_RE = re.compile(r"\w+", re.UNICODE)

# Tech token normalizations applied before word-token extraction (e.g. ".net" → "dotnet").
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


# Search operators that change a query's meaning and must NOT be collapsed by the
# token-sort cache key. When present, the cache uses the strict order-preserving key so a
# refined directive query can't collide with a differently-meaning one.
_OPERATOR_RE = re.compile(
    r'(?:^|\s)(?:-?site:|filetype:|intitle:|inurl:|before:|after:|")'
    r'|(?:^|\s)OR(?:\s|$)|(?:^|\s)-\w',
    re.IGNORECASE,
)


# True when the query carries a meaning-changing search operator.
def has_search_operators(query: str) -> bool:
    return bool(_OPERATOR_RE.search(query or ""))


# Canonical cache key: lowercase, stopwords removed, terms sorted (order discarded).
def normalize_query_key(query: str) -> str:
    if not query or not query.strip():
        return ""

    lowered = query.lower()
    for token, replacement in COMPOSITE_TOKENS.items():
        lowered = lowered.replace(token, replacement)

    tokens = _WORD_RE.findall(lowered)
    content = sorted({t for t in tokens if len(t) >= 2 and t not in QUERY_STOPWORDS})

    return " ".join(content) if content else lowered.strip()


# Order-preserving canonical query string for strict cache keys.
def normalize_exact_query_key(query: str) -> str:
    if not query or not query.strip():
        return ""

    lowered = query.lower()
    for token, replacement in COMPOSITE_TOKENS.items():
        lowered = lowered.replace(token, replacement)

    return " ".join(lowered.split())
