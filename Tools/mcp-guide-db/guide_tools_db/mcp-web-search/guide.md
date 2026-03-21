# mcp-web-search

## Overview

`mcp-web-search` is the default retrieval tool for web research in this workspace.

Use it for:

- documentation lookup
- factual web search
- product/spec/review checks
- reading specific URLs
- long-form research through `deep_research(...)`

This tool should usually be used in this order:

```text
1. web_search(query or [queries])
2. inspect Preview/Snippet fields
3. read_page([...]) only for the best URLs
4. deep_research(...) only after a plan and explicit user confirmation
```

---

## Available Tools

### `web_search(query, limit=10)`

Fast general web search with merged results from YaCy and DDGS.

**`query` can be a string or a list of strings.**
When a list is passed, each query is run in parallel and results are returned grouped — one block per query. This replaces the old `web_search_batch` tool.

Use it when:

- you need a quick answer
- you need candidate sources
- you want to validate names, SKUs, vendor features, or version-specific claims
- you need to compare several products or sub-topics — pass a list of queries

Returns results per query that include:

- title
- URL
- snippet
- preview (600 chars)
- source engine

**Single query:**

```json
{ "tool": "web_search", "query": "nginx reverse proxy" }
```

**Multi-query (parallel, grouped results):**

```json
{
  "tool": "web_search",
  "query": [
    "Samsung S27DG612SI OLED",
    "Gigabyte FO27Q2 OLED",
    "Gigabyte MO27Q2A EK OLED"
  ],
  "limit": 5
}
```

> `limit` applies per query when a list is passed.

### `read_page(url)` or `read_page([url1, url2, ...])`

Reads one or more webpages and returns cleaned text.

Use it when previews are not enough and you need:

- exact specs
- warranty details
- review methodology
- quoted claims from a source

Rules:

- prefer batch reads over sequential single-page reads
- use the URLs returned by search
- do not read pages blindly if the preview already answers the question
- YouTube URLs attempt transcript extraction automatically
- Reddit URLs (`reddit.com/r/...`) work natively via `.json` API — no auth needed
- If `read_page` returns `⬇ This URL points to a downloadable file` — switch to `import_web_file` immediately, do not retry

### `import_web_file(url, save_to="downloads/", allowed_types=None, max_size_mb=50)`

Downloads a binary or document file from the web into the task workspace.

Use when:

- `read_page` returns the `⬇ downloadable file` hint
- A search result has a `⬇ FILE` or `📄 PDF ⬇` badge and you need the actual file
- The task requires the raw binary: PDF to parse, ZIP to extract, CSV to analyze, image to inspect

Rules:

- **Only call after confirming the URL is a real file** — via a `⬇ FILE` / `📄 PDF ⬇` badge in search results or a `⬇ downloadable file` hint from `read_page`. Never call speculatively.
- **Do not retry the same URL more than once.** If it fails, report the error and stop.
- **Do not use for web pages or repo homepages** — only for direct file URLs with a known extension (.pdf, .zip, .csv, etc.).
- **Hard cap: 50 MB. Never pass `max_size_mb` above 50.** For large datasets use `bash("curl -L -o file.csv URL")` inside the sandbox instead.
- `allowed_types` accepts: `"text"`, `"media"`, `"archive"`, `"data"` — pass it when you know the expected category.
- File lands in `task/{save_to}/{filename}` — immediately accessible via `bash(...)` or `show_image(...)` in the sandbox.
- Executables and scripts (`.exe`, `.sh`, `.py`, `.dll`, etc.) are hard-blocked server-side.

Workflow:

```text
web_search / read_page  →  ⬇ badge or hint appears
import_web_file(url, allowed_types=["text"])  →  saved to task/downloads/
bash("pdftotext downloads/paper.pdf -")       →  process in sandbox
```

### `deep_research(query, depth="medium")`

Long-running autonomous research pipeline.

Depth values:

- `low`
- `medium`
- `high`
- `extra`

Use it only when:

- the task needs many sources and cross-checking
- the user explicitly wants a deep report
- lightweight search is no longer enough

Hard rule:

- do not start `deep_research` immediately
- first present a brief research plan
- wait for explicit user confirmation
- run it at most once per conversation

---

## Search Query Rules

Write search queries as compact keyword queries, not long chat sentences.

Rules:

- prefer English by default
- preserve exact model names, SKUs, versions, feature names, and error text
- use short queries first
- if the task is a comparison, pass a list of queries — one per product/entity

Examples:

| Weak | Better |
| --- | --- |
| `Which OLED monitor is better for work and burn-in protection` | `OLED monitor burn-in protection work` |
| `Does Samsung Odyssey G6 S27DG612SI exist and how bright is it` | `Samsung S27DG612SI SDR brightness OLED` |
| `compare Gigabyte FO27Q2 and MO27Q2A EK for anti glare` | `["Gigabyte FO27Q2 anti glare", "Gigabyte MO27Q2A EK anti glare"]` |

---

## Recommended Workflows

### Quick lookup

```text
1. web_search("short query")
2. read Preview/Snippet
3. answer if enough evidence is already present
```

### Comparison workflow

```text
1. web_search(["query per product", ...], limit=5)
2. compare previews/snippets
3. read_page([...]) for the strongest sources only
4. answer with explicit tradeoffs and source-backed claims
```

### Deep research workflow

```text
1. summarize what needs to be researched
2. present a short plan
3. ask the user for confirmation
4. run deep_research(detailed query, depth=...)
5. fill small gaps with web_search/read_page, not another deep_research
```

---

## Practical Notes

- `Preview` is often enough for fast fact checking.
- `read_page` is for depth, not discovery.
- `deep_research` is expensive in time; gate it behind plan + confirmation.
- If exact product names are present, do not mutate them in search queries.
- If a result is ambiguous, report it as ambiguous instead of declaring the entity nonexistent.

---

## Summary

| Field | Value |
| --- | --- |
| Tool family | Web retrieval and long-form research |
| Best first step | `web_search(query)` or `web_search([q1, q2, ...])` |
| Best second step | `read_page([...])` |
| Escalation path | plan -> explicit confirmation -> `deep_research(...)` |
| Avoid | immediate deep research, long sentence queries, sequential page reads |
