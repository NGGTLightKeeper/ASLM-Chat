# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""
Per-content-type tuning profiles for the deep research pipeline.

Different content domains have very different dedup, quality, verbosity,
and source-type requirements.

Architecture
------------
ContentProfile holds only the fields that DIFFER from the base ResearchConfig
defaults.  Missing fields are left as-is so depth presets still dominate.

apply_content_profile(state) reads state.query_type (set by plan.run_plan) and
patches state.config in-place.  Call once, immediately after run_plan succeeds.

Recognised query_type values (from plan.classify_query):
    technical, academic, medical, finance, journalistic,
    shopping, troubleshooting, forum, general

Any unknown type falls back to "general" (no-op — defaults stay).

Source-type filtering
---------------------
source_type_weights is an optional dict[str, float] applied as a multiplier to
relevance_score in harvest._build_source().  Keys are source types returned by
classify_source_type():

    "reddit"   — reddit.com
    "forum"    — Stack Overflow, stackexchange, quora, community/forum/discuss subdomains
    "academic" — arxiv, pubmed, .edu, researchgate, nature, ieee, acm, doi.org, etc.
    "docs"     — docs.*, readthedocs, developer.*, /docs/ path, devdocs.io
    "blog"     — medium.com, substack.com, blogspot.*, wordpress.*, /blog/ path, dev.to
    "news"     — major news domains detected by domain suffix patterns
    "other"    — anything that doesn't match the above

Missing keys default to 1.0 (no adjustment).  Use "other" as an explicit
catch-all weight if you want a non-1.0 default for unclassified sources.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

from services.deep_research.models import ResearchState


# ---------------------------------------------------------------------------
# Source-type URL classifier
# ---------------------------------------------------------------------------

_ACADEMIC_DOMAINS = frozenset({
    "arxiv.org", "pubmed.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov",
    "researchgate.net", "scholar.google.com", "semanticscholar.org",
    "doi.org", "springer.com", "nature.com", "sciencedirect.com",
    "ieee.org", "acm.org", "biorxiv.org", "medrxiv.org",
    "plos.org", "frontiersin.org", "mdpi.com", "wiley.com",
    "tandfonline.com", "jstor.org", "nih.gov", "who.int",
})

_FORUM_DOMAINS = frozenset({
    "stackoverflow.com", "stackexchange.com", "superuser.com",
    "serverfault.com", "askubuntu.com", "unix.stackexchange.com",
    "math.stackexchange.com", "quora.com", "answers.yahoo.com",
})

_BLOG_DOMAINS = frozenset({
    "medium.com", "substack.com", "dev.to", "hashnode.dev",
    "hackernoon.com", "towardsdatascience.com", "freecodecamp.org",
})

_NEWS_DOMAIN_PATTERNS = re.compile(
    r"""(?:
        bbc\.(?:com|co\.uk) | cnn\.com | reuters\.com | apnews\.com |
        theguardian\.com | nytimes\.com | washingtonpost\.com |
        bloomberg\.com | techcrunch\.com | theverge\.com | wired\.com |
        ars(?:technica)?\.com | zdnet\.com | engadget\.com |
        forbes\.com | businessinsider\.com | time\.com |
        wsj\.com | ft\.com | economist\.com | axios\.com
    )""",
    re.VERBOSE | re.IGNORECASE,
)


def classify_source_type(url: str) -> str:
    """Return a coarse source-type label for the given URL.

    Labels: "reddit", "forum", "academic", "docs", "blog", "news", "other"
    """
    if not url:
        return "other"
    try:
        parsed = urlparse(url)
        host = parsed.netloc.lower().lstrip("www.")
        path = parsed.path.lower()
    except Exception:
        return "other"

    if host == "reddit.com" or host.endswith(".reddit.com"):
        return "reddit"

    if host in _FORUM_DOMAINS or any(seg in host for seg in ("forum", "forums", "community", "discuss", "board")):
        return "forum"

    if host in _ACADEMIC_DOMAINS or host.endswith(".edu") or ".edu/" in url:
        return "academic"

    # Docs: dedicated docs subdomain or /docs/ path
    if (
        host.startswith("docs.") or host.startswith("developer.")
        or host.startswith("documentation.")
        or host == "devdocs.io"
        or "readthedocs.io" in host
        or "readthedocs.org" in host
        or re.search(r"^/docs?/", path)
    ):
        return "docs"

    if (
        host in _BLOG_DOMAINS
        or host.endswith(".blogspot.com")
        or host.endswith(".wordpress.com")
        or re.search(r"^/blog/", path)
    ):
        return "blog"

    if _NEWS_DOMAIN_PATTERNS.search(host):
        return "news"

    return "other"


