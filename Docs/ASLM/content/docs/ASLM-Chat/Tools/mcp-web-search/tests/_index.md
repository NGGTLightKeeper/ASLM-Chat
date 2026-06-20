---
title: "tests"
draft: false
---

## Package `tests`

`Tools/mcp-web-search/tests/` — Pytest suite for the MCP bridge, search pipeline, `read_page`, registries, and ASLM embedding exports.

Run from the tool directory with the project venv active:

```text
pytest tests/
```

`pytest.ini` at the tool root configures discovery and markers (`unit`, `integration`).

---

## Module map

| Doc | Source | Role |
| --- | --- | --- |
| [conftest](conftest/) | `conftest.py` | Shared skips for missing ONNX exports |
| [test_validate_search_query](test_validate_search_query/) | `test_validate_search_query.py` | Query spam gate |
| [test_search_query_contract](test_search_query_contract/) | `test_search_query_contract.py` | MCP query/effort schema |
| [test_mcp_bridge_contract](test_mcp_bridge_contract/) | `mcp-server.py` bridge contract |
| [test_class_profiles](test_class_profiles/) | Rule-based query classification |
| [test_domain_constraints](test_domain_constraints/) | `site:` / boolean rewriting |
| [test_aslm_embedding_models](test_aslm_embedding_models/) | Export path constants |
| [test_aslm_embedding_bootstrap](test_aslm_embedding_bootstrap/) | Model download / migration |
| [test_neural_pipeline_components](test_neural_pipeline_components/) | Session, routing, pipeline modes |
| [test_content_quality_signal](test_content_quality_signal/) | Reputation EMA + lexical boost |
| [test_trust_registry_profiles](test_trust_registry_profiles/) | Trust profile merge/load |
| [test_domain_registry_profiles](test_domain_registry_profiles/) | Domain profile merge/load |
| [test_domain_registry_nextjs](test_domain_registry_nextjs/) | Next.js RSC registry flag |
| [test_ddgs_partial_buffer](test_ddgs_partial_buffer/) | DDGS partial buffer + fallback |
| [test_nextjs_rsc](test_nextjs_rsc/) | RSC payload parser |
| [test_micro_chunk_worker](test_micro_chunk_worker/) | Clause-level pruning |
| [test_read_page_compress](test_read_page_compress/) | Read-page focus + compress |
| [test_read_page_nextjs_rsc](test_read_page_nextjs_rsc/) | RSC fast path |
| [test_read_page_spa_fallback](test_read_page_spa_fallback/) | Camoufox SPA fallback |
| [test_read_page_cache_and_fallback](test_read_page_cache_and_fallback/) | Source cache + fetch fallback |
| [test_read_page_whatsnew_github](test_read_page_whatsnew_github/) | Long GitHub doc compression (integration) |
| [test_github_urls](test_github_urls/) | GitHub URL parsing + live blob |
| [test_web_search_neural_domain_eval](test_web_search_neural_domain_eval/) | Neural eval trace (optional) |
| [test_hosted_providers](test_hosted_providers/) | `test_hosted_providers.py` | Hosted API unit tests |
| [test_search_core](test_search_core/) | `test_search_core.py` | Search core unit tests |
| [test_shopping_web_integration](test_shopping_web_integration/) | `test_shopping_web_integration.py` Shopping integration tests |
| [test_browser_layer](test_browser_layer/) | `test_browser_layer.py` | Offline coverage for warm-browser layer |
| [test_search_core](test_search_core/) | `test_search_core.py` | Search orchestrator logic |

---

## Related

- [mcp-web-search](../_index/)
