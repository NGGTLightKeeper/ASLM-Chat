# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import os
import re as _re
import subprocess
import sys
from pathlib import Path


# Core sandbox paths.

CONTAINER_NAME = os.getenv("SANDBOX_CONTAINER_NAME", "mcp-sandbox")
SANDBOX_IMAGE = os.getenv("SANDBOX_IMAGE", "dima1312313/mcp-sandbox:latest")
SANDBOX_IMAGE_SOURCE = os.getenv("SANDBOX_IMAGE_SOURCE", "local").strip().lower()
SNAPSHOT_IMAGE_PREFIX = os.getenv(
    "SANDBOX_SNAPSHOT_PREFIX",
    f"{CONTAINER_NAME}-snapshot",
)
CONTAINER_WORKSPACE = "/workspace"
DEFAULT_TASK_DIR = os.getenv("SANDBOX_DEFAULT_TASK_DIR", "_sandbox")
MODEL_WORKSPACE_CONTAINER = (
    f"{CONTAINER_WORKSPACE.rstrip('/')}/{DEFAULT_TASK_DIR}"
    if DEFAULT_TASK_DIR not in ("", ".")
    else CONTAINER_WORKSPACE
)
IN_CONTAINER = os.getenv("SANDBOX_IN_CONTAINER", "").strip().lower() in {
    "1",
    "true",
    "yes",
}
COMMAND_USER = os.getenv("SANDBOX_COMMAND_USER", "sandbox_user")
SUPERVISOR_SRC = os.getenv("SANDBOX_SUPERVISOR_SRC", "/opt/sandbox-src")
SUPERVISOR_VENV = os.getenv("SANDBOX_SUPERVISOR_VENV", "/opt/sandbox-venv")
SUPERVISOR_VENV_HOST = os.getenv("SANDBOX_SUPERVISOR_VENV_HOST", "").strip()

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_SANDBOX_DIR = os.path.join(os.path.expanduser("~"), ".sandbox-workspace")
HOST_WORKSPACE = os.getenv(
    "SANDBOX_HOST_WORKSPACE",
    CONTAINER_WORKSPACE if IN_CONTAINER else str(_PROJECT_ROOT),
)
# In production the supervisor source is baked into the image (COPY src /opt/sandbox-src).
# Bind-mounting the host source tree on top is a dev-only convenience; it must be
# explicitly opted-in via SANDBOX_DEV_BIND=1 so production containers run baked code.
DEV_BIND = os.getenv("SANDBOX_DEV_BIND", "").strip().lower() in {"1", "true", "yes"}
SUPERVISOR_SRC_HOST = os.getenv(
    "SANDBOX_SUPERVISOR_SRC_HOST",
    str(_PROJECT_ROOT / "src") if DEV_BIND else "",
).strip()


# Import and sharing settings.

LM_STUDIO_USER_FILES = os.getenv(
    "LM_STUDIO_USER_FILES",
    os.path.expanduser("~/.lmstudio/user-files"),
)
IMPORT_ROOTS_ENV = os.getenv("SANDBOX_IMPORT_ROOTS", "")

# Execution limits.

MAX_OUTPUT_CHARS = int(os.getenv("SANDBOX_MAX_OUTPUT_CHARS", "40000"))
DEFAULT_TIMEOUT = int(os.getenv("SANDBOX_DEFAULT_TIMEOUT", "60"))
OCR_TIMEOUT = int(os.getenv("SANDBOX_OCR_TIMEOUT", "60"))
MAX_READ_BYTES = int(os.getenv("SANDBOX_MAX_READ_BYTES", "200000"))
MAX_CAT_FILE_BYTES = int(os.getenv("SANDBOX_MAX_CAT_FILE_BYTES", "30720"))
MAX_CAT_LINE_THRESHOLD = int(os.getenv("SANDBOX_MAX_CAT_LINE_THRESHOLD", "300"))
MAX_IMAGE_PREVIEW_BYTES = int(os.getenv("SANDBOX_MAX_IMAGE_PREVIEW_BYTES", "2000000"))
MAX_LS_ENTRIES = int(os.getenv("SANDBOX_MAX_LS_ENTRIES", "500"))
MAX_FIND_RESULTS = int(os.getenv("SANDBOX_MAX_FIND_RESULTS", "200"))
MAX_GREP_RESULTS = int(os.getenv("SANDBOX_MAX_GREP_RESULTS", "200"))

# Presentation layer tuning.

FILE_MAP_MIN_LINES = int(os.getenv("SANDBOX_FILE_MAP_MIN_LINES", "200"))
GREP_CLUSTER_THRESHOLD = int(os.getenv("SANDBOX_GREP_CLUSTER_THRESHOLD", "30"))
MAX_FILE_MAP_SYMBOLS = int(os.getenv("SANDBOX_MAX_FILE_MAP_SYMBOLS", "50"))
LOOP_BREAK_THRESHOLD = int(os.getenv("SANDBOX_LOOP_BREAK_THRESHOLD", "3"))
CPU_LIMIT = os.getenv("SANDBOX_CPU_LIMIT", "4")
THREAD_LIMIT = int(os.getenv("SANDBOX_THREAD_LIMIT", "4"))
MEMORY_LIMIT = os.getenv("SANDBOX_MEMORY_LIMIT", "3g")
MEMORY_SWAP_LIMIT = os.getenv("SANDBOX_MEMORY_SWAP_LIMIT", "4g")
PIDS_LIMIT = os.getenv("SANDBOX_PIDS_LIMIT", "256")
STORAGE_LIMIT = os.getenv("SANDBOX_STORAGE_LIMIT", "12G")
NETWORK_LIMIT_MBIT = int(os.getenv("SANDBOX_NETWORK_LIMIT_MBIT", "100"))
DOCKER_START_TIMEOUT_SECONDS = int(
    os.getenv("SANDBOX_DOCKER_START_TIMEOUT_SECONDS", "60")
)
BACKGROUND_TIMEOUT_THRESHOLD = int(
    os.getenv("SANDBOX_BACKGROUND_TIMEOUT_THRESHOLD", "10")
)


