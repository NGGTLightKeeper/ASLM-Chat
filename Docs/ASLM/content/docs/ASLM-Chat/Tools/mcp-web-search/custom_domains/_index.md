---
title: "custom_domains"
draft: false
---

## Package `custom_domains`

`Tools/mcp-web-search/custom_domains/` — Site-specific fetchers and metadata extractors for previews and `read_page`.

---

## Module map

| Doc | Source | Role |
| --- | --- | --- |
| [router](router/) | `router.py` | `CustomRoute` table and preview dispatch |
| [github](github/) | `github.py` | GitHub REST → markdown |
| [reddit](reddit/) | `reddit.py` | Reddit `.json` threads |
| [x](x/) | `x.py` | X/Twitter syndication / oEmbed |
| [amazon](amazon/) | `amazon.py` | Amazon product snapshot |
| [ebay](ebay/) | `ebay.py` | eBay listing snapshot (heavy) |
| [common](common/) | `common.py` | Shared HTML pipeline helpers |
| [retail](retail/) | `retail.py` | JSON-LD product metadata |
| [retail_common](retail_common/) | `retail_common.py` | Price/availability formatting |
| [dns_shop](dns_shop/) | `dns_shop.py` | DNS-Shop URL rewrite + metadata |
| [citilink](citilink/) | `citilink.py` | Citilink metadata |
| [stackexchange](stackexchange/) | `stackexchange.py` | Re-exports Stack Exchange fetcher |

---

## Related

- [mcp-web-search](../_index/)
- [services/read_page](../services/read_page/)
| [base](base/) | `base.py` | custom-domains layer contract |
| [youtube](youtube/) | `youtube.py` | YouTube watch/short metadata |
