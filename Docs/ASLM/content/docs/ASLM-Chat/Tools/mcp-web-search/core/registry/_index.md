---
title: "registry"
draft: false
---

## Package `registry`

`Tools/mcp-web-search/core/registry/` — Domain access policies, trust tiers, dynamic reputation, and endpoint probing.

JSON on disk: `domain_registry.json`, `trust_registry.json`, `domain_profiles/`, `trust_registry_profiles/`, `academic_registry.json`.

---

## Module map

| Doc | Source | Role |
| --- | --- | --- |
| [config](config/) | `config.py` | Path constants and probe tuning |
| [domain_registry](domain_registry/) | `domain_registry.py` | Fetch strategy, Camoufox/Next.js flags |
| [trust_registry](trust_registry/) | `trust_registry.py` | Trust tiers and blacklist |
| [domain_reputation](domain_reputation/) | `domain_reputation.py` | EMA quality, auto promote/blacklist |
| [endpoint_overlay](endpoint_overlay/) | `endpoint_overlay.py` | Validated JSON/API endpoints |
| [doctor](doctor/) | `doctor.py` | Profile consistency CLI |
| [import_majestic](import_majestic/) | `import_majestic.py` | Majestic CSV importer |

---

## Related

- [core](../_index/)