# ---------------------------------------------------------------------------
# Profile dataclass
# ---------------------------------------------------------------------------

@dataclass
class ContentProfile:
    """
    Overrides applied on top of the depth-preset ResearchConfig.

    Fields that are None mean "keep whatever the depth preset set".
    """

    # --- Dedup ---
    # MinHash: removes near-exact text copies.
    #   Higher threshold = only remove very close duplicates (keep more variety).
    #   Lower threshold  = remove moderately similar texts too (stricter dedup).
    minhash_threshold: Optional[float] = None

    # Embedding cosine sim: removes semantically near-identical docs.
    #   Higher threshold = only remove near-identical docs (keep more variety).
    #   Lower threshold  = also remove "same story, different wording" (stricter).
    embedding_threshold: Optional[float] = None

    # GLiNER min named-entity density required to keep a source.
    #   Higher = stricter filter (drop low-entity content like fluff/ads).
    min_entity_density: Optional[int] = None

    # --- Synthesis ---
    # Chars per source block fed into synthesis prompt.
    #   Higher = more context per source (expensive but richer).
    synthesis_char_budget_per_source: Optional[int] = None

    # Minimum heuristic quality score [0,1] to include a source in synthesis.
    #   Higher = stricter quality gate (fewer but better sources).
    synthesis_min_source_quality: Optional[float] = None

    # --- Harvest ---
    # Max chars extracted per source during harvest (relevant_chunks extraction).
    #   Higher = more content per source block.
    harvest_relevant_chunks_max_chars: Optional[int] = None

    # --- Reflection ---
    # Max chars per snippet shown to LLM during reflection gap-detection.
    #   Higher = more context per source for the reflection LLM.
    reflection_snippet_char_limit: Optional[int] = None

    # --- Source-type filtering ---
    # Per-source-type relevance multipliers applied in harvest._build_source().
    # Keys: "reddit", "forum", "academic", "docs", "blog", "news", "other"
    # Missing keys → 1.0 (no adjustment).
    # Use "other" as an explicit default for unclassified domains.
    source_type_weights: Optional[dict[str, float]] = None


# ---------------------------------------------------------------------------
# Profile registry
# ---------------------------------------------------------------------------

