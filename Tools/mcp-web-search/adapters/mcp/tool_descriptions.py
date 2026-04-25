from __future__ import annotations


MCP_SERVER_DESCRIPTION = "Search and page reading tools."


WEB_SEARCH_TOOL_DESCRIPTION = """Search the web and return ranked sources with previews.

HOW TO SEARCH WELL — use layered queries, not one broad question:

Bad:  "best AI models 2025"
Good: first pass to discover names -> ["top LLM releases 2025", "new language models 2025"]
      then targeted follow-ups per candidate ->
        ["Gemini 2.0 Flash benchmarks", "Llama 4 reddit review",
         "GPT-4o vs Claude 3.5 site:reddit.com OR site:news.ycombinator.com"]

Other useful patterns:
- Add "reddit", "forum", or "site:reddit.com" to get real user opinions vs marketing copy
- Add "benchmark", "vs", "review 2025" to get comparative signal
- Add "github" or "site:github.com" for code, issues, release notes
- Use domain constraints when you need strict source control:
  "site:who.int H3N2 treatment"
  "H3N2 treatment site:who.int OR site:pubmed.ncbi.nlm.nih.gov"
  "Samsung Galaxy S25 specs -site:wikipedia.org"
  "Samsung Galaxy S25 specs -wikipedia.org"
- Use the model's exact version name, not a generic category ("Llama 3.3 70B" not "Meta AI")
- For products: first find the exact model name, then search price/availability separately
- For bugs or errors: search the exact error message in quotes

Domain constraint behavior:
- "site:domain.com" includes that domain and its subdomains
- Multiple include domains can be chained with "OR"
- "-site:domain.com" excludes that domain and its subdomains
- "-domain.com" is a short exclude alias
- If the same domain appears in both include and exclude, exclude wins

Avoid SEO-bait words that surface content farms and listicle spam:
"best", "top", "ultimate guide", "everything you need to know", "complete list",
"vs" alone (use "X vs Y benchmark" instead), "free", "easy", "simple".
Replace them with specifics: version numbers, error text, site: filters, or "reddit".

Language: search in English by default even when answering in another language.
Use the local language only when sources are region-specific (e.g. Russian retailers, local news).

Returns a dynamically sized ranked set per query depending on query type,
ranking quality, and search strategy. Accepts a single string or a list
of up to 10 query strings."""


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
