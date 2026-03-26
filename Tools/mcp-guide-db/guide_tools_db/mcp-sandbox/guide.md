# mcp-sandbox

## Overview

`mcp-sandbox` v2 is the main workspace and execution tool family.

Use it for:
- reading and editing files in `task/`
- searching the workspace with `ls`, `find`, and `grep`
- running Linux commands with `bash`
- OCR and CLI-based processing
- image inspection through `read(...)` on image files

Do not expect artifact sharing, host imports, or lifecycle controls in the public tool layer anymore.

---

## Mental model

- The model-facing root is `task/`
- Use relative paths like `.`, `script.py`, `site/index.html`
- Specialized tools come first
- `bash(...)` is the execution escape hatch, not the default way to list/search/edit files

---

## Public tools

### `ls(path=".", depth=1, max_entries=..., include_hidden=false)`

Use to inspect workspace layout.

### `read(path, start_line=None, end_line=None, max_bytes=...)`

Universal read tool:
- text -> content + line metadata
- image -> metadata + inline preview payload
- binary -> metadata only

Use it before `edit(...)`.

### `write(path, content)`

Create a new file or fully overwrite an existing one.

### `edit(path, old_str, new_str, replace_all=false)`

Exact literal replacement tool.

Rules:
- fails if `old_str` is missing
- fails if it matches multiple times unless `replace_all=true`
- returns previews and diff metadata

### `find(path=".", name_pattern=None, type="any", max_depth=8, max_results=...)`

Use for path discovery when you know filename shape but not exact location.

### `grep(pattern, path=".", glob=None, case_sensitive=false, context_before=0, context_after=0, max_results=...)`

Use for structured text search across the workspace.

### `bash(command, cwd=".", timeout_s=60, stdin=None)`

Use for:
- Python execution
- package installs inside container
- tests and builds
- OCR
- shell-native tooling

Prefer `write(...)` then `bash(...)` for non-trivial logic.

---

## Optional advanced tools

Only when `SANDBOX_ADVANCED_TOOLS=true`:
- `mkdir(path, parents=true)`
- `move(src, dst, overwrite=false)`
- `delete(path, recursive=false)`

These are convenience tools so the model does not need to fall back to shell for simple filesystem mutations.

---

## Result contract

Every tool returns:

```json
{
  "ok": true,
  "tool": "read",
  "result": {},
  "error": null,
  "warnings": [],
  "truncated": false
}
```

The only tool-specific payload lives inside `result`.

---

## Recommended workflows

### Code change

```text
ls(...)
read(...)
edit(...) or write(...)
bash(...)
read(...)
```

### Search within repo-like workspace

```text
find(...)
grep(...)
read(...)
```

### Image verification

```text
read("chart.png")
```

If `result.kind == "image"`, the tool can provide inline preview data for the model.

### OCR

```text
bash("tesseract page.png stdout -l rus+eng", timeout_s=120)
```

---

## Critical rules

1. Prefer `ls/find/grep/read/edit/write` before `bash`.
2. Always `read(...)` before `edit(...)`.
3. Use `write(...)` only for full rewrites or new files.
4. Treat `bash(...)` as execution, not as the main file API.
5. Use relative paths, not host absolute paths.

---

## Common mistakes

| Mistake | Better path |
| --- | --- |
| `bash("find . -name ...")` for discovery | `find(...)` |
| `bash("grep -R ...")` for workspace search | `grep(...)` |
| blind `edit(...)` from memory | `read(...)` then `edit(...)` |
| separate image tool mental model | `read("image.png")` |