_PROFILES: dict[str, ContentProfile] = {

    # -----------------------------------------------------------------------
    # Technical documentation, code, APIs, infra
    # Docs and academic sources are authoritative; forums and Reddit are noisy.
    # -----------------------------------------------------------------------
    "technical": ContentProfile(
        minhash_threshold=0.80,          # only remove near-exact copies (default 0.70)
        embedding_threshold=0.88,        # allow semantically similar docs (default 0.93)
        min_entity_density=2,
        synthesis_char_budget_per_source=3500,  # code + prose need room (default 2000)
        synthesis_min_source_quality=0.45,      # terse API refs still useful (default 0.55)
        harvest_relevant_chunks_max_chars=4000,
        reflection_snippet_char_limit=350,
        source_type_weights={
            "docs":     1.15,
            "academic": 1.05,
            "blog":     0.80,
            "forum":    0.60,
            "reddit":   0.55,
        },
    ),

    # -----------------------------------------------------------------------
    # Academic research: papers, studies, datasets, arxiv
    # Peer-reviewed sources are gold; user-generated content strongly penalised.
    # -----------------------------------------------------------------------
    "academic": ContentProfile(
        minhash_threshold=0.82,          # allow similar-methodology papers
        embedding_threshold=0.86,        # different papers on same topic = good
        min_entity_density=3,            # papers must name entities (methods, datasets)
        synthesis_char_budget_per_source=3500,
        synthesis_min_source_quality=0.60,
        harvest_relevant_chunks_max_chars=4000,
        reflection_snippet_char_limit=400,
        source_type_weights={
            "academic": 1.30,
            "docs":     1.00,
            "news":     0.65,
            "blog":     0.50,
            "forum":    0.35,
            "reddit":   0.30,
        },
    ),

    # -----------------------------------------------------------------------
    # Medical / clinical
    # Clinical papers only; anecdotal and user-generated content is hazardous.
    # -----------------------------------------------------------------------
    "medical": ContentProfile(
        minhash_threshold=0.65,          # aggressively remove near-duplicate advice
        embedding_threshold=0.82,        # remove "same advice, different wording"
        min_entity_density=3,            # must mention conditions / drugs / procedures
        synthesis_char_budget_per_source=3200,
        synthesis_min_source_quality=0.65,      # strict — no low-quality health content
        harvest_relevant_chunks_max_chars=4000,
        reflection_snippet_char_limit=380,
        source_type_weights={
            "academic": 1.40,
            "docs":     1.00,
            "news":     0.55,
            "blog":     0.35,
            "forum":    0.25,
            "reddit":   0.25,
        },
    ),

    # -----------------------------------------------------------------------
    # Journalistic / news
    # Multiple outlets covering same event = cross-verification.  Forums and
    # Reddit can add community context; strict quality bar not needed.
    # -----------------------------------------------------------------------
    "journalistic": ContentProfile(
        minhash_threshold=0.88,          # only remove literal copy-paste reposts
        embedding_threshold=0.78,        # keep independent reports on same event
        min_entity_density=1,            # news can be entity-sparse (quotes, context)
        synthesis_char_budget_per_source=1500,  # news is concise
        synthesis_min_source_quality=0.40,      # even brief reports count
        harvest_relevant_chunks_max_chars=2000,
        reflection_snippet_char_limit=180,
        source_type_weights={
            "news":     1.10,
            "blog":     1.00,
            "reddit":   1.00,
            "forum":    0.90,
            "docs":     0.75,
            "academic": 0.70,
        },
    ),

    # -----------------------------------------------------------------------
    # Finance / markets / crypto
    # Multiple analyst views are additive.  News and blogs valuable.
    # Reddit finance boards useful but noisy.
    # -----------------------------------------------------------------------
    "finance": ContentProfile(
        minhash_threshold=0.85,          # keep different analysts' views
        embedding_threshold=0.80,        # different takes on same asset = useful
        min_entity_density=2,
        synthesis_char_budget_per_source=1800,
        synthesis_min_source_quality=0.48,
        harvest_relevant_chunks_max_chars=2500,
        reflection_snippet_char_limit=220,
        source_type_weights={
            "news":     1.10,
            "academic": 0.90,
            "blog":     0.85,
            "reddit":   0.75,
            "forum":    0.70,
        },
    ),

    # -----------------------------------------------------------------------
    # Shopping / product research
    # User reviews (Reddit, forums) are often the most honest signal.
    # Price comparison blogs and review sites are also valuable.
    # Academic sources are irrelevant.
    # -----------------------------------------------------------------------
    "shopping": ContentProfile(
        minhash_threshold=0.84,          # keep different reviewers' perspectives
        embedding_threshold=0.82,        # "same product, different experience" = useful
        min_entity_density=1,            # product names count, but prose can be thin
        synthesis_char_budget_per_source=2000,
        synthesis_min_source_quality=0.38,      # even short reviews add signal
        harvest_relevant_chunks_max_chars=2500,
        reflection_snippet_char_limit=250,
        source_type_weights={
            "reddit":   1.20,  # product subreddits / buy recommendations
            "forum":    1.15,  # user experience threads
            "blog":     1.00,  # review blogs
            "news":     0.90,
            "docs":     0.75,
            "academic": 0.45,
        },
    ),

    # -----------------------------------------------------------------------
    # Troubleshooting / fixing errors
    # Forums and Reddit are the primary signal — Stack Overflow, GitHub Issues,
    # r/techsupport etc.  Official docs are also excellent.  Academic sources
    # are rarely useful for debugging.
    # -----------------------------------------------------------------------
    "troubleshooting": ContentProfile(
        minhash_threshold=0.78,          # different solutions to same error = all useful
        embedding_threshold=0.85,        # similar-sounding fixes may have different steps
        min_entity_density=2,            # error names / package names needed
        synthesis_char_budget_per_source=3000,  # step-by-step solutions need space
        synthesis_min_source_quality=0.42,
        harvest_relevant_chunks_max_chars=3500,
        reflection_snippet_char_limit=320,
        source_type_weights={
            "forum":    1.30,  # Stack Overflow / stackexchange gold standard
            "reddit":   1.15,  # r/techsupport, r/linux, etc.
            "docs":     1.10,  # official error reference docs
            "blog":     1.00,
            "news":     0.60,
            "academic": 0.50,
        },
    ),

    # -----------------------------------------------------------------------
    # Forum / community discussion
    # User explicitly wants forum-style content; boost all community sources.
    # -----------------------------------------------------------------------
    "forum": ContentProfile(
        minhash_threshold=0.85,          # different people's opinions = all valuable
        embedding_threshold=0.83,
        min_entity_density=1,
        synthesis_char_budget_per_source=2000,
        synthesis_min_source_quality=0.35,      # low bar — community posts count
        harvest_relevant_chunks_max_chars=2500,
        reflection_snippet_char_limit=250,
        source_type_weights={
            "forum":    1.30,
            "reddit":   1.30,
            "blog":     0.90,
            "news":     0.80,
            "docs":     0.70,
            "academic": 0.60,
        },
    ),

    # -----------------------------------------------------------------------
    # General (fallback) — matches base ResearchConfig defaults exactly
    # No overrides needed; listed explicitly for documentation.
    # -----------------------------------------------------------------------
    "general": ContentProfile(
        # All None → no overrides, depth preset rules
    ),
}


