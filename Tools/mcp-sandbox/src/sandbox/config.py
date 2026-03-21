# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import os
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
DEFAULT_TASK_DIR = os.getenv("SANDBOX_DEFAULT_TASK_DIR", "task")

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_SANDBOX_DIR = os.path.join(os.path.expanduser("~"), ".sandbox-workspace")
HOST_WORKSPACE = os.getenv("SANDBOX_HOST_WORKSPACE", str(_PROJECT_ROOT))


# Import and sharing settings.

LM_STUDIO_USER_FILES = os.getenv(
    "LM_STUDIO_USER_FILES",
    os.path.expanduser("~/.lmstudio/user-files"),
)
IMPORT_ROOTS_ENV = os.getenv("SANDBOX_IMPORT_ROOTS", "")

HTTP_PORT = int(os.getenv("SANDBOX_HTTP_PORT", "8099"))
HTTP_HOST = "127.0.0.1"
TOKEN_TTL_SECONDS = int(os.getenv("SANDBOX_TOKEN_TTL_SECONDS", "1800"))


# Execution limits.

MAX_OUTPUT_CHARS = int(os.getenv("SANDBOX_MAX_OUTPUT_CHARS", "40000"))
DEFAULT_TIMEOUT = int(os.getenv("SANDBOX_DEFAULT_TIMEOUT", "60"))
OCR_TIMEOUT = int(os.getenv("SANDBOX_OCR_TIMEOUT", "60"))

CPU_LIMIT = os.getenv("SANDBOX_CPU_LIMIT", "1")
MEMORY_LIMIT = os.getenv("SANDBOX_MEMORY_LIMIT", "3g")
MEMORY_SWAP_LIMIT = os.getenv("SANDBOX_MEMORY_SWAP_LIMIT", "4g")
PIDS_LIMIT = os.getenv("SANDBOX_PIDS_LIMIT", "256")
STORAGE_LIMIT = os.getenv("SANDBOX_STORAGE_LIMIT", "12G")
DOCKER_START_TIMEOUT_SECONDS = int(
    os.getenv("SANDBOX_DOCKER_START_TIMEOUT_SECONDS", "60")
)


# Docker Desktop discovery.

WINDOWS_DOCKER_DESKTOP_PATHS = [
    os.path.expandvars(r"%ProgramFiles%\Docker\Docker\Docker Desktop.exe"),
    os.path.expandvars(r"%LocalAppData%\Docker\Docker Desktop.exe"),
]


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


if not _validate_workspace_path(HOST_WORKSPACE):
    print(
        f"CRITICAL SECURITY ERROR: HOST_WORKSPACE '{HOST_WORKSPACE}' is not safe!",
        file=sys.stderr,
    )
    print("Using fallback isolated directory instead.", file=sys.stderr)
    HOST_WORKSPACE = _DEFAULT_SANDBOX_DIR

HOST_WORKSPACE = os.path.abspath(HOST_WORKSPACE)


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
