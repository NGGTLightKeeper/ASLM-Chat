# mcp-guide-db

Unified MCP server for tool guides, workflow recipes, and modular guide-memory snippets.

It serves three roles through one tool surface:
- read assembled guides on demand
- discover and load task-specific workflow recipes
- manage reusable snippet modules inside `guide_tools_db/`

---

## Purpose

`mcp-guide-db` provides structured guidance for tool usage through three layers:

1. **Core Guides** -- compact tool cards with semantics, rules, and common mistakes
2. **Recipes** -- curated step-by-step workflows for common task types (repo analysis, code editing, PDF processing, etc.)
3. **Snippets** -- field notes and learned patterns from past tasks

---

## MCP Tools

### `list_guides()`

Returns an indexed list of logical guides.

### `get_guide(name_or_index, mode="core")`

Retrieves one assembled guide. Modes:

- `core` -- guide.md + recipe index (titles and triggers only)
- `core+recipes` -- guide.md + full recipe content
- `full` -- guide.md + full recipes + active snippets

### `list_recipes(guide=None)`

Lists available workflow recipes. Optionally filtered by guide name.
Each recipe entry shows: slug, title, domain, and trigger description.

### `get_recipe(name_or_query)`

Retrieves a specific recipe by:
- exact slug (e.g. `repo-analysis`)
- partial name match
- search query (matches title, domain, trigger, tools)

Returns the full recipe with goal, workflow steps, stop conditions, and anti-patterns.

### `list_snippets(guide, include_deprecated=false)`

Lists snippet metadata for a guide as JSON.

### `create_snippet(guide, slug, title, kind, body, source_task, related_tools=[])`

Creates a new snippet under `guide_tools_db/<guide>/snippets/<slug>.md`.

Allowed `kind` values: `pattern`, `synergy`, `pitfall`, `example`.

### `append_snippet(guide, snippet, content, note)`

Appends a dated addendum block and refreshes `updated_at`.

### `deprecate_snippet(guide, snippet, reason)`

Moves an active snippet into `_deprecated/`.

---

## Guide Database Format

```text
guide_tools_db/
  mcp-sandbox/
    guide.md              <-- compact tool card (Layer A)
    recipes/              <-- curated workflows (Layer B)
      repo-analysis.md
      targeted-code-edit.md
      pdf-processing.md
      reverse-engineering.md
      archive-triage.md
      media-conversion.md
      web-file-import.md
    snippets/             <-- field notes (Layer C)
    _deprecated/

  mcp-web-search/
    guide.md
    recipes/
    snippets/
    _deprecated/
```

### Recipe file format

Recipes use YAML frontmatter:

```yaml
---
title: "Repository Analysis"
domain: code-analysis
trigger: "User asks to analyze a git repository"
tools: [bash, grep, find, cat, sed]
related_guides: [mcp-sandbox]
difficulty: medium
---

## Goal
...
## When to use
...
## When NOT to use
...
## Workflow
...
## Stop conditions
...
## Anti-patterns
...
```

---

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `GUIDE_DB_DIR` | `./guide_tools_db` | Root directory containing guide folders |

---

## Safety Model

- All writes are confined to `guide_tools_db/`
- Path traversal is rejected
- Recipes are read-only through MCP (curated by humans)
- Snippets are writable through create/append/deprecate
- Deprecated snippets are moved, not deleted

---

## MCP Configuration (`mcp.json`)

```json
{
  "guide-db": {
    "command": "C:/Users/.../python.exe",
    "args": ["C:/Users/.../mcp-guide-db/guide_db_mcp.py"],
    "timeout": 30000
  }
}
```
