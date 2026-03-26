# mcp-web-search

MCP server for web search and deep research. Provides three tools: fast search via YaCy + DDGS, page reading, and an autonomous multi-step research agent.

---

## Project Structure

```
mcp-web-search/
├── config.py                  # Universal config (MCP server + deep-research)
├── src/
│   └── server.py              # MCP server (all three tools)
├── deep-research/
│   ├── scripts/
│   │   └── deep_research.py   # Main research pipeline
│   ├── src/
│   │   ├── config.py          # Backward-compat proxy → ../config.py
│   │   ├── models.py          # DataClass models (SearchResult, ExtractedSource, ResearchState)
│   │   ├── ddgs_client.py     # DDGS client (multi-backend, cache, fallback)
│   │   ├── yacy_client.py     # YaCy client (local index)
│   │   ├── extractor.py       # Content extraction (Trafilatura + Playwright)
│   │   ├── llm_client.py      # OpenAI-compatible LLM client (LM Studio)
│   │   ├── semantic.py        # Semantic filtering (sentence-transformers)
│   │   ├── gliner_wrapper.py  # NER density filter (GLiNER)
│   │   └── trust_registry.py  # Domain trust registry (Tiers A/B/C)
│   ├── config/
│   │   └── trust_registry.json
│   ├── _out/                  # Generated reports
│   ├── _cache/                # SQLite DDGS cache
│   └── resume_report.py       # Re-synthesize report from existing sources.md
├── config/
│   ├── search_config.json     # Search and extraction parameters
│   └── trust_registry.json    # Domain trust registry (for MCP server)
├── services/
│   └── yacy/
│       ├── docker-compose.yml # YaCy Docker configuration
│       └── seeds.json         # Initial crawl seed URLs
├── requirements.txt
└── README.md
```

---

## MCP Tools

### `web_search(query, limit=10, engine="auto")`

Search the internet and local YaCy index.

**Parameters:**
- `query` — search query (English recommended, 1–5 words)
- `limit` — maximum number of results (default: 10)
- `engine` — search source:
  - `"auto"` — YaCy first (local cache), then DDGS if results are insufficient
  - `"yacy"` — local index only (fast, offline)
  - `"ddgs"` — external search via DDGS only

**Behavior:**
- `Preview` now uses a denser cleanup pipeline: DOM noise stripping -> article extraction -> boilerplate removal -> optional semantic chunk selection
- `legacy` mode keeps the cleaned dense preview without semantic chunking; `semantic` mode compresses to the most relevant chunks (E5) and allows soft result reranking
- Results from trusted DDGS domains are automatically submitted to YaCy for indexing (self-learning)
- Blocks PDF, video, social media (YouTube, Twitter/X, TikTok, Vimeo)

**Preview mode config (`config.py`):**
- `WEB_SEARCH_MODE = "semantic"` (default) or `"legacy"`
- `WEB_SEARCH_PREVIEW_PROFILE = "speed" | "balanced" | "quality"` tunes preview density and latency
- `WEB_SEARCH_PREVIEW_RERANK = "soft" | "off"` controls post-preview result reordering in single-query mode
- `WEB_SEARCH_SEMANTIC_REQUIRE_CUDA = True` requires CUDA for `semantic` mode
- On CUDA/model initialization error, automatically falls back to `legacy`

**Output format:**
```
[N] 🌐 WEB 🔍 DDGS
Title   : ...
URL     : ...
Snippet : ...
Preview : ...
```

---

### `read_page(url)`

Reads a page and returns cleaned text.

**Parameters:**
- `url` — string (single URL) or list of strings (parallel reading)
- LLM can pass a list as a string `["url1", "url2"]` — automatically parsed

**Extraction strategy:**
1. Tries to use `ingest.router` (if available)
2. Fallback: HTTP via `httpx` + script/style/tag removal, up to 12,000 characters

**Automatically skips:** PDF, MP4, MP3, AVI, ZIP, EXE, YouTube, Twitter/X, Vimeo, TikTok

---

### `deep_research(query, depth="medium")`

Autonomous multi-step research agent. Runs `deep-research/scripts/deep_research.py` as a subprocess.

