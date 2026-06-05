---
title: "Tools"
draft: false
icon: "build"
---

## Tools

Supporting utilities under `Tools/` used by ASLM Chat and local workflows.

| Doc | Source | Role |
| --- | --- | --- |
| [update_model_runtime_metadata](update_model_runtime_metadata/) | `update_model_runtime_metadata/` | Refresh `model_runtime_metadata.json` from live endpoints |
| [context_compression](context_compression/) | `context_compression/` | History compression for long chats |
| [mcp-browser-agent](mcp-browser-agent/) | `mcp-browser-agent/` | Playwright browser automation MCP |
| [mcp-sandbox](mcp-sandbox/) | `mcp-sandbox/` | Docker Linux sandbox MCP |
| [mcp-web-search](mcp-web-search/) | `mcp-web-search/` | Web search and read-page MCP |

---

## Documentation conventions

Paths mirror `Tools/<tool>/…` in the repository. See [ASLM-Chat/_index](../_index/) for global rules.

| Level | Use for |
| --- | --- |
| `## Tool \`name\`` | Tool root `_index.md` only |
| `## Package \`name\`` | Package `_index.md` |
| `## Module \`name\`` | Leaf `.py` page |
| `## Public functions` / `## Private functions` | Grouped `def` members |
| `#### \`def name(...)\`` | **Purpose:** and **Steps:** per symbol |
| `## Test methods` | `tests/test_*.py` and `tests.py` |

Do **not** use `## \`function_name\`` in the sidebar.

---

## Integration

[`Apps.UI/views`](../Apps/UI/views/) adds `Tools/` to `sys.path` and imports [context_compression/history_compressor](context_compression/history_compressor/).
