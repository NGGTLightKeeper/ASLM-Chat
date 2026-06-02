---
title: "setup-sandbox"
draft: false
---

## Module `setup-sandbox`

`Tools/mcp-sandbox/setup-sandbox.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools\mcp-sandbox`. See **Related** for package index and callers.

---

## Public functions

#### `def main() -> int`

**Purpose:** Entry point: pull or build the sandbox image according to --source.

**Steps:**

1. Return the computed result to the caller.

---

## Private functions

#### `def _ensure_env_file(path) -> None`

**Purpose:** Create sandbox.env with commented defaults when missing.

**Steps:**

1. Handle errors and map them to a safe response.

#### `def _load_env_file(path) -> dict[str, str]`

**Purpose:** Parse key=value lines from a sandbox.env file.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Iterate and transform or accumulate state.

#### `def _cfg(key, default) -> str`

**Purpose:** Resolve a config key from env, sandbox.env, or default.

#### `def _run(args, timeout) -> subprocess.CompletedProcess`

**Purpose:** Run a subprocess and capture stdout/stderr as text.

**Steps:**

1. Return the computed result to the caller.
2. Spawn or communicate with a child process.

#### `def _stream(args, timeout) -> int`

**Purpose:** Run a command with real-time stdout/stderr visible to the user.

#### `def _ok(msg) -> None`

**Purpose:** Print a success line.

#### `def _info(msg) -> None`

**Purpose:** Print a progress line.

#### `def _fail(msg) -> None`

**Purpose:** Print an error line to stderr.

#### `def _check_docker() -> bool`

**Purpose:** Verify the Docker CLI is installed and responsive.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _check_daemon() -> bool`

**Purpose:** Verify the Docker daemon is reachable.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.

#### `def _image_exists_and_valid() -> bool`

**Purpose:** Return True when the local image has the required runtime label.

**Steps:**

1. Return the computed result to the caller.
2. Handle errors and map them to a safe response.
3. Parse or serialize JSON payloads.

#### `def _pull() -> bool`

**Purpose:** Pull the sandbox image from the registry.

**Steps:**

1. Return the computed result to the caller.

#### `def _build() -> bool`

**Purpose:** Build the sandbox image from the local Dockerfile.

**Steps:**

1. Return the computed result to the caller.
2. Iterate and transform or accumulate state.

---

## Related

- [mcp-sandbox/_index](../../_index/)
