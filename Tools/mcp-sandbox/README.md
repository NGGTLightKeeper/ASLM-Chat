# mcp-sandbox

Sandbox v2 is the workspace and execution server for code, files, OCR, and Linux CLI work.

## Public tools

The model sees three tools:

- `bash(command, cwd=".", timeout_s=60, stdin=None)` — universal interface
- `write(path, content)` — create or overwrite a file
- `edit(path, old_str, new_str, replace_all=False)` — surgical text replacement

## Bash supervisor

Simple shell commands are transparently routed to internal structured tools
for safety, path validation, and structured output. Compound commands (pipes,
chains, subshells) and execution commands go to real bash inside a Docker
container.

Routed commands include:

| Shell command | Internal operation |
| --- | --- |
| `cat`, `head`, `tail`, `less`, `more` | `read(path, ...)` |
| `ls`, `tree` | `ls(path, ...)` |
| `find`, `fd` | `find(path, ...)` |
| `grep`, `rg`, `egrep` | `grep(pattern, ...)` |
| `sed -n '10,50p' file` | `read(path, start_line, end_line)` |
| `wc`, `file`, `stat` | file metadata via `read(...)` |
| `mkdir`, `touch` | `mkdir(...)` / `write(...)` |
| `mv` | `move(src, dst)` |
| `cp` (single file) | `read(...)` + `write(...)` |
| `rm` | `delete(path, ...)` |
| `pwd` | returns workspace root |

Everything else (python, pytest, git, npm, pip, curl, etc.) goes to real bash.

## Result envelope

Every tool returns the same shape:

```json
{
  "ok": true,
  "tool": "bash",
  "result": {},
  "error": null,
  "warnings": [],
  "truncated": false
}
```

Routed bash results include `"routed": true` inside the result object.

## Workflow

Typical coding flow:

```text
bash("ls -la")
bash("grep -rn 'pattern' .")
bash("cat file.py")
edit("file.py", old_str, new_str)
bash("python file.py")
```
