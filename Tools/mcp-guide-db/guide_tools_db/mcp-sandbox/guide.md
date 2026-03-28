# mcp-sandbox

## What it is

`mcp-sandbox` is the primary workspace and execution environment.
Everything runs inside a sandboxed `task/` directory.
Use relative paths from `task/` root.

---

## Tools

### `bash(command, cwd=".", timeout_s=60, stdin=None)`

Universal shell interface. Handles navigation, search, file reading, execution, git, downloads, data processing.

### `write(path, content)`

Create a new file or fully overwrite an existing one.
Use only for new files or complete rewrites.

### `edit(path, old_str, new_str, replace_all=false)`

Exact literal string replacement inside a file.
Fails if `old_str` is not found or matches multiple times (unless `replace_all=true`).
Always read the file before editing -- never guess `old_str`.

---

## Result contract

Every tool returns a JSON envelope:

```json
{
  "ok": true/false,
  "tool": "bash|write|edit",
  "result": {},
  "error": null,
  "warnings": [],
  "truncated": false
}
```

---

## Golden rules

1. `bash` is the primary tool for navigation, search, and reading. Do not guess paths.
2. Always read before `edit`. Use `bash("cat ...")` or `bash("sed -n ...")`.
3. Use `write` only for full rewrites or new files.
4. For cloning repos: `bash("git clone URL task/dirname")`.
5. For large file downloads (>50 MB): `bash("curl -L -o task/file URL")`.
6. Use relative paths inside `task/`, not host absolute paths.
7. After 3 file reads, stop and assess whether you can answer.

---

## Common mistakes

| Mistake | Correct approach |
| --- | --- |
| `read_page(github_url)` to inspect a repo | `bash("git clone URL task/repo")` |
| `import_web_file(github_url)` | `bash("git clone URL task/repo")` |
| Editing blindly from memory | `bash("cat file")` then `edit(...)` |
| Using `write` for a one-line change | `edit(path, old_str, new_str)` |
| Sequential `cat` on every file in a dir | `grep` first, then targeted reads |

---

## What bash can do

- Navigation and structure: `ls`, `tree`, `pwd`, `du`, `stat`, `file`, `find`
- Reading: `cat`, `head`, `tail`, `sed -n`
- Search: `grep -rn`, `find . -name`, `rg`, `fd`
- Filesystem: `mkdir -p`, `mv`, `cp`, `rm`, `touch`, `chmod`
- Execution: `python`, `pytest`, `npm`, `pip`, `cargo`, `make`, `go`, `dotnet`
- Git: `git clone`, `git log`, `git diff`, `git status`
- Downloads: `curl -L -o`, `wget`
- Data processing: `jq`, `awk`, `sort`, `uniq`, `ffmpeg`, `convert`, `tar`, `unzip`
