# mcp-sandbox

## Overview

`mcp-sandbox` is the primary tool for code execution, workspace file operations, artifact generation, Linux shell workflows, image inspection, and localhost sharing.

It replaces the old split-tool mental model with one cleaner model:

- one bind-mounted workspace
- one Linux container for execution
- one MCP server for files, execution, media, and sharing

The workspace is visible on the host and mounted into the container as `/workspace`.

Practical organization rule:

- treat `task/` as the model-facing workspace root
- use paths relative to that root such as `job.py`, `site/index.html`, or `.`
- never prefix model paths with `task/` or `/workspace/...`

---

## Core Mental Model

Think of `mcp-sandbox` as two layers behind one tool family:

1. **Workspace layer**
   Host-side file operations on the shared workspace.
   These do not require Docker startup.

2. **Execution layer**
   Linux container execution through `bash(...)`.
   This is where Python, shell commands, package installs, OCR, and CLI tools run.

Use the workspace layer to inspect and edit files.
Use the execution layer to run things.

---

## Tool Call Syntax

If your client uses XML-style tool calls, arguments must be wrapped in explicit parameter tags.

Correct:

```xml
<tool_call>
  <function=bash>
    <parameter=command>pwd</parameter>
  </function>
</tool_call>
```

Incorrect:

```xml
<tool_call>
  <function=bash> command=pwd </function>
</tool_call>
```

Rule:

- never place `command=...` directly after `<function=...>`
- always use `<parameter=name>...</parameter>` for every provided argument

Example with optional parameters:

```xml
<tool_call>
  <function=bash>
    <parameter=command>python report.py</parameter>
    <parameter=cwd>.</parameter>
    <parameter=timeout_s>120</parameter>
  </function>
</tool_call>
```

---

## Available Tools

### `status()`

Inspect Docker availability, container state, configured image, workspace mount, and active limits.

Use it when:

- the first `bash(...)` call failed
- you need to explain runtime state
- you want to verify whether Docker is sleeping or the container is missing

```json
{ "tool": "status" }
```

---

### `list_directory(path=".", recursive=False, max_depth=3)`

List files and directories inside the model workspace.

Use it when:

- you need to explore the sandbox layout
- you do not yet know the exact file path
- you want to inspect what is already present in the working directory

```json
{ "tool": "list_directory", "path": "." }
```

Recursive example:

```json
{ "tool": "list_directory", "path": ".", "recursive": true, "max_depth": 2 }
```

---

### `read_file(path, start_line=None, end_line=None)`

Read a text file from the workspace.

Use it for:

- source code
- configs
- logs
- generated reports
- verifying exact text before `str_replace(...)`

For large files, prefer line ranges.

```json
{ "tool": "read_file", "path": "report.py" }
```

```json
{ "tool": "read_file", "path": "report.py", "start_line": 40, "end_line": 90 }
```

---

### `write_file(path, content)`

Create or fully overwrite a UTF-8 text file in the workspace.

Use it when:

- creating a new script
- generating HTML/CSS/JS
- writing configs
- replacing an entire file is simpler than editing part of it

```json
{ "tool": "write_file", "path": "job.py", "content": "print('hello')\n" }
```

---

### `str_replace(path, old_str, new_str)`

Surgical exact-match edit for text files.

This is the main safe editing tool.

Rules:

- `old_str` must match exactly once
- if it matches 0 times or multiple times, the tool errors instead of guessing
- `new_str=""` is allowed for deletion
- response includes numbered context after the replacement

Best practice:

1. `read_file(...)`
2. copy the exact current text block
3. call `str_replace(...)` with enough surrounding context to make the match unique

```json
{
  "tool": "str_replace",
  "path": "job.py",
  "old_str": "print('old')",
  "new_str": "print('new')"
}
```

Avoid using it blind.

Wrong:

```text
str_replace("job.py", "return x", "return y")
```

Right:

```text
read_file("job.py", start_line=60, end_line=90)
copy exact surrounding block
str_replace(...)
```

---

### `bash(command, cwd=".", timeout_s=60, stdin=None)`

Primary execution tool inside the Linux container.

Use it for:

- Python execution
- package installation
- shell commands
- git
- grep, ripgrep, sed, find
- OCR with Tesseract
- builds, tests, conversions, CLI tools

The working directory is always relative to the model-facing `task/` root.
Use `.` for that root. Do not pass `task`, `task/...`, or `/workspace/...`.

```json
{ "tool": "bash", "command": "pwd" }
```

```json
{ "tool": "bash", "command": "python job.py", "cwd": "." }
```

```json
{ "tool": "bash", "command": "tesseract page.png stdout -l rus+eng" }
```

Rules of thumb:

- use `bash(...)` as the default execution path
- prefer writing a real script file before running non-trivial logic
- if output is large, pipe through `tail`, `head`, `rg`, or `grep`
- on timeout the container may be restarted to clear stuck processes

---

### `show_image(path)`

Display an image to the model directly in chat.

This exists because shell output cannot provide real visual understanding.

Use it for:

- screenshots
- plots
- diagrams
- generated images
- validating rendered output before sharing

```json
{ "tool": "show_image", "path": "chart.png" }
```

Important:

- `bash(...)` can inspect metadata or OCR text
- only `show_image(...)` gives the model direct access to image pixels

---

### `share(path)`

Create a localhost share link for a file or HTML app.

Behavior:

- file -> download link
- `.html` file -> preview link
- directory with `index.html` -> app preview link

Use it after generating artifacts for the user.

```json
{ "tool": "share", "path": "report.pdf" }
```

```json
{ "tool": "share", "path": "site" }
```

---

### `import_from_host(host_path, dest_path=None)`

Copy a file or directory from an allowed host location into the workspace.

Default destination is the default task folder.

Use it when:

- the user has a host file outside the workspace
- a chat upload needs to be staged into the sandbox
- an external folder must be copied into the workspace for processing

```json
{
  "tool": "import_from_host",
  "host_path": "C:/Users/.../.lmstudio/user-files/data.csv",
  "dest_path": "data.csv"
}
```

---

### `reset(preserve_workspace=True)`

Recreate the container from the base image.

Use it when:

- the environment is polluted
- you installed bad packages
- a process got stuck
- you want a clean container state

By default the workspace is preserved. If you disable preservation, the dedicated workspace contents are cleared.

---

### `snapshot(name)` / `restore(name)`

Save and reload prepared container states.

Use snapshots when you spent time preparing an environment and want a checkpoint.

```json
{ "tool": "snapshot", "name": "stable" }
```

```json
{ "tool": "restore", "name": "stable" }
```

---

## Recommended Workflows

### 1. Non-trivial Python or shell task

```text
get_guide("mcp-sandbox")
list_directory(...) if needed
write_file("task.py", ...)
bash("python task.py")
read_file(...) or show_image(...)
share(...) if user needs artifact
```

### 2. Surgical file fix

```text
read_file("task.py", start_line=...)
str_replace(...)
bash("python task.py")
```

### 3. OCR from image

```text
bash("tesseract page.png stdout -l rus+eng")
```

If visual layout matters too:

```text
show_image("page.png")
```

### 4. HTML app generation

```text
write_file("site/index.html", ...)
write_file("site/style.css", ...)
write_file("site/app.js", ...)
share("site")
```

### 5. Data or artifact pipeline

```text
import_from_host(...) if needed
write_file("process.py", ...)
bash("python process.py")
read_file("summary.txt") or show_image(...)
share("result.xlsx")
```

---

## Tool Selection Guide

| Goal | Best tool |
|------|-----------|
| Explore workspace | `list_directory` |
| Read exact file contents | `read_file` |
| Create or fully replace a file | `write_file` |
| Patch one exact code block | `str_replace` |
| Run code or shell commands | `bash` |
| Inspect an image visually | `show_image` |
| OCR an image | `bash("tesseract ...")` |
| Deliver artifact to user | `share` |
| Stage host file into workspace | `import_from_host` |
| Clean container state | `reset` |
| Save or reload environment | `snapshot` / `restore` |

---

## Critical Rules

1. For non-trivial execution, prefer write-then-run instead of giant inline commands.
2. Read before `str_replace`; do not patch from memory.
3. Keep outputs and code in the single workspace unless a subfolder helps.
5. Use `show_image(...)` when the task requires actual visual understanding.
6. Use `share(...)` after successful artifact creation.
7. Do not treat host shell and sandbox container as the same environment.

---

## Common Mistakes

| # | Mistake |
|---|---------|
| 1 | Using `bash(...)` to inspect an image visually instead of `show_image(...)` |
| 2 | Calling `str_replace(...)` without first reading the exact current file |
| 3 | Spreading files into unnecessary subfolders when one workspace directory is enough |
| 4 | Re-pasting the same long script inline instead of writing it once to a real file |
| 5 | Using host shell assumptions to reason about container packages or cwd |
| 6 | Forgetting `share(...)` after generating the final artifact |

---

## Summary

| Field | Value |
|------|-------|
| Primary execution tool | `bash(...)` |
| Primary edit tools | `write_file(...)`, `str_replace(...)` |
| Visual tool | `show_image(...)` |
| Artifact delivery | `share(...)` |
| OCR path | `bash("tesseract ...")` |
| Main mental model | Shared workspace + Linux container execution |
