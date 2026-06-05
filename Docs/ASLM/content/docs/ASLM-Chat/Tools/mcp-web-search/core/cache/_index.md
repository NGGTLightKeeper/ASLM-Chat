---
title: "cache"
draft: false
---

## Package `cache`

`Tools/mcp-web-search/core/cache/` — Persistent caches for SERP results and fetched page text.

---

## Module map

| Doc | Source | Role |
| --- | --- | --- |
| [hosted_cache](hosted_cache/) | `hosted_cache.py` | Hosted API SERP SQLite cache |
| [source_cache](source_cache/) | `source_cache.py` | Page text cache for previews and `read_page` |
| [query_normalizer](query_normalizer/) | `query_normalizer.py` | Stable query keys for cache lookups |

---

## Related

- [core](../_index/)
- [fetch](../fetch/)
