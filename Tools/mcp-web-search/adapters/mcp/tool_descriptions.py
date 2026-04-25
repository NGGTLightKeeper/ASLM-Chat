from __future__ import annotations


MCP_SERVER_DESCRIPTION = "Search and page reading tools."


WEB_SEARCH_TOOL_DESCRIPTION = """Primary web search tool for current information.

Use this tool when you need up-to-date facts, recent news, current product details,
latest documentation, prices, releases, schedules, or any information that may have
changed since your built-in knowledge cutoff.

Returns ranked sources with URLs, parsed page content when extraction succeeds,
and search-engine preview text as a fallback.
Citation policy:
- Cite web-search evidence only with the citation handles returned in the search context.
- Put each citation immediately after the exact sentence or bullet it supports.
- Use a handle only when that source explicitly supports the claim in its title, preview, or parsed content.
- Never cite a source only because the domain or title sounds related.
- Never reuse a handle from a different search result list or earlier tool call.
- Never invent, renumber, shorten, translate, or merge citation handles.
- Do not use bare domains, URLs, or source numbers as citations when handles are available.
- If none of the returned sources supports a claim, say the search did not confirm it or omit the claim.
- Prefer parsed page content over search-engine preview snippets; preview-only sources are weaker evidence.
The UI renders valid handles as compact source chips.

HOW TO SEARCH WELL - use layered queries, not one broad question:

Bad:  "best database"
Good: first pass to discover names -> ["relational database comparison", "document database tradeoffs"]
      then targeted follow-ups per candidate ->
        ["PostgreSQL indexing documentation", "SQLite WAL mode limitations",
         "MongoDB transactions documentation site:mongodb.com"]

Other useful patterns:
- For domain targeting, always use the exact ASCII operator "site:domain.com".
- Never translate search operators. Do not write "сайт:domain.com", "site：domain.com", "с site", or any localized variant.
- Do not use a bare domain or brand word when you mean a source constraint. Use "site:reddit.com", not "reddit"; use "site:github.com", not "github".
- Add "site:reddit.com" or "forum" to get real user opinions vs marketing copy
- Add "benchmark", "vs", or "review" to get comparative signal
- Add "site:github.com" for code, issues, release notes
- Use domain constraints when you need strict source control:
  "site:who.int H3N2 treatment"
  "H3N2 treatment site:who.int OR site:pubmed.ncbi.nlm.nih.gov"
  "Samsung Galaxy S25 specs -site:wikipedia.org"
  "Samsung Galaxy S25 specs -wikipedia.org"
- Use exact product, standard, library, or version names instead of generic categories
- For products: first find the exact product identifier, then search price/availability separately
- For bugs or errors: search the exact error message in quotes

Domain constraint behavior:
- Only the ASCII "site:" operator creates an include-domain constraint
- "site:domain.com" includes that domain and its subdomains
- Multiple include domains can be chained with "OR"
- "-site:domain.com" excludes that domain and its subdomains
- "-domain.com" is a short exclude alias
- If the same domain appears in both include and exclude, exclude wins
- Bare words like "reddit", "github", or "wikipedia" are normal query terms, not domain constraints

Avoid SEO-bait words that surface content farms and listicle spam:
"best", "top", "ultimate guide", "everything you need to know", "complete list",
"vs" alone (use "X vs Y benchmark" instead), "free", "easy", "simple".
Replace them with specifics: version numbers, error text, site: filters, or "reddit".

Language: search in English by default even when answering in another language.
Use the local language only when sources are region-specific (e.g. Russian retailers, local news).

Returns a dynamically sized ranked set per query depending on query type,
ranking quality, and search strategy. Accepts a single search string."""


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
