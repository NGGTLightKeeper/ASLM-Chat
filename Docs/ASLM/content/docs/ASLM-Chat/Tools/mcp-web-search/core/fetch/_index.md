---
title: "fetch"
draft: false
---

## Package `fetch`

`Tools/mcp-web-search/core/fetch/` — Search providers and HTTP fetch utilities.

---

## Module map

| Doc | Source | Role |
| --- | --- | --- |
| [ddgs_client](ddgs_client/) | `ddgs_client.py` | DuckDuckGo / multi-engine via `ddgs` |
| [hosted_clients](hosted_clients/) | `hosted_clients.py` | Tavily, Brave, Bing, SerpAPI |
| [engine_router](engine_router/) | `engine_router.py` | Quality-based engine ordering |
| [engine_stats](engine_stats/) | `engine_stats.py` | Per-engine rolling metrics |
| [page_fetcher](page_fetcher/) | `page_fetcher.py` | httpx + curl fetch → source cache |
| [camoufox_fetcher](camoufox_fetcher/) | `camoufox_fetcher.py` | Headless browser fetch |
| [academic_fetcher](academic_fetcher/) | `academic_fetcher.py` | arXiv / Semantic Scholar fast path |
| [stackexchange_fetcher](stackexchange_fetcher/) | `stackexchange_fetcher.py` | Stack Exchange API |
| [url_utils](url_utils/) | `url_utils.py` | SSRF-safe URL validation |
| [thread_pool](thread_pool/) | `thread_pool.py` | Shared `io_pool` executor |
| [antibot](antibot/) | `antibot.py` | Challenge-page detection |
| [download_types](download_types/) | `download_types.py` | Non-HTML download detection |
| [constants](constants/) | `constants.py` | `DEFAULT_UA` |
| [_ddgs_worker](_ddgs_worker/) | `_ddgs_worker.py` | Isolated DDGS subprocess |
| [_camoufox_worker](_camoufox_worker/) | `_camoufox_worker.py` | Isolated Camoufox subprocess |

---

## Related

- [core](../_index/)
- [services/web_search](../../services/web_search/)
