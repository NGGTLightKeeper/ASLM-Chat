# mcp-web-search

`mcp-web-search` is an MCP server focused on two tools:

- `web_search`
- `read_page`

It is intended to be the search and page-reading layer for `ASLM-Chat`, with a separate FastMCP server for direct MCP use.

## What It Does

`web_search` is not just a thin wrapper around one search provider. It is a search pipeline built for LLM use:

- it accepts either a single query or a small batch of query variants
- it merges results from multiple search paths
- it ranks and trims the output into a compact, usable set instead of dumping raw engine output
- it fetches page previews for stronger relevance signals
- it keeps domain and query-type behavior flexible instead of pretending every query should return the same fixed number of results

`read_page` fetches and extracts readable content from a URL. It supports regular HTML pages, PDFs, YouTube transcripts, and several domain-specific readers.

## Search Features

The search layer is designed around practical retrieval quality for assistants and agents, not around imitating a browser search page.

### Query Handling

- supports a single query or a list of query variants
- works well with layered search strategies such as discovery query -> targeted follow-up query
- handles domain constraints such as `site:example.com`, chained include domains, and exclusions
- keeps result count dynamic based on query type, ranking quality, and search strategy

### Result Enrichment

- fetches previews from shortlisted pages instead of relying only on raw search snippets
- tries to surface stronger content for downstream `read_page`
- can expose direct `pdf_url` hints for academic-style results when the PDF target is known

### Search Behavior

- tuned for LLM workflows where the model needs compact, high-signal sources
- better suited for iterative querying than one-shot “give me everything” search
- intended to work well with mixed query types such as general web, academic, retailer, forum, and documentation lookups
- designed so `web_search` is the discovery step and `read_page` is the deep-reading step

### Why It Exists

The point of this server is not just “search the internet”. The point is to give a model:

- a tighter shortlist
- better previews
- cleaner follow-up URLs
- a smoother handoff into full-page reading

That is why the project focuses on `web_search` + `read_page` as a pair.

## Main Entry Points

- [adapters/mcp/server.py](C:/Users/dimap/Projects/ASLM-Chat/Tools/mcp-web-search/adapters/mcp/server.py:1)
  FastMCP server entry point. This is the primary MCP runtime.
- [mcp-server.py](C:/Users/dimap/Projects/ASLM-Chat/Tools/mcp-web-search/mcp-server.py:1)
  Bridge file for `ASLM-Chat`. It exposes the legacy tool bridge API used by the host app and is not the main FastMCP server implementation.

## Project Layout

- `adapters/mcp/`
  MCP server layer, tool descriptions, logging setup.
- `services/`
  High-level `web_search` and `read_page` orchestration.
- `core/`
  Fetching, extraction, ranking, previewing, and shared utilities.
- `custom_domains/`
  Site-specific readers and fetch helpers.
- `scripts/`
  Utility and probe scripts.
- `tests/`
  Test suite.

## Search Workflow

The intended usage pattern is:

1. call `web_search` with one query or a small batch of query variants
2. inspect the ranked result blocks and shortlist the strongest URLs
3. call `read_page` on those shortlisted URLs

This split is intentional:

- `web_search` is optimized for discovery and triage
- `read_page` is optimized for extraction and reading

Keeping those responsibilities separate makes the search layer faster and more stable than trying to fully parse every candidate page during the search step itself.

## Requirements

- Python `3.12+`
- Windows is the primary environment this project is currently tuned for

## Install Dependencies

The easiest way is the bootstrap script:

```bash
python setup_env.py --dev
```

Useful variants:

```bash
python setup_env.py
python setup_env.py --dev
python setup_env.py --recreate --dev
```

This script:

- creates `.venv` if needed
- upgrades `pip`, `setuptools`, and `wheel`
- installs the project from [pyproject.toml](C:/Users/dimap/Projects/ASLM-Chat/Tools/mcp-web-search/pyproject.toml:1)

## Generate `mcp.json`

Use:

```bash
python setup_mcp.py
```

By default this writes `mcp.json` to the project root and auto-detects the Python interpreter from `.venv` when available.

Other examples:

```bash
python setup_mcp.py --target lmstudio
python setup_mcp.py --output tmp/generated_mcp.json
python setup_mcp.py --server-name web-search-engine
```

Default generated server settings:

- command: detected Python executable
- args: `-m adapters.mcp.server`
- cwd: project root
- timeout: `120000`

## Run The MCP Server

After dependencies are installed:

```bash
.venv\Scripts\python -m adapters.mcp.server
```

If you are not using the local virtualenv, replace the interpreter accordingly.

## Run Tests

```bash
python -m pytest -q
```

If you keep a copied test sandbox such as `test_directory/`, avoid collecting duplicate tests from it during normal runs.

## Notes

- Tool descriptions are centralized in [adapters/mcp/tool_descriptions.py](C:/Users/dimap/Projects/ASLM-Chat/Tools/mcp-web-search/adapters/mcp/tool_descriptions.py:1).
- `mcp-server.py` should be treated as an `ASLM-Chat` compatibility bridge, not as the canonical MCP server implementation.
- `setup_mcp.py` updates only this server entry inside `mcpServers` and preserves other existing MCP server definitions in the target file.
