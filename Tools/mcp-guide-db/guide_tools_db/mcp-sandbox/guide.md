# mcp-sandbox

## What it is

`mcp-sandbox` is the primary workspace and execution environment.
Everything runs inside a dedicated sandbox workspace root.
Use root-relative paths like `repo/README.md` or `downloads/file.pdf`.
Do not prepend `_sandbox/` — paths are already relative to the workspace root.

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

## Scope and isolation

- `bash` has full access to the entire container filesystem. Use `/etc`, `/usr`, `/tmp`, `/var` freely when needed.
- The default `cwd="."` always points to the sandbox workspace root (your personal scratch space).
- `write` and `edit` are restricted to the workspace root — they cannot write outside it.
- Files you create in the workspace root are visible on the host and persist across sessions (until `clear_workspace`).
- Files written outside the workspace root (e.g. `/tmp/`) exist only inside the container and are lost on restart.
- To place a file outside the workspace (e.g. `/etc/nginx/nginx.conf`): create it with `write` first, then move it with `bash("mv file /target/path")`.

---

## Golden rules

1. `bash` is the primary tool for navigation, search, and reading. Do not guess paths.
2. Always read before `edit`. Use `bash("cat ...")` for small files and `bash("sed -n ...")` for large or unknown files.
3. Use `write` for generated helper scripts and other full-file content you may need to correct later. Prefer `write` over `cat <<'EOF' ...` when creating a script from scratch.
4. For cloning repos: `bash("git clone URL repo")` or another root-relative target directory.
5. For large file downloads (>50 MB): `bash("curl -L -o downloads/file URL")`.
6. Use root-relative sandbox paths, not host absolute paths.
7. After 3 file reads, stop and assess whether you can answer.

---

## Common mistakes

| Mistake | Correct approach |
| --- | --- |
| `read_page(github_url)` to inspect a repo | `bash("git clone URL repo")` |
| `import_web_file(github_url)` | `bash("git clone URL repo")` |
| Editing blindly from memory | `bash("cat file")` then `edit(...)` |
| Using `write` for a one-line change | `edit(path, old_str, new_str)` |
| Creating a helper script with `cat <<'EOF' ...` | `write(path, content)` so the script can be corrected surgically if it fails |
| Sequential `cat` on every file in a dir | `grep` first, then targeted reads |
| `cat` on a generated log or manifest | `stat` first, then `grep` / `head` / `sed -n` |
| Reading only the first chunk of a generated index and then ignoring it | Keep using the index as a navigation artifact throughout the task |

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
