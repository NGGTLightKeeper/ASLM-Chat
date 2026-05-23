# Data Analysis Sandbox (`open_data_analysis` / ODA)

**Python-first analysis sandbox** for ASLM-Chat. Used when **Sandbox default** is `data_analysis` and the **Data Analysis** tool server (`oda`) is enabled.

The persistent shared workspace on the host is:

```text
<Tools/open_data_analysis>/tmp/_sandbox/
```

Inside ephemeral Docker run containers it is mounted as:

```text
/mnt/data/_sandbox/   (read/write, user-visible)
/mnt/data/work/       (read/write, per-run scratch — not for user delivery)
```

---

## Role in ASLM-Chat

| UI setting | Value | Tool server id |
|------------|--------|----------------|
| Sandbox default | `data_analysis` | `oda` |
| Host shared root | `Tools/open_data_analysis/tmp/_sandbox` | — |
| Model path prefix | `/mnt/data/_sandbox/...` | — |

Chat requests pass `sandbox_default_mode: "data_analysis"` in `tool_context`.

**Uploads** routed with `tool_server_ids: ["oda"]` are stored under the ODA `_sandbox` tree with model paths prefixed by `/mnt/data/_sandbox/`.

> **Legacy path**: `Tools/ODA/tmp/_sandbox` is still accepted for downloads while old layouts drain. New work should use `open_data_analysis/tmp/_sandbox` only.

---

## Architecture

```text
  ASLM UI / chat API
        │
        ▼
  Tools/open_data_analysis/mcp-server.py
        │
        ├── (optional) sandboxd daemon — reuses warm containers
        │
        ▼
  Docker container (sandbox:latest or configured image)
        │
        ├── /mnt/data/_sandbox  ← host tmp/_sandbox (shared, persistent)
        └── /mnt/data/work      ← per-run temp (private scratch)
```

Each `oda_python` invocation typically runs `python3 -u -c <code>` with the working directory `/mnt/data/work`. Code should read/write **user-visible** artifacts under `/mnt/data/_sandbox`.

Configuration is driven by environment variables set in `setup_mcp.py` / MCP `mcp.json`:

| Variable | Typical value | Meaning |
|----------|----------------|---------|
| `SANDBOX_SHARED_ROOT` | `<repo>/Tools/open_data_analysis/tmp/_sandbox` | Host bind for shared folder |
| `SANDBOX_IMAGE` | `sandbox:latest` | Container image |
| `SANDBOX_TIMEOUT` | `60` | Command timeout (seconds) |
| `SANDBOX_MAX_CONCURRENT` | `1` | Parallel runs |
| `SANDBOX_USE_DAEMON` | optional | Route via `sandboxd` for lower latency |

---

## First-time setup

### 1. Build or pull the sandbox image

Use the Dockerfile under `Tools/open_data_analysis/sandbox/` or your registry tag. Dev compose (optional):

```bash
cd Tools/open_data_analysis
docker compose --profile dev up -d
```

This mounts `./tmp/_sandbox` → `/mnt/data/_sandbox` for manual inspection.

### 2. Register MCP server

```bash
python Tools/open_data_analysis/setup_mcp.py --target project
```

Adjust `--image`, `--shared-root`, `--use-daemon`, `--daemon-autostart` as needed. ASLM exposes the server as tool id **`oda`**.

---

## Workspace layout (`tmp/_sandbox/`)

| Path (under `_sandbox/`) | Purpose |
|--------------------------|---------|
| `User/<scope>/` | UI uploads when ODA is selected (`/mnt/data/_sandbox/User/...`) |
| `screens/` | Browser Agent screenshots when `data_analysis` mode is active |
| `*.csv`, `*.png`, … | Tables, charts, exports produced by `oda_python` |
| *(synced files)* | Files merged from Linux sandbox on mode switch |

### Allowed shared file types

The file bridge enforces safe names and an extension allowlist (see `sandbox_mcp/files.py`): e.g. `.csv`, `.json`, `.txt`, `.py`, `.md`, `.parquet`, `.xlsx`, `.png`, `.html`, `.zip`, and others. Paths must stay inside `/mnt/data/_sandbox`.

---

## MCP tools (`oda`)

| Tool id | Purpose |
|---------|---------|
| `oda_python` | Run Python in the container; use `/mnt/data/_sandbox` for durable outputs |
| `oda_share_file` | Present a file under `_sandbox` to the user (download card) |
| `oda_view_image` | Image metadata + preview for vision models |

### Python execution contract

