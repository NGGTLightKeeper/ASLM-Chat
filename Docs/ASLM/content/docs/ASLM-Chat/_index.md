---
title: "ASLM-Chat"
draft: false
icon: "developer_board"
weight: 101
---

Python and JavaScript sources for the **ASLM Chat** module (`aslm-chat`).

| Section | Doc |
| --- | --- |
| [main](main/) | Host CLI entry (`runserver`, settings bridge, Ollama runtime, downloads bridge) |
| [manage](manage/) | Django `manage.py` shim |
| [API](API/) | LLM engine adapters and MCP tool registry |
| [ASLM](ASLM/) | Django project package (`settings`, `urls`, WSGI) |
| [Services](Services/) | Host interop, venvs, MCP workers, Ollama service |
| [Settings](Settings/) | `settings.json`, first run, MCP, skills, host snapshots |
| [Apps](Apps/) | Django apps and client static assets |
| [Tools](Tools/) | MCP tool servers |

---

## Architecture overview

ASLM Chat runs as a Django app inside the ASLM host. The host launches `main.py` (server venv, `runserver`, optional `downloads_bridge`). The browser loads `Apps/UI` templates and `static/js` modules. Chat turns flow through `Apps/UI/views.py` (`chat_api`), which persists messages in `Apps/Data`, composes prompts (skills, uploads), and calls `API/llm_api.py` for the active engine adapter (`ollama`, `lms`, `openai`, `google_genai`). Tool calls go through `API/mcp.py`, which discovers `Tools/*/mcp-server.py` and runs handlers in `Services/tool_worker.py` or external user MCP servers. Long histories may be compressed via `Tools/context_compression`.

---

## Documentation conventions

Documentation paths **mirror** the repository tree: `path/to/module.py` → `Docs/.../ASLM-Chat/path/to/module.md` (or `file.js` → `file.md`).

| Artifact | Rule |
| --- | --- |
| Package directory | `_index.md` with **Module map** so Hugo keeps full menu depth |
| `tests/test_*.py` | `tests/test_foo.md` with **## Test methods** |
| Single `tests.py` | `tests.md` with **## Test methods** and `####` per test |
| `__init__.py` | Not documented — no `__init__.md` |
| Migrations | One page per migration file when present |

Reference pages follow the same outline as [ASLM C# documentation](https://github.com/nickel-grove/ASLM) (`Docs/ASLM` in the ASLM repo):

| Level | Use for |
| --- | --- |
| `## Module \`name\`` / `## File \`name.js\`` | Leaf page title |
| `## Overview` | Pipeline or role for large modules |
| `## Classes` | Types; `### \`class Name\`` for summary |
| `## Public functions` / `## Private functions` | Grouped members |
| `#### \`signature\`` | One block per function with **Purpose:** and **Steps:** when non-trivial |
| `## Test methods` | Test modules (`test_*.py`) |
| `## Related` | Parent `_index` first |

**Markdown:** use normal Hugo markdown — no blank lines between rows of one table or items in one list; blank lines only between sections or adjacent `####` blocks.

Do **not** use `## \`function_name\`` in the sidebar (use `####` under Public/Private only).

---

## Related

- [Documentation home](../)
