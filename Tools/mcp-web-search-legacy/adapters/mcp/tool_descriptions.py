# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations


MCP_SERVER_DESCRIPTION = "Search and page reading tools."


WEB_SEARCH_TOOL_DESCRIPTION = """\
Ranked web search and page-content extraction.

The query is a search-engine directive, not a conversational request. Write it
like a librarian's search expression: concrete nouns, identifiers, versions,
quoted error text, and at most one intent term - no prose, no explanation.

EFFORT:
  effort="low"     fast discovery mode, typically ~7-9s. It uses DDGS only,
                   no hosted/academic engines and no page scraping. Best for
                   quick source discovery, names, URLs, and rough orientation.
                   If the DDGS worker hits its short timeout, it returns any
                   per-request partial source buffer that was already found.
  effort="medium"  default mode, typically ~10-20s. It keeps the current search
                   behavior: ranking, triage, normal scraping, and parsed
                   previews. Use this first for ordinary cited answers,
                   shopping, recommendations, reviews, and comparisons.
  effort="high"    expanded mode, typically ~15-60s. It gives the current
                   search/scoring/scraping budget about 3x more room and uses
                   a larger source pool. This is an exceptional escalation:
                   use it only for explicitly exhaustive or high-stakes work,
                   or after medium leaves an important claim unresolved. Do not
                   use it first for ordinary shopping or recommendations.

SHOPPING:
  shopping=false    default. Never runs shopping providers.
  shopping=true     use when the user needs a specific product, its price,
                    where to buy it, or availability. The query must contain
                    only the thing being searched — model, spec, SKU, or product
                    phrase.
                    Keep false for technical meanings such as payload delivery,
                    deployment, or supply-chain analysis.

QUALITY GATE (enforced automatically):
  The engine validates every query before sending it to the network.
  Only extreme violations return a BAD_QUERY error you must resolve:
  - Piles of multiple SEO-style superlatives and clickbait phrases that surface
    marketing pages instead of evidence. A single natural intent word such as
    "best" or its equivalent is allowed when paired with specific nouns and
    identifiers.
  - More than 18 content words - operators (site:, -site:, OR, "phrases")
    are free and do not count toward the limit, but they also do not reduce
    the existing content-word count: adding operators cannot make an
    overlong query valid. Plain filler words do.
  High already expands the lower-effort search budget. Do not retry the same
  intent with medium or low after high; answer from the collected evidence.
    
OPERATORS (ASCII only - never translate):
  site:domain.com           restrict to domain and subdomains
  -site:domain.com          exclude domain
  -domain.com               short exclude alias
  "exact phrase"            force exact match; counts as one content token
  term1 OR term2            either term
  site:A OR site:B term     multi-domain search

  - "reddit", "github", "arxiv" are keywords, not source constraints.
    Use site:reddit.com, site:github.com, site:arxiv.org instead.
  - Always quote exact error messages: "ModuleNotFoundError: No module named 'x'"

LAYERED QUERIES - use only when the first result leaves a distinct claim unresolved:
  1. Discover the exact name / version:  pytorch 2.3 release
  2. Drill into it:  "torch.compile" Python 3.12 site:github.com
  3. Cross-check a claim:  torch.compile site:pytorch.org
  Stop as soon as the request is answerable. Do not run all layers by default.

WHAT IT CAN READ:
  PDF       - any domain (.pdf URL or PDF bytes detected automatically)
  YouTube   - full transcript (pass the video URL to read_page)
  Reddit    - posts and comment threads (native JSON, no scraping)
  GitHub    - READMEs, releases, issues, wiki pages
  StackExchange / Stack Overflow - questions and top answers
  X/Twitter - tweet text and metadata
  Amazon    - product title, price, rating, feature bullets
  HTML      - articles, docs, blogs (structured content extraction)

CITATION:
  - Cite only with the handles returned in search context.
  - Place each handle after the exact sentence it supports.
  - Only cite a source whose content explicitly confirms the claim.
  - Never reuse handles from a different query or earlier call.
  - Parsed content outweighs snippet-only sources.

LANGUAGE: search in English by default; use local language only for
region-specific sources or proper names that exist only in that language.\
"""


READ_PAGE_TOOL_DESCRIPTION = """Open a page and extract readable text from it.

Use it when you need:
- the full content of an article, documentation page, post, or thread
- cleaner text after you already found promising URLs with search
- a small batch read of several shortlisted pages

It works best as the second step after search, when discovery is done
and you want to actually read the sources.

Ops note:
- If read_page extraction strategy was updated recently and you still see
  stale output, restart the mcp-web-search process so long-lived workers
  and in-memory caches pick up the new strategy version."""
