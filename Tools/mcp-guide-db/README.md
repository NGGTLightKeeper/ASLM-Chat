# mcp-guide-db

Unified MCP server for tool guides and modular guide-memory snippets.

It serves two roles through one tool surface:
- read assembled guides on demand
- manage reusable snippet modules inside `guide_tools_db/`

---

## Purpose

Instead of spreading guide reads and guide-memory writes across separate MCP servers, `mcp-guide-db` exposes both in one place.

Use it to:
- discover which guides exist
- retrieve one assembled guide
- inspect snippet inventory for a guide
- create, extend, and deprecate snippet modules

---

## MCP Tools

### `list_guides()`

Returns an indexed list of logical guides. Folder-based guides are preferred over legacy flat files when both exist.

### `get_guide(name_or_index)`

Retrieves one assembled guide:
- `guide.md`
- active local snippets from `snippets/`
- active external synergy snippets from other guides whose `related_tools` include the requested guide

Deprecated snippets under `_deprecated/` are excluded.

### `list_snippets(guide, include_deprecated=false)`

Lists snippet metadata for a guide as JSON.

### `create_snippet(guide, slug, title, kind, body, source_task, related_tools=[])`

Creates a new snippet under `mcp-guide-db/guide_tools_db/<guide>/snippets/<slug>.md`.

Allowed `kind` values:
- `pattern`
- `synergy`
- `pitfall`
- `example`

New snippets default to:
- `status: active`
- `verification: unverified`

### `append_snippet(guide, snippet, content, note)`

Appends a dated `## Addendum (YYYY-MM-DD)` block and refreshes `updated_at`.

### `deprecate_snippet(guide, snippet, reason)`

Moves an active snippet into `_deprecated/`, marks it `deprecated`, and records:
- `deprecated_at`
- `deprecation_reason`

Hard delete is intentionally not exposed.

---

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `GUIDE_DB_DIR` | `./guide_tools_db` | Root directory containing guide folders and legacy `.md` files |

---

## Guide Database Format

Preferred layout:

```text
mcp-guide-db/
  guide_tools_db/
  mcp-web-search/
    guide.md
    snippets/
      search_plus_browser.md
    _deprecated/
  mcp-sandbox/
    guide.md
    snippets/
```

Legacy flat files such as `mcp-guide-db/guide_tools_db/mcp-web-search.md` remain readable during migration.

Snippet modules are Markdown files with YAML frontmatter. Expected fields:
- `title`
- `kind`
- `status`
- `verification`
- `created_at`
- `updated_at`
- `source_task`
- `related_tools`

---

## Safety Model

- All snippet writes are confined to `mcp-guide-db/guide_tools_db/`
- Path traversal is rejected
- If a guide still exists only as a legacy flat file, `guide.md` is bootstrapped from that file before snippet writes
- Deprecated snippets are moved into `_deprecated/`; physical deletion is manual

---

## Project Structure

```text
mcp-guide-db/
  guide_db_mcp.py
  guide_tools_db/
    mcp-web-search/
      guide.md
      snippets/
      _deprecated/
    mcp-web-search.md   # optional legacy fallback
```

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