- **Shared / user-visible**: `/mnt/data/_sandbox/...` only for files the user should keep or download.
- **Scratch**: `/mnt/data/work` for intermediate steps; not shared with the user by default.
- **Dependencies**: install inside the snippet if missing, e.g. `subprocess.run([sys.executable, "-m", "pip", "install", "pandas"], check=True)`.
- **Delivery**: after creating a deliverable, call `oda_share_file` with a path under `_sandbox`.

The runtime image includes Python, pip, common build tools, Chromium/Chromedriver, ffmpeg, PDF/image/OCR tooling, and network access for pip installs (see tool descriptions in `mcp-server.py`).

---

## UI integration

### Switching from Linux sandbox

When the user selects `data_analysis` as Sandbox default:

1. `POST /api/sandbox/sync/` merge-copies **from** `Tools/mcp-sandbox/_sandbox` **to** `Tools/open_data_analysis/tmp/_sandbox`.
2. Relative paths (`User/...`, task outputs, `screens/`, etc.) are preserved.
3. The next model turn receives a **one-shot system notice** (not shown in chat UI) explaining:
   - files were merged;
   - new paths must use `/mnt/data/_sandbox/...`;
   - older `/workspace/_sandbox/...` references in history refer to the same relative files.

### Switching to Linux sandbox

The reverse sync runs on the next toggle (`data_analysis` → `linux_sandbox`). Same merge rules: no deletes, newer target files kept.

### Model context without a mode switch

Normal messages include:

- System prompt + skills (project skills are **not** auto-synced into ODA `_sandbox`; only the Linux sandbox gets `_sandbox/Skills/`).
- Chat history and uploads with `sandbox_path` when `oda` or `sandbox` is enabled.

---

## Cross-sandbox sync

Implemented in `Apps/UI/views.py` → `_sync_sandbox_roots()`:

| Behavior | Detail |
|----------|--------|
| Direction | One-way per UI click: `source_mode` → `target_mode` |
| Deletes | Never removes files only present in the target |
| Overwrite | Copies only if target missing or **older** than source (`mtime`) |
| Symlinks | Skipped |

Host root mapping:

```python
linux_sandbox  → Tools/mcp-sandbox/_sandbox
data_analysis  → Tools/open_data_analysis/tmp/_sandbox
```

---

## Browser Agent screenshots

When `sandbox_default_mode` is `data_analysis` (or `oda` is in `selected_tool_server_ids` and mode is unset):

- **Host**: `Tools/open_data_analysis/tmp/_sandbox/screens/`
- **Model path**: `/mnt/data/_sandbox/screens/screenshot_<timestamp>.png`

---

## Downloads and path resolution

The UI and API accept container-style paths:

```text
/mnt/data/_sandbox/User/chat/file__report.csv
```

These resolve to `Tools/open_data_analysis/tmp/_sandbox/User/...` on the host. Linux-style `/workspace/_sandbox/...` paths are mapped when resolving shared files after a sync (see `_resolve_shared_file_path` in `Apps/UI/views.py`).

---

## Staging, artifacts, and TTL

Beyond `_sandbox`, the runner may use OS temp directories for per-run layout (`SANDBOX_TMP_ROOT`, staging, artifacts, archives) with TTL cleanup — see `sandbox_mcp/files.py` (`DEFAULT_STAGING_TTL_SECONDS`, etc.). Only `_sandbox` is intended as the durable user workspace.

---

## Development

| Area | Location |
|------|----------|
| MCP wrapper | `mcp-server.py` |
| Runner / Docker | `mcp_server/sandbox_mcp/runner.py` |
| File bridge | `mcp_server/sandbox_mcp/files.py` |
| MCP generator | `setup_mcp.py` |
| Tests | `mcp_server/tests/` |

Example tests (Docker required for integration):

```bash
cd Tools/open_data_analysis/mcp_server
pytest tests/
```

---

## Choosing Linux vs Data Analysis

| Use **linux_sandbox** (`sandbox`) when… | Use **data_analysis** (`oda`) when… |
|----------------------------------------|-------------------------------------|
| You need shell, git, apt, multi-step CLI | You need pandas/plots/nbconvert-style Python |
| Skills under `_sandbox/Skills` matter | You want a focused Python + data stack image |
| Paths are `/workspace/_sandbox/...` | Paths are `/mnt/data/_sandbox/...` |

ASLM can **merge workspace files** between the two on every Sandbox default change so the user can switch modes without losing work.

---

## Related documentation

- [Linux sandbox (`mcp-sandbox`)](../mcp-sandbox/README.md)
- ASLM cross-mode tests: `Apps/UI/test_sandbox_cross_mode.py`
- Upload storage: `Apps/UI/upload_storage.py`