# Docker Desktop discovery.

WINDOWS_DOCKER_DESKTOP_PATHS = [
    os.path.expandvars(r"%ProgramFiles%\Docker\Docker\Docker Desktop.exe"),
    os.path.expandvars(r"%LocalAppData%\Docker\Docker Desktop.exe"),
]


IGNORED_DIR_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".vscode",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    "dist",
    "build",
    "target",
    ".next",
    ".nuxt",
}


# Workspace validation.

def _validate_workspace_path(path: str) -> bool:
    """Return True when the host workspace path looks safe."""

    normalized = os.path.normpath(os.path.abspath(path)).lower()
    dangerous_patterns = [
        "windows",
        "system32",
        "program files",
        "program files (x86)",
        "programdata",
        "/bin",
        "/sbin",
        "/usr",
        "/etc",
        "/var",
        "/root",
    ]

    if len(normalized) <= 3 and normalized.endswith((":\\", ":/")):
        return False

    if normalized in {"/", "\\"}:
        return False

    for pattern in dangerous_patterns:
        if pattern in normalized:
            return False

    path_parts = normalized.replace("\\", "/").strip("/").split("/")
    return len(path_parts) >= 2


if not IN_CONTAINER and not _validate_workspace_path(HOST_WORKSPACE):
    print(
        f"CRITICAL SECURITY ERROR: HOST_WORKSPACE '{HOST_WORKSPACE}' is not safe!",
        file=sys.stderr,
    )
    print("Using fallback isolated directory instead.", file=sys.stderr)
    HOST_WORKSPACE = _DEFAULT_SANDBOX_DIR

HOST_WORKSPACE = os.path.abspath(HOST_WORKSPACE)
CONFIG_FILE_PATH = os.getenv(
    "SANDBOX_CONFIG_FILE",
    os.path.join(str(Path(__file__).resolve().parents[2]), "sandbox.env"),
)


# Import root normalization.

def get_allowed_import_roots() -> list[str]:
    """Return normalized host roots allowed for imports."""

    raw_roots: list[str] = []

    if IMPORT_ROOTS_ENV.strip():
        raw_roots.extend(
            item for item in IMPORT_ROOTS_ENV.split(os.pathsep) if item.strip()
        )

    if LM_STUDIO_USER_FILES:
        raw_roots.append(LM_STUDIO_USER_FILES)

    normalized_roots: list[str] = []
    seen: set[str] = set()

    for raw_root in raw_roots:
        normalized = os.path.normpath(os.path.abspath(os.path.expanduser(raw_root)))
        if normalized in seen:
            continue

        seen.add(normalized)
        normalized_roots.append(normalized)

    return normalized_roots


ALLOWED_IMPORT_ROOTS = get_allowed_import_roots()

os.makedirs(HOST_WORKSPACE, exist_ok=True)
os.makedirs(os.path.join(HOST_WORKSPACE, DEFAULT_TASK_DIR), exist_ok=True)


# File-type → glob mapping (used by grep/rg routing and code-extension detection).

_RG_TYPE_FALLBACK: dict[str, str] = {
    "py": "*.py", "python": "*.py",
    "js": "*.js", "javascript": "*.js",
    "ts": "*.ts", "typescript": "*.ts",
    "tsx": "*.tsx", "jsx": "*.jsx",
    "rs": "*.rs", "rust": "*.rs",
    "go": "*.go",
    "java": "*.java",
    "c": "*.c",
    "cpp": "*.cpp", "cc": "*.cc", "cxx": "*.cxx",
    "h": "*.h", "hpp": "*.hpp",
    "cs": "*.cs", "csharp": "*.cs",
    "rb": "*.rb", "ruby": "*.rb",
    "php": "*.php",
    "html": "*.html", "css": "*.css",
    "json": "*.json",
    "yaml": "*.yaml", "yml": "*.yml",
    "toml": "*.toml", "xml": "*.xml",
    "md": "*.md", "markdown": "*.md",
    "sh": "*.sh", "bash": "*.sh",
    "sql": "*.sql",
    "lua": "*.lua",
    "r": "*.r",
    "swift": "*.swift",
    "kt": "*.kt", "kotlin": "*.kt",
    "scala": "*.scala",
    "tex": "*.tex",
    "txt": "*.txt",
}


def _load_rg_type_map() -> dict[str, str]:
    """Return type→glob map built from `rg --type-list`; falls back to built-in table."""
    try:
        proc = subprocess.run(
            ["rg", "--type-list"],
            capture_output=True, text=True, timeout=5,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return dict(_RG_TYPE_FALLBACK)

        result: dict[str, str] = {}
        for line in proc.stdout.splitlines():
            m = _re.match(r'^([\w-]+):\s*(.+)$', line)
            if not m:
                continue
            type_name = m.group(1).lower()
            globs = [g.strip() for g in m.group(2).split(",")]
            primary = next((g for g in globs if _re.match(r'^\*\.\w+$', g)), None)
            if primary is None:
                continue
            result[type_name] = primary
            # Short-ext alias: "python" → also register "py"
            ext = primary[2:]  # "*.py" → "py"
            if ext not in result:
                result[ext] = primary

        return result if result else dict(_RG_TYPE_FALLBACK)
    except Exception:
        return dict(_RG_TYPE_FALLBACK)


RG_TYPE_TO_GLOB: dict[str, str] = _load_rg_type_map()
