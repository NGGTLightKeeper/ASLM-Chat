---
title: "tests"
draft: false
---

## Package `tests`

`Tools/mcp-web-search/tests/` — Pytest suite for the search core, engine parsers, caches, verticals, and `read_page` content pipeline.

Run from the tool directory with the project venv active:

```text
pytest tests/
```

`pytest.ini` at the tool root configures discovery and markers (`unit`, `integration`).

---

## Module map

| Doc | Source | Role |
| --- | --- | --- |
| [test_search_core](test_search_core/) | `test_search_core.py` | Search core unit tests |
| [test_search_cache](test_search_cache/) | `test_search_cache.py` | SERP cache + repeat block |
| [test_new_engine_parsers](test_new_engine_parsers/) | `test_new_engine_parsers.py` | Engine HTML parsers (fixtures) |
| [test_hosted_providers](test_hosted_providers/) | `test_hosted_providers.py` | Hosted API unit tests |
| test_query_dates | `test_query_dates.py` | Date-intent parsing *(doc pending)* |
| [test_academic](test_academic/) | `test_academic.py` | Academic vertical |
| [test_browser_daemon](test_browser_daemon/) | `test_browser_daemon.py` | Warm-browser recycle/checkpoint supervision |
| [test_browser_layer](test_browser_layer/) | `test_browser_layer.py` | Browser client seam |
| [test_identity_cookies](test_identity_cookies/) | `test_identity_cookies.py` | Identity store generations + HTTP cookies |
| test_chunk_compaction | `test_chunk_compaction.py` | BM25 chunk compaction *(doc pending)* |
| test_content_cleaning | `test_content_cleaning.py` | Content cleaning *(doc pending)* |
| [test_reddit](test_reddit/) | `test_reddit.py` | Reddit fallback testing |
| [test_shopping_engine](test_shopping_engine/) | `test_shopping_engine.py` | Shopping engine |
| [test_shopping_parse_products](test_shopping_parse_products/) | `test_shopping_parse_products.py` | Product parsing |
| [test_shopping_price_parse](test_shopping_price_parse/) | `test_shopping_price_parse.py` | Price parsing |
| test_shopping_assets | `test_shopping_assets.py` | Shopping assets *(doc pending)* |
| [test_onion_contract](test_onion_contract/) | `test_onion_contract.py` | Onion capability schema/opt-in |
| [test_onion_registry](test_onion_registry/) | `test_onion_registry.py` | Onion allowlist / resolver |
| [test_onion_search](test_onion_search/) | `test_onion_search.py` | Deep onion search pipeline |
| [test_onion_transport](test_onion_transport/) | `test_onion_transport.py` | Onion transport/tor spawn |

---

## Related

- [mcp-web-search](../_index/)
