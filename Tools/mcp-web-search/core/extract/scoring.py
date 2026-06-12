# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import re
from urllib.parse import urlparse

from core.cache.query_normalizer import QUERY_STOPWORDS as _QUERY_STOPWORDS, COMPOSITE_TOKENS as _COMPOSITE_TOKENS


_PUNCT_STRIP = "?!.,;:\"'()[]{}<>@#"


# Tokenise query into meaningful terms (stopwords removed when possible).
def query_terms(query: str) -> list[str]:
    raw = []
    for t in (query or "").split():
        tl = t.lower()
        # Composite tokens (e.g. ".NET", "C#") must be substituted before
        # punct-strip so ".NET".strip(…) → "net" false-match doesn't happen.
        if tl in _COMPOSITE_TOKENS:
            raw.append(_COMPOSITE_TOKENS[tl])
        else:
            stripped = tl.strip(_PUNCT_STRIP)
            if stripped:
                raw.append(stripped)
    raw = [t for t in raw if len(t) > 2]
    filtered = [t for t in raw if t not in _QUERY_STOPWORDS]
    return filtered or raw


# BM25-lite relevance score in [0, 1] from title, snippet, and URL path.
def lexical_score(query: str, title: str, snippet: str, url: str) -> float:
    terms = query_terms(query)
    if not terms:
        return 0.0
    url_path = (urlparse(url).path or "").lower()
    title_l = title.lower()
    snippet_l = snippet.lower()
    n = len(terms)
    return min(
        1.0,
        0.6 * sum(1 for t in terms if t in title_l) / n
        + 0.3 * sum(1 for t in terms if t in snippet_l) / n
        + 0.1 * sum(1 for t in terms if t in url_path) / n,
    )


# Keep highest entity-density paragraphs via GliNER; fall back to head-truncation.
def densify_text_gliner(text: str, output_chars: int = 3_000) -> str:
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    if not paragraphs:
        return text[:output_chars]

    try:
        from core.extract.gliner_wrapper import is_gliner_available, score_entity_density

        if not is_gliner_available():
            raise ImportError
        scores = score_entity_density(paragraphs)
        ranked = sorted(
            zip(scores, range(len(paragraphs)), paragraphs),
            key=lambda t: t[0],
            reverse=True,
        )
        kept: list[tuple[int, str]] = []
        total = 0
        for _score, idx, para in ranked:
            if total >= output_chars:
                break
            kept.append((idx, para))
            total += len(para)
        kept.sort(key=lambda t: t[0])
        result_text = "\n\n".join(p for _, p in kept)
    except Exception:
        result_text = text[:output_chars].rsplit("\n", 1)[0]

    if len(result_text) > output_chars:
        result_text = result_text[:output_chars].rsplit("\n", 1)[0] + "\n[...densified]"
    return result_text
