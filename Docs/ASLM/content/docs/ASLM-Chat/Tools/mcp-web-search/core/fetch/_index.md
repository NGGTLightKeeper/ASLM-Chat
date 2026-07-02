---
title: "fetch"
draft: false
---

## Package `fetch`

`Tools/mcp-web-search/core/fetch/` — Fetch transports, verticals, and HTTP utilities.

---

## Module map

| Doc | Source | Role |
| --- | --- | --- |
| [transport](transport/) | `transport.py` | primp/curl HTTP transport with per-engine identity |
| [httpx_transport](httpx_transport/) | `httpx_transport.py` | Plain httpx transport |
| [browser](browser/) | `browser/` | Warm-browser daemon, client seam, identity store |
| [academic](academic/) | `academic/` | Keyless scholarly REST APIs (OpenAlex, Crossref, EuropePMC, DOAJ, arXiv) |
| [shopping](shopping/) | `shopping/` | Shopping vertical (providers, parse, assets) |
| [onion](onion/) | `onion/` | Optional Tor/onion access layer |
| [stackexchange_fetcher](stackexchange_fetcher/) | `stackexchange_fetcher.py` | Stack Exchange API |
| [profiles](profiles/) | `profiles.py` | Per-engine fetch personalities |
| [antibot](antibot/) | `antibot.py` | Challenge-page detection |
| [download_types](download_types/) | `download_types.py` | Non-HTML download detection |
| [url_utils](url_utils/) | `url_utils.py` | SSRF-safe URL validation |
| [thread_pool](thread_pool/) | `thread_pool.py` | Shared `io_pool` executor |
| [constants](constants/) | `constants.py` | `DEFAULT_UA` |
| [_base](_base/) | `_base.py` | Shared fetch primitives |

---

## Related

- [core](../_index/)
- [browser](browser/)
