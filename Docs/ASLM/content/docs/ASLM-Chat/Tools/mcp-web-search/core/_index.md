---
title: "core"
draft: false
---

## Package `core`

`Tools/mcp-web-search/core/` — Shared libraries for search, fetch, extraction, caching, and domain policy.

---

## Module map

| Doc | Source | Role |
| --- | --- | --- |
| [search](search/) | `search/` | Web search core: SERP orchestration, triage, hosted stream, prefetch, cache |
| [engines](engines/) | `engines/` | Per-engine HTTP SERP clients and parsers |
| [config](config/) | `config/` | `search_config.json`, API keys |
| [fetch](fetch/) | `fetch/` | Page fetch transports, warm browser, academic/shopping/onion verticals |
| [extract](extract/) | `extract/` | HTML/PDF→text, previews, chunking, compaction |
| [cache](cache/) | `cache/` | SQLite source + hosted SERP caches |
| [profiles](profiles/) | `profiles/` | Runtime domain profiles (TTL/decay) and known-domain seeds |
| [read](read/) | `read/` | Implementation of `read_page` |
| [mcp_contract](mcp_contract/) | `mcp_contract.py` | Tool schemas and payload contract |
| [runtime](runtime/) | `runtime.py` | Event-loop helpers (`run_fast`) |
| [logging_setup](logging_setup/) | `logging_setup.py` | File logging for daemon/MCP processes |
| [search_io_logger](search_io_logger/) | `search_io_logger.py` | NDJSON debug log of tool I/O |

---

## Related

- [mcp-web-search](../_index/)
