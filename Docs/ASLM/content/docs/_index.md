---
title: "ASLM Chat documentation"
draft: false
---

**ASLM Chat** (`aslm-chat`) is the official **ASLM host module** for local chat: a Django web UI, SQLite data layer, multi-engine LLM backends, and MCP tools. The host loads the module from `ASLM_Module.json` and runs [`main`](../ASLM-Chat/main/) inside the ASLM desktop shell.

This site documents the **ASLM-Chat repository** (Python and client-side JavaScript) and **patch notes**.

---

## Terminology

| Name | Meaning |
| --- | --- |
| **ASLM** (host) | The Windows desktop host in the main ASLM repository |
| **ASLM Chat** (module) | This chat module (`aslm-chat`) |
| **`ASLM/` package** | Django project package in this repo — not the MAUI host application |
