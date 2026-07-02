---
title: "search"
draft: false
---

## Package `search`

`Tools/mcp-web-search/core/search/` — SERP orchestration: engine fan-out, triage, hosted supplement, prefetch, caching.

---

## Module map

| Doc | Source | Role |
| --- | --- | --- |
| [web_search](web_search/) | `web_search.py` | `WebSearchService`: full pipeline, cache + repeat-block |
| [serp_api](serp_api/) | `serp_api.py` | Engine fan-out over the shared transport |
| [triage](triage/) | `triage.py` | Streaming result triage and ranking |
| [prefetch](prefetch/) | `prefetch.py` | Parallel page prefetch of top sources |
| [hosted_providers](hosted_providers/) | `hosted_providers.py` | Tavily / Firecrawl / Brave / SerpApi clients |
| [hosted_stream](hosted_stream/) | `hosted_stream.py` | Key-gated hosted supplement merged into triage |
| [quality](quality/) | `quality.py` | Result quality scoring |
| [health](health/) | `health.py` | Per-engine circuit breaker / health snapshot |
| [recent_tracker](recent_tracker/) | `recent_tracker.py` | Identical-query repeat block |
| query_dates | `query_dates.py` | Date-intent parsing for queries *(doc pending)* |

---

## Related

- [core](../_index/)
