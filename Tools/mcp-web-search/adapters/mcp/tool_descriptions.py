from __future__ import annotations


MCP_SERVER_DESCRIPTION = "Search and page reading tools."


WEB_SEARCH_TOOL_DESCRIPTION = """\
Ranked web search and page-content extraction.

The query is a search-engine directive, not a question. Write it like a
librarian's search expression: concrete nouns, identifiers, versions, or
quoted error text — no prose, no explanation.

QUALITY GATE (enforced automatically):
  The engine validates every query before sending it to the network.
  Two violations return a BAD_QUERY error you must resolve:
  · Vague SEO-style filler words — generic qualifiers that surface
    clickbait instead of substance (e.g. "great", "ultimate", "overview",
    "how to", "what is"). Use specific nouns and identifiers instead.
  · More than 6 content words — operators (site:, -site:, OR, "phrases")
    are free and do not count toward the limit. Plain filler words do.

OPERATORS (ASCII only — never translate):
  site:domain.com           restrict to domain and subdomains
  -site:domain.com          exclude domain
  -domain.com               short exclude alias
  "exact phrase"            force exact match; counts as one content token
  term1 OR term2            either term
  site:A OR site:B term     multi-domain search

  · "reddit", "github", "arxiv" are keywords, not source constraints.
    Use site:reddit.com, site:github.com, site:arxiv.org instead.
  · Always quote exact error messages: "ModuleNotFoundError: No module named 'x'"

LAYERED QUERIES — one narrow query beats one broad one:
  1. Discover the exact name / version:  pytorch 2.3 release
  2. Drill into it:  "torch.compile" Python 3.12 site:github.com
  3. Cross-check a claim:  torch.compile site:pytorch.org
  Issue steps as separate calls; never bundle them.

WHAT IT CAN READ:
  PDF       — any domain (.pdf URL or PDF bytes detected automatically)
  YouTube   — full transcript (pass the video URL to read_page)
  Reddit    — posts and comment threads (native JSON, no scraping)
  GitHub    — READMEs, releases, issues, wiki pages
  StackExchange / Stack Overflow — questions and top answers
  X/Twitter — tweet text and metadata
  Amazon    — product title, price, rating, feature bullets
  HTML      — articles, docs, blogs (structured content extraction)

CITATION:
  · Cite only with the handles returned in search context.
  · Place each handle after the exact sentence it supports.
  · Only cite a source whose content explicitly confirms the claim.
  · Never reuse handles from a different query or earlier call.
  · Parsed content outweighs snippet-only sources.

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
