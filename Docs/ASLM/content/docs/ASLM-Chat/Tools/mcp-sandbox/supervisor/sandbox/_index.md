---
title: "sandbox package"
draft: false
---

## Package `sandbox`

`Tools/mcp-sandbox/supervisor/sandbox/` — In-container MCP implementation (import name `sandbox` when `supervisor/` is on `sys.path`).

All tools return the **v2 envelope** from [responses](responses/): `{ok, tool, result, error, warnings, truncated}`.

---

## Module map

| Doc | Source | Role |
| --- | --- | --- |
| [config](config/) | `config.py` | `sandbox.env`, limits, paths |
| [responses](responses/) | `responses.py` | Success/error helpers |
| [workspace](workspace/) | `workspace.py` | Secure paths and file CRUD |
| [api](api/) | `api.py` | `handle_tool`, bash supervision |
| [exec](exec/) | `exec.py` | Native bash subprocess |
| [jobs](jobs/) | `jobs.py` | Background job registry |
| [container](container/) | `container.py` | Native `jobs`/`fg`/`kill` |
| [intent](intent/) | `intent.py` | Command classifier |
| [controller](controller/) | `controller.py` | Intent handlers |
| [session_state](session_state/) | `session_state.py` | Exploration state |
| [presenters](presenters/) | `presenters.py` | Preview formatters |
| [cleanup](cleanup/) | `cleanup.py` | Idle workspace cleanup |
| [tools](tools/) | `tools.py` | FastMCP wrappers |
| [supervisor](supervisor/) | `supervisor.py` | `FastMCP.run()` entry |

---

## Related

- [mcp-sandbox](../../_index/)
