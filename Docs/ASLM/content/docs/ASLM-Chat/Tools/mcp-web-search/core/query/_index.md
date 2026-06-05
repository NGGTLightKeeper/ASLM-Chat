---
title: "query"
draft: false
---

## Package `query`

`Tools/mcp-web-search/core/query/` — Query classification, domain constraints, routing scores, and ASLM embedding runtime.

---

## Module map

| Doc | Source | Role |
| --- | --- | --- |
| [class_profiles](class_profiles/) | `class_profiles.py` | Rule/model hybrid query-type inference |
| [domain_constraints](domain_constraints/) | `domain_constraints.py` | `site:` parsing and provider query building |
| [routing_score](routing_score/) | `routing_score.py` | Weighted source scoring |
| [aslm_embedding_models](aslm_embedding_models/) | `aslm_embedding_models.py` | ONNX export paths |
| [aslm_embedding_bootstrap](aslm_embedding_bootstrap/) | `aslm_embedding_bootstrap.py` | Legacy migration and model download |
| [aslm_embedding_runtime](aslm_embedding_runtime/) | `aslm_embedding_runtime.py` | `SearchModelSession`, inference |

---

## Related

- [core](../_index/)
- [services/web_search](../../services/web_search/)
