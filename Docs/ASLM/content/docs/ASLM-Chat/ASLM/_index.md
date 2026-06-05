---
title: "ASLM"
draft: false
icon: "settings_applications"
---

## Package `ASLM`

Django project package for ASLM-Chat (not the MAUI ASLM host). URL routing, WSGI/ASGI, and project settings from [Settings/settings](../Settings/settings/).

---

## Module map

| Doc | Source | Role |
| --- | --- | --- |
| [settings](settings/) | `settings.py` | `INSTALLED_APPS`, DB, middleware, static, engine URLs |
| [urls](urls/) | `urls.py` | Admin + `Apps.UI` routes |
| [wsgi](wsgi/) | `wsgi.py` | WSGI `application` for [main](../main/) |
| [asgi](asgi/) | `asgi.py` | ASGI entry for async servers |

---

## Related

- [_index](../_index/)
