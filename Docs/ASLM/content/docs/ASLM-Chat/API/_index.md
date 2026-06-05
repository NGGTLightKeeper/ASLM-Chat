---
title: "API"
draft: false
icon: "api"
---

## Package `API`

LLM engine adapters and shared routing. [llm_api](llm_api/) selects the active engine and delegates below.

---

## Module map

| Doc | Source | Role |
| --- | --- | --- |
| [llm_api](llm_api/) | `llm_api.py` | Engine registry façade |
| [ollama](ollama/) | `ollama.py` | Ollama HTTP + managed service |
| [lms](lms/) | `lms.py` | LM Studio OpenAI-compatible API |
| [openai](openai/) | `openai.py` | OpenAI-compatible HTTP APIs |
| [google_genai](google_genai/) | `google_genai.py` | Google GenAI / Gemini |
| [mcp](mcp/) | `mcp.py` | Tool registry and execution |

Tool calling during `generate` flows through [mcp](mcp/) on all engines.

---

## Related

- [_index](../_index/)
