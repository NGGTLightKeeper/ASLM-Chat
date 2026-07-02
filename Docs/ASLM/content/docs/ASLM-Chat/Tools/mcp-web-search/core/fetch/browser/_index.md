---
title: "browser"
draft: false
---

## Package `browser`

`Tools/mcp-web-search/core/fetch/browser/` — Warm-browser daemon and identity.

---

## Module map

| Doc | Source | Role |
| --- | --- | --- |
| [client](client/) | `client.py` | Client seam: `browser_fetch`, daemon autostart |
| [daemon](daemon/) | `daemon.py` | Warm-browser daemon (supervised chromium) |
| [identity_store](identity_store/) | `identity_store.py` | Browser identity storage (storageState generations, HTTP cookies) |
| [models](models/) | `models.py` | `BrowserFetch` result model |
| [tempjanitor](tempjanitor/) | `tempjanitor.py` | Temp profile reaper |

---

## Related

- [fetch](../_index/)
