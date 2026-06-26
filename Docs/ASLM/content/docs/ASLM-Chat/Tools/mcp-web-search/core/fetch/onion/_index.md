---
title: "onion"
draft: false
---

## Package `onion`

`Tools/mcp-web-search/core/fetch/onion/` — Optional Tor/onion access layer.

Strictly opt-in and zero-install. Reuses a running tor SOCKS or spawns its own from an already-installed tor binary.

---

## Module map

| Doc | Source | Role |
| --- | --- | --- |
| [harvester](harvester/) | `harvester.py` | Anchored auto-expansion of the onion allowlist |
| [models](models/) | `models.py` | Onion domain models |
| [registry](registry/) | `registry.py` | Loader for the onion service allowlist |
| [resolver](resolver/) | `resolver.py` | Resolve onion addresses from clearnet anchors |
| [search](search/) | `search.py` | Deep onion search implementation |
| [store](store/) | `store.py` | Persistent store for auto-harvested onion services |
| [tor_proxy](tor_proxy/) | `tor_proxy.py` | Resolve a usable tor SOCKS proxy |
| [transport](transport/) | `transport.py` | Fetch over Tor via curl_cffi + socks5h |

---

## Related

- [fetch](../_index/)
