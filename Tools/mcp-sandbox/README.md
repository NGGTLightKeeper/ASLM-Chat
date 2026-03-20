# mcp-sandbox

Unified MCP server that combines file operations, Linux shell execution, OCR, image display, and localhost sharing behind one Docker-managed sandbox.

## Tools

- `status()` - Docker, container, workspace, and limits status.
- `list_directory(path=".", recursive=False, max_depth=3)` - list workspace files.
- `read_file(path, start_line=None, end_line=None)` - read text files with optional numbered ranges.
- `write_file(path, content)` - write UTF-8 files directly in the bind-mounted workspace.
- `str_replace(path, old_str, new_str)` - unique exact-match replacement with numbered context.
- `bash(command, cwd="task", timeout_s=60, stdin=None)` - execute bash inside the Linux container.
  If `cwd` is omitted, commands run in the default task folder.
- `show_image(path)` - inline image rendering for MCP clients that support `ImageContent`.
- `share(path)` - download link for files or preview link for HTML apps.
- `import_from_host(host_path, dest_path=None)` - import files from approved host roots into the workspace.
- `reset(preserve_workspace=True)` - recreate the container from the base image.
- `snapshot(name="stable")` - `docker commit` checkpoint.
- `restore(name="stable", preserve_workspace=True)` - recreate the container from a saved snapshot.

## Tool usage hints

- `status`
  Use when you need to know whether Docker is available or the container is already running.
- `list_directory`
  Use before reading or editing when you need to explore the workspace layout.
- `read_file`
  Use for exact source inspection. Prefer line ranges for large files.
- `write_file`
  Use for creating new files or replacing the entire contents.
- `str_replace`
  Use for surgical edits. Always copy exact surrounding text from `read_file` so the match is unique.
- `bash`
  Main execution tool. Use for Python, shell commands, builds, package installs, grep, git, and OCR via CLI.
- `show_image`
  Special-purpose media tool. Use this when the model must visually inspect an image; `bash` cannot do that natively.
- `share`
  Use when the user needs a download link or browser preview for an artifact.
- `import_from_host`
  Use to stage external host files directly into the workspace.
- `reset`
  Use to throw away container-side mutations and return to the base image.
- `snapshot` / `restore`
  Use to save and reload prepared container states.

## Notes

- Host workspace is a single dedicated folder bind-mounted to `/workspace`.
- File tools use host IO directly and do not start Docker.
- Docker starts lazily on the first container-dependent tool.
- `reset(..., preserve_workspace=False)` and `restore(..., preserve_workspace=False)` clear the dedicated workspace contents while keeping the workspace root.