**Parameters:**
- `query` — research question (English preferred, detailed)
- `depth`:
  - `"low"` — 4 queries, up to 8 sources, 2 iterations (~3–5 min)
  - `"medium"` — 6 queries, up to 23 sources, 4 iterations (~7–10 min)
  - `"high"` — 10 queries, up to 60 sources, 10 iterations, Playwright (~15+ min)

**Returns:** a finished Markdown report with sources. The report is saved to `_out/<task_id>/report.md`.

---

## Deep Research Pipeline

```
User Question
      │
      ▼
[1] Query Classification (query_type: general / technical / academic / ...)
      │
      ▼
[2] Search Query Generation (LLM → N English queries)
      │
      ▼
[3] Parallel Search — YaCy + DDGS (multi-backend with fallback)
      │
      ▼
[4] Result Filtering — TrustRegistry (Tiers A/B/C) + deduplication
      │
      ▼
[5] Content Extraction — Trafilatura → Playwright (if needed)
      │
      ▼
[5a] GLiNER NER filter (optional) — filters SEO filler by entity presence
      │
      ▼
[5b] Semantic Filtering — sentence-transformers, top-K chunks
      │
      ▼
[6] LLM summarization of each source
      │
      ▼
[7] Final report synthesis (LLM, up to 16,384 tokens)
      │
      ▼
  report.md
```

**Iterative mode:** after each iteration, the agent generates follow-up queries to fill gaps and repeats the cycle.

---

## Dependencies & Infrastructure

### YaCy (local search engine)

Start via Docker:
```bash
cd services/yacy
docker-compose up -d
```

Default URL: `http://localhost:8090`. Credentials: `admin` / `admin123`.

### LM Studio

LLM calls are routed to `http://localhost:1234/v1` (OpenAI-compatible API). Used for query generation, source summarization, and report synthesis.

Models are configured in `config.py`:
```python
LLM_MODEL_QUERY_GEN  = "local-model"
LLM_MODEL_SUMMARIZE  = "local-model"
LLM_MODEL_SYNTHESIS  = "local-model"
```

### DDGS (DuckDuckGo Search)

Multi-backend search via the `ddgs` package (or `duckduckgo_search` as fallback).

Backends by query type:
| Query Type    | Backends            |
|---------------|---------------------|
| `technical`   | google, brave       |
| `academic`    | google, brave       |
| `finance`     | google, bing        |
| `medical`     | google, brave       |
| `ru`          | yandex, google      |
| `general`     | auto                |

On failure, automatically tries the next backend: `google,brave` → `yandex,bing` → `duckduckgo,mojeek` → `auto`.

---

## Trust Registry

Domain trust registry in `config/trust_registry.json`. Defines source tier:

- **Tier A** — GitHub, Arxiv, Hugging Face, official docs — high weight
- **Tier B** — Stack Overflow, Wikipedia, authoritative blogs — medium weight
- **Tier C** — others — low weight

Used in two ways:
- In `web_search`: only registry domains are auto-submitted to YaCy for indexing
- In `deep_research`: source filtering and ranking

---

## ML Components (Deep Research)

### Sentence Transformers (semantic filtering)
- Model: `intfloat/multilingual-e5-small`
- Splits text into chunks → computes cosine similarity with query → keeps top-K relevant chunks
- Loaded once lazily, supports offline mode

### GLiNER (NER filter, optional)
- Model: `urchade/gliner_small-v2.1` (~150 MB, CPU-capable)
- Zero-shot NER: checks for target entities in text
- If entity count is below threshold — source is treated as SEO filler and discarded
- Disabled by default (`enable_gliner=False`), enabled automatically in `high` depth mode

---

## Installation

```bash
# 1. Create virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux/macOS

# 2. Install dependencies
pip install -r requirements.txt

# 3. (Optional) PyTorch with GPU
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

# 4. Start YaCy
cd services/yacy && docker-compose up -d
```

### MCP Configuration (mcp.json)

```json
{
  "web-search-engine": {
    "command": "C:/Users/.../python.exe",
    "args": ["-m", "src.server"],
    "cwd": "C:/Users/.../mcp-web-search"
  }
}
```

---

## Utilities

### `deep-research/resume_report.py`

Re-synthesizes `report.md` from an already-completed `sources.md` (if the main synthesis step failed).

```bash
python deep-research/resume_report.py _out/research_xxxxxxxx/
```

Useful if the pipeline completed successfully but the LLM returned garbage on the final step — allows re-running only the synthesis phase.
