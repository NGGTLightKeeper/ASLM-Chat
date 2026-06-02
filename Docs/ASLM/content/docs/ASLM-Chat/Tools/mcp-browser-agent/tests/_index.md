---
title: "tests"
draft: false
---

## Package `tests`

`Tools/mcp-browser-agent/tests/` — Pytest suite for MCP bridge contracts, snapshot formatting, screenshot vision gating, worker helpers, and text editor helpers.

---

## Module map

| Doc | Source | Role |
| --- | --- | --- |
| [conftest](conftest/) | `conftest.py` | Loads `mcp-server.py` as `bridge_module` |
| [test_mcp_bridge_contract](test_mcp_bridge_contract/) | `test_mcp_bridge_contract.py` | MCP metadata and `call_tool` routing |
| [test_browser_snapshot_format](test_browser_snapshot_format/) | `test_browser_snapshot_format.py` | A11y snapshot formatting |
| [test_browser_screenshot](test_browser_screenshot/) | `test_browser_screenshot.py` | PNG dimensions and vision gating |
| [test_browser_process_helpers](test_browser_process_helpers/) | `test_browser_process_helpers.py` | Worker IPC helpers |
| [test_browser_text](test_browser_text/) | `test_browser_text.py` | Editor line/range helpers |

---

## Related

- [mcp-browser-agent](../_index/)
