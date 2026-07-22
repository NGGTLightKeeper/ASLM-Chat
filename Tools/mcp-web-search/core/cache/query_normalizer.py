# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

from core.query.operators import has_search_operators  # noqa: F401 - compatibility export


# Compatibility vocabulary for document scoring only. Cache normalization never uses it.
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
    # Spanish
    "pas", "mais", "plus", "très", "aux", "ces", "son", "leur",
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


# Unambiguous technical spelling normalizations applied without discarding query syntax.
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


# Canonical cache key that preserves every semantic token, punctuation, repetition, and order.
def normalize_query_key(query: str) -> str:
    if not query or not query.strip():
        return ""

    lowered = query.lower()
    for token, replacement in COMPOSITE_TOKENS.items():
        lowered = lowered.replace(token, replacement)

    return " ".join(lowered.split())


# Compatibility alias used by the recent-query tracker.
def normalize_exact_query_key(query: str) -> str:
    return normalize_query_key(query)
