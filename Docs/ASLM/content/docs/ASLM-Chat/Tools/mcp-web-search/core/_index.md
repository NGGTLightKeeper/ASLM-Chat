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
| [search](search/) | `search/` | Web search core, caching, prefetch, recent tracker |
| [models](models/) | `models/` | SERP/UI dataclasses |
| [config](config/) | `config/` | `search_config.json`, API keys, hardware, pipeline modes |
| [query](query/) | `query/` | Classification, constraints, routing, ASLM embeddings |
| [fetch](fetch/) | `fetch/` | DDGS, hosted APIs, page fetch, Camoufox workers |
| [extract](extract/) | `extract/` | HTML→text, previews, GLiNER, chunking |
| [cache](cache/) | `cache/` | SQLite source + hosted SERP caches |
| [registry](registry/) | `registry/` | Domain/trust profiles, reputation, endpoints |
| [search](search/) | `search/` | Web search core logic |
| [debug](debug/) | `debug/` | Developer CLIs (not production MCP) |
| [engines](engines/) | `engines/` | Search engines |

---

## Related

- [mcp-web-search](../_index/)
- [services](../services/)
