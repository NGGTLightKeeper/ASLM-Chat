---
title: "UI"
draft: false
---

## Package `UI`

`Apps/UI/` — Chat web UI: routes, JSON APIs, uploads, i18n, host theme/locale bridges, client JavaScript.

---

## Module map

| Doc | Source | Role |
| --- | --- | --- |
| [views](views/) | `views.py` | Pages and `/api/*` handlers |
| [urls](urls/) | `urls.py` | URL routing |
| [models](models/) | `models.py` | Empty placeholder (ORM in Data) |
| [admin](admin/) | `admin.py` | Empty placeholder (admin in Data) |
| [tests](tests/) | `tests.py` | Django regression tests |
| [upload_storage](upload_storage/) | `upload_storage.py` | Sandbox uploads |
| [file_manifests](file_manifests/) | `file_manifests.py` | Upload metadata and extraction |
| [locale_catalog](locale_catalog/) | `locale_catalog.py` | JSON i18n catalogs |
| [host_theme_bridge](host_theme_bridge/) | `host_theme_bridge.py` | ASLM theme → CSS variables |
| [host_locale_bridge](host_locale_bridge/) | `host_locale_bridge.py` | ASLM locale → bootstrap |
| [markitdown_extractor](markitdown_extractor/) | `markitdown_extractor.py` | Optional MarkItDown text |
| [templatetags](templatetags/) | `templatetags/` | Template tags |
| [static](static/) | `static/js/` | Client JavaScript |

**Excluded:** `locales/*.json`, Django migrations.

---

## Related

- [Apps/_index](../_index/)
