# mcp-web-search

## What it is

`mcp-web-search` is the web retrieval tool.
Provides search, page reading, file download, and long-form research.

---

## Tools

### `web_search(query, limit=10)`

Fast web search with DDGS-backed results.
`query` accepts a string or a list of strings (parallel batch search).
Returns: title, URL, snippet, preview (600 chars), source engine.

### `read_page(url)` or `read_page([url1, url2, ...])`

Reads one or more webpages and returns cleaned text.
YouTube URLs attempt transcript extraction.
Reddit URLs work via .json API natively.
If it returns a "downloadable file" hint -- switch to `import_web_file`.

### `import_web_file(url, save_to="downloads/", allowed_types=None, max_size_mb=50)`

Downloads a binary or document file into the task workspace.
Hard cap: 50 MB. Executables are blocked server-side.
Only call after confirming the URL is a real file (badge or hint).

### `deep_research(query, depth="medium")`

Long-running autonomous research pipeline.
Depth values: `low`, `medium`, `high`, `extra`.
Gate behind plan + explicit user confirmation. Run at most once per conversation.

---

## Golden rules

1. Use compact keyword queries, not long sentences.
2. Preserve exact model names, SKUs, versions in queries.
3. Prefer batch reads (`read_page([...])`) over sequential single-page reads.
4. Do not use `read_page` if the preview already answers the question.
5. Do not call `import_web_file` speculatively -- only after a confirmed file hint.
6. Do not retry `import_web_file` more than once on the same URL.
7. Do not start `deep_research` without presenting a plan and getting user confirmation.

---

## Common mistakes

| Mistake | Correct approach |
| --- | --- |
| Long sentence queries | Short keyword queries |
| `read_page` on every search result | Check previews first, read only the best |
| `import_web_file` on a GitHub repo URL | `bash("git clone ...")` |
| `import_web_file` without file hint | `read_page` first, then switch if hinted |
| Immediate `deep_research` | Plan first, confirm with user, then run |
| `read_page` for repo code inspection | `bash("git clone ...")` |
