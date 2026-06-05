---
title: "Services"
draft: false
icon: "hub"
---

## Package `Services`

Runtime services for [main](../main/), engine adapters, and the UI.

---

## Module map

| Doc | Source | Role |
| --- | --- | --- |
| [aslm_interop_client](aslm_interop_client/) | `aslm_interop_client.py` | HTTP client to ASLM host interop API |
| [downloads_bridge](downloads_bridge/) | `downloads_bridge.py` | Ollama library catalog stdin/stdout bridge |
| [venv_manager](venv_manager/) | `venv_manager.py` | `Data/venvs/*` lifecycle |
| [user_mcp_client](user_mcp_client/) | `user_mcp_client.py` | User `mcp.json` MCP client |
| [tool_worker](tool_worker/) | `tool_worker.py` | Subprocess worker for bundled tools |
| [ollama-service](ollama-service/) | `ollama-service.py` | Managed `ollama serve` |

---

## Related

- [_index](../_index/)
