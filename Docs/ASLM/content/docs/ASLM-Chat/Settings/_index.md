---
title: "Settings"
draft: false
icon: "settings"
---

## Package `Settings`

Module configuration, host snapshots, MCP JSON, skills, and console helpers.

---

## Module map

| Doc | Source | Role |
| --- | --- | --- |
| [settings](settings/) | `settings.py` | `settings.json` load/save, engines, env overlay |
| [first_run](first_run/) | `first_run.py` | Initial settings and venv bootstrap |
| [mcp_json](mcp_json/) | `mcp_json.py` | `MCP/mcp.json` validation |
| [skills](skills/) | `skills.py` | `Skills/` tree and sandbox mirror |
| [host_theme](host_theme/) | `host_theme.py` | Host theme JSON snapshots |
| [host_locale](host_locale/) | `host_locale.py` | Host locale JSON snapshots |
| [console](console/) | `console.py` | Startup banner from `ASLM_Module.json` |
| [module_manifest_locale](module_manifest_locale/) | `module_manifest_locale.py` | Patch manifest string catalogs for host UI |

---

## Related

- [_index](../_index/)
