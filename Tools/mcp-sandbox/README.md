# mcp-sandbox

Sandbox v2 is the workspace and execution server for code, files, OCR, and Linux CLI work.

## Public tools

Core tools:
- `ls(path=".", depth=1, max_entries=...)`
- `read(path, start_line=None, end_line=None, max_bytes=...)`
- `write(path, content)`
- `edit(path, old_str, new_str, replace_all=False)`
- `find(path=".", name_pattern=None, type="any", max_depth=8, max_results=...)`
- `grep(pattern, path=".", glob=None, case_sensitive=False, context_before=0, context_after=0, max_results=...)`
- `bash(command, cwd=".", timeout_s=60, stdin=None)`

Optional advanced tools when `SANDBOX_ADVANCED_TOOLS=true`:
- `mkdir(path, parents=True)`
- `move(src, dst, overwrite=False)`
- `delete(path, recursive=False)`

Removed from the public model-facing API:
- `status`
- `reset`
- `snapshot`
- `restore`
- `share`
- `import_from_host`
- `show_image`
- legacy names such as `list_directory`, `read_file`, `write_file`, `str_replace`

## Result envelope

Every tool returns the same shape:

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

Errors are typed:

```json
{
  "ok": false,
  "tool": "edit",
  "result": {},
  "error": {
    "type": "match_not_found",
    "message": "old_str not found in file."
  },
  "warnings": [],
  "truncated": false
}
```

## Usage notes

- Prefer specialized tools before `bash`.
- Treat `task/` as the workspace root and use relative paths like `.` or `src/app.py`.
- `read` is universal:
  - text files return content and line metadata
  - binary files return metadata only
  - images return metadata plus inline preview payload when small enough
- `write` is for full file creation or overwrite.
- `edit` is for exact literal replacements and fails on ambiguous matches unless `replace_all=true`.
- `bash` is the escape hatch for execution, installs, tests, builds, and OCR.

## Workflow

Typical coding flow:

```text
ls(...)
read(...)
write(...) or edit(...)
bash(...)
read(...) again if you need output or visual image inspection
```
