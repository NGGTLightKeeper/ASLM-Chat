---
title: "mcp"
draft: false
---

## Package `mcp`

`Tools/mcp-web-search/adapters/mcp/` — FastMCP stdio server and MCP-facing contracts.

`__init__.py` is an empty package marker.

---

## Module map

| Doc | Source | Role |
| --- | --- | --- |
| [server](server/) | `server.py` | `web_search` and `read_page` tools, Pydantic outputs, keepalive |
| [search_query_contract](search_query_contract/) | `search_query_contract.py` | Query/effort coercion and JSON schema |
| [search_io_logger](search_io_logger/) | `search_io_logger.py` | NDJSON debug log of tool I/O |
| [logging_setup](logging_setup/) | `logging_setup.py` | File + stderr logging for MCP process |
| [tool_descriptions](tool_descriptions/) | `tool_descriptions.py` | Tool description strings (constants only) |

---

## Related

- [adapters](../_index/)
- [mcp-server](../../mcp-server/)