# ---------------------------------------------------------------------------
# Apply profile to state
# ---------------------------------------------------------------------------

def apply_content_profile(state: ResearchState) -> None:
    """
    Patch state.config in-place with content-type-specific overrides.

    Called once by the orchestrator after run_plan() sets state.query_type.
    Only non-None profile fields overwrite the existing config values.
    """
    profile = _PROFILES.get(state.query_type) or _PROFILES["general"]
    cfg = state.config

    if profile.minhash_threshold is not None:
        cfg.minhash_threshold = profile.minhash_threshold
    if profile.embedding_threshold is not None:
        cfg.embedding_threshold = profile.embedding_threshold
    if profile.min_entity_density is not None:
        cfg.min_entity_density = profile.min_entity_density
    if profile.synthesis_min_source_quality is not None:
        cfg.synthesis_min_source_quality = profile.synthesis_min_source_quality

    # Fields not in ResearchConfig are stored as dynamic attributes on the config
    # so phase modules can read them via getattr with a fallback default.
    if profile.synthesis_char_budget_per_source is not None:
        cfg.synthesis_char_budget_per_source = profile.synthesis_char_budget_per_source  # type: ignore[attr-defined]
    if profile.harvest_relevant_chunks_max_chars is not None:
        cfg.harvest_relevant_chunks_max_chars = profile.harvest_relevant_chunks_max_chars  # type: ignore[attr-defined]
    if profile.reflection_snippet_char_limit is not None:
        cfg.reflection_snippet_char_limit = profile.reflection_snippet_char_limit  # type: ignore[attr-defined]
    if profile.source_type_weights is not None:
        cfg.source_type_weights = profile.source_type_weights  # type: ignore[attr-defined]

    applied = [
        f for f in (
            "minhash_threshold", "embedding_threshold", "min_entity_density",
            "synthesis_min_source_quality", "synthesis_char_budget_per_source",
            "harvest_relevant_chunks_max_chars", "reflection_snippet_char_limit",
            "source_type_weights",
        )
        if getattr(profile, f, None) is not None
    ]
    state.log(
        f"Content profile: type={state.query_type!r} "
        + (f"overrides={applied}" if applied else "no overrides (general default)")
    )
