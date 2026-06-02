---
title: "stackexchange"
draft: false
---

## Module `stackexchange`

`Tools/mcp-web-search/custom_domains/stackexchange.py` — thin re-export surface for Stack Exchange question URLs. Implementation lives in [stackexchange_fetcher](../core/fetch/stackexchange_fetcher/).

---

## Public re-exports

| Symbol | Purpose |
|--------|---------|
| `fetch_stackexchange_question` | Fetch and normalize a Stack Exchange question page for the search pipeline. |
| `is_stackexchange_question_url` | Return whether a URL targets a Stack Exchange question thread. |

---

## Related

- [stackexchange_fetcher](../core/fetch/stackexchange_fetcher/)
- [custom_domains/_index](_index/)
