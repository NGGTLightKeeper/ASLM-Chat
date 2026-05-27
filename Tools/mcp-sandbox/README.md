# Linux Sandbox (`mcp-sandbox`)

General-purpose **Linux container sandbox** for ASLM-Chat. Enable the **Sandbox** tool server (`sandbox`) in the chat UI to use it.

The persistent workspace lives on the host at:

```text
<Tools/mcp-sandbox>/_sandbox/
```

Inside the container the same tree is mounted as:

```text
/workspace/_sandbox/
```

---

## Role in ASLM-Chat

| Item | Value |
|------|--------|
| Tool server id | `sandbox` |
| Host workspace root | `Tools/mcp-sandbox/_sandbox` |
| Model path prefix | `/workspace/_sandbox/...` |

When sandbox tools are enabled, `tool_context.sandbox_enabled` is true so tools (including Browser Agent screenshots) use this workspace.

**Skills** from the project `Skills/` folder are mirrored into `_sandbox/Skills/` before sandbox tool calls (`Settings/skills.py` → `sync_skills_to_sandbox()`). The model sees them under `/workspace/_sandbox/Skills/...`.

---

## Architecture

```text
  ASLM UI / chat API
        │
        ▼
  Tools/mcp-sandbox/mcp-server.py  (host)
        │
        ▼
  Docker container (mcp-sandbox image)
        │
        └── /workspace/_sandbox  ← bind-mounted to host _sandbox/
```

- **Host**: MCP supervisor runs on the machine running ASLM; bash/write/edit execute inside Docker.
- **Container**: Full Linux userspace (git, build tools, package managers, etc.). Default cwd for `bash` is the workspace root (`/workspace/_sandbox/`).
- **Config**: `sandbox.env` in `Tools/mcp-sandbox/` (created by `setup-sandbox.py` on first run). Loaded before other `SANDBOX_*` variables.

### Key environment variables (`sandbox.env`)

| Variable | Default | Meaning |
|----------|---------|---------|
| `SANDBOX_IMAGE` | `nggtlightkeeper/aslm-chat-sandbox:latest` | Docker image |
| `SANDBOX_DEFAULT_TASK_DIR` | `_sandbox` | Subdirectory under `/workspace` exposed as the model workspace |
| `SANDBOX_HOST_WORKSPACE` | project `Tools/mcp-sandbox` | Host path bound into the container |
| `SANDBOX_DEFAULT_TIMEOUT` | `60` | Default bash timeout (seconds) |
| `SANDBOX_MEMORY_LIMIT` | `3g` | Container memory cap |

See `setup-sandbox.py` and `supervisor/sandbox/config.py` for the full list.

---

## First-time setup

From the repo root (Docker required):

```bash
python Tools/mcp-sandbox/setup-sandbox.py
```

Optional flags: `--source local|registry|auto`, `--force`.

This ensures the image exists and creates `sandbox.env` if missing. The MCP server is registered in ASLM as tool server **`sandbox`**.

---

## Workspace layout (`_sandbox/`)

Typical directories (created on demand):

| Path (relative to `_sandbox/`) | Purpose |
|--------------------------------|---------|
| `User/<scope>/` | Chat uploads and shared user files (`<file_id>__<name>`) |
| `User/<sha256>/` | Content-addressed private uploads |
| `Skills/<skill-name>/` | Mirrored project skills (`SKILL.md`, scripts) |
| `screens/` | Browser Agent screenshots when `linux_sandbox` mode is active |
| *(project files)* | Anything the model creates via `bash` / `write` / `edit` |

**Uploads** (UI) land under `User/` when `tool_server_ids` includes `sandbox` (default). Model-facing paths look like:

```text
/workspace/_sandbox/User/<chat-scope>/<file_id>__notes.txt
```

**Do not** commit secrets or large binaries under `_sandbox/` unless you intend to; the folder is workspace data, not source code (see `.dockerignore`).

---

## MCP tools (`sandbox`)

| Tool id | Purpose |
|---------|---------|
| `bash` | Run shell commands in the container; cwd `.` = `/workspace/_sandbox/` |
| `write` | Create or overwrite UTF-8 text files under the workspace |
| `edit` | Surgical edits (`match` or `lines` mode) |
| `view_image` | Image metadata + optional inline preview for vision models |
| `share_file` | Expose a workspace file to the user as a downloadable card |

### Path rules for the model

- **Workspace files**: relative paths (`report.csv`, `out/plot.png`) or aliases:
  - `_sandbox/...`
  - `/workspace/_sandbox/...`
- **System paths**: absolute paths inside the container (`/etc/os-release`, `/tmp/foo`) work in `bash` but `write`/`edit` are workspace-only.
- **Rejected**: Windows drive paths (`C:\...`).

Large `cat`/`less`/`more` on a single file may return a structured preview instead of raw bytes. Long command output is truncated with a visible marker.

---

## UI integration

### Downloads

Shared files uploaded or created here are downloadable via the UI using paths such as:

```text
/workspace/_sandbox/User/...
```

The backend maps these to the host tree under `Tools/mcp-sandbox/_sandbox/`.

---

## Browser Agent screenshots

When sandbox tools are enabled, screenshots are saved to:

- **Host**: `Tools/mcp-sandbox/_sandbox/screens/`
- **Model path**: `screens/screenshot_<timestamp>.png`

---

## Resource and cleanup behavior

- Workspace cleanup can stage idle sandboxes to tmp and recycle containers (see `SANDBOX_WORKSPACE_CLEANUP_*` in `sandbox.env`).
- Background jobs are supported via `bash` with `background` parameter.
- Output and read limits (`SANDBOX_MAX_OUTPUT_BYTES`, `SANDBOX_MAX_READ_BYTES`, etc.) protect the model context.

---

## Development

| Area | Location |
|------|----------|
| MCP entry | `mcp-server.py` |
| Tool implementation | `supervisor/sandbox/` |
| Docker host bridge | `src/sandbox/docker_host.py` |
| Tests | `tests/` |

Run tests:

```bash
cd Tools/mcp-sandbox
pytest
```

---

## Related documentation

- ASLM UI: `Apps/UI/views.py` (shared file download paths)
- Upload routing: `Apps/UI/upload_storage.py`
