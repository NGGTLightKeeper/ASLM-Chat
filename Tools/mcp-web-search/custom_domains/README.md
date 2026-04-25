# Custom Domains

This folder is a staging area for domain-specific routes that are too opinionated
to wire straight into `services/read_page.py`.

Current modules:

- `amazon.py`
  - Browser-like `httpx` snapshot fetch for Amazon PDPs.
- `ebay.py`
  - Browser fetch (`camoufox` / `patchright`) plus `trafilatura`-first cleanup.
- `dns_shop.py`
  - DNS URL rewrite/variant logic and DNS-specific metadata extraction.
- `citilink.py`
  - Citilink JSON-LD/fallback metadata extraction.
- `retail.py`
  - Shared retail routing and metadata header helpers.
- `reddit.py`
  - Reddit `.json` fetch route for post+comments.
- `x.py`
  - X/Twitter public syndication and oEmbed route.
- `stackexchange.py`
  - Stack Exchange routing shim over the existing public API fetcher.

Planned migration candidates:

- `youtube`

Why this folder exists:

- lets us experiment without bloating generic `read_page`
- keeps domain heuristics isolated and easier to benchmark
- makes later promotion into production routes much more deliberate
