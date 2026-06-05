---
title: "test_host_proxy"
draft: false
---

## Module `test_host_proxy`

`Tools/mcp-sandbox/tests/test_host_proxy.py` — ASLM Chat Python module.

---

## Overview

Part of `Tools\mcp-sandbox\tests`. See **Related** for package index and callers.

---

## Classes

### `class FakeProcess`

**Purpose:** Type `FakeProcess` defined in `test_host_proxy.py`.

### `class BlockingInput`

**Purpose:** Type `BlockingInput` defined in `test_host_proxy.py`.

### `class Read1Stream`

**Purpose:** Type `Read1Stream` defined in `test_host_proxy.py`.

### `class HostProxyTests`

**Purpose:** Type `HostProxyTests` defined in `test_host_proxy.py`.

---

## Test methods

#### `def FakeProcess.__init__(*, stdout=…, stderr=…, returncode=…, on_wait=…) -> None`

**Purpose:** Implements `FakeProcess.__init__` in `test_host_proxy.py`.

#### `def FakeProcess.wait() -> int`

**Purpose:** Implements `FakeProcess.wait` in `test_host_proxy.py`.

#### `def FakeProcess.poll() -> int`

**Purpose:** Implements `FakeProcess.poll` in `test_host_proxy.py`.

#### `def BlockingInput.__init__() -> None`

**Purpose:** Implements `BlockingInput.__init__` in `test_host_proxy.py`.

#### `def BlockingInput.read(_size) -> bytes`

**Purpose:** Implements `BlockingInput.read` in `test_host_proxy.py`.

#### `def BlockingInput.close() -> None`

**Purpose:** Implements `BlockingInput.close` in `test_host_proxy.py`.

#### `def Read1Stream.__init__(chunks) -> None`

**Purpose:** Implements `Read1Stream.__init__` in `test_host_proxy.py`.

#### `def Read1Stream.read(_size) -> bytes`

**Purpose:** Implements `Read1Stream.read` in `test_host_proxy.py`.

#### `def Read1Stream.read1(_size) -> bytes`

**Purpose:** Implements `Read1Stream.read1` in `test_host_proxy.py`.

**Steps:**

1. Return the computed result to the caller.

#### `def HostProxyTests.test_ensure_docker_running_does_not_launch_desktop_by_default() -> None`

**Purpose:** Implements `HostProxyTests.test_ensure_docker_running_does_not_launch_desktop_by_default` in `test_host_proxy.py`.

**Steps:**

1. Spawn or communicate with a child process.

#### `def HostProxyTests.test_forward_binary_stream_uses_read1_for_pipe_responsiveness() -> None`

**Purpose:** Implements `HostProxyTests.test_forward_binary_stream_uses_read1_for_pipe_responsiveness` in `test_host_proxy.py`.

#### `def HostProxyTests.test_stdin_queue_uses_read1_for_pipe_responsiveness() -> None`

**Purpose:** Implements `HostProxyTests.test_stdin_queue_uses_read1_for_pipe_responsiveness` in `test_host_proxy.py`.

#### `def HostProxyTests.test_supervisor_exec_uses_plain_stdin_stdout_stderr_pipes() -> None`

**Purpose:** Implements `HostProxyTests.test_supervisor_exec_uses_plain_stdin_stdout_stderr_pipes` in `test_host_proxy.py`.

**Steps:**

1. Spawn or communicate with a child process.

#### `def HostProxyTests.test_pipe_keeps_supervisor_stderr_out_of_mcp_stdout() -> None`

**Purpose:** Implements `HostProxyTests.test_pipe_keeps_supervisor_stderr_out_of_mcp_stdout` in `test_host_proxy.py`.

#### `def HostProxyTests.test_supervisor_healthcheck_uses_runtime_pong() -> None`

**Purpose:** Implements `HostProxyTests.test_supervisor_healthcheck_uses_runtime_pong` in `test_host_proxy.py`.

#### `def HostProxyTests.test_supervisor_ready_recreates_after_healthcheck_failures() -> None`

**Purpose:** Implements `HostProxyTests.test_supervisor_ready_recreates_after_healthcheck_failures` in `test_host_proxy.py`.

#### `def HostProxyTests.test_pipe_reconnects_when_model_kills_supervisor_process() -> None`

**Purpose:** Implements `HostProxyTests.test_pipe_reconnects_when_model_kills_supervisor_process` in `test_host_proxy.py`.

#### `def HostProxyTests.test_corrupted_supervisor_runtime_recreates_then_fails_closed() -> None`

**Purpose:** Implements `HostProxyTests.test_corrupted_supervisor_runtime_recreates_then_fails_closed` in `test_host_proxy.py`.

#### `def HostProxyTests.test_proxy_does_not_start_mcp_pipe_when_runtime_healthcheck_is_bad() -> None`

**Purpose:** Implements `HostProxyTests.test_proxy_does_not_start_mcp_pipe_when_runtime_healthcheck_is_bad` in `test_host_proxy.py`.

#### `def HostProxyTests.test_missing_supervisor_venv_rebuilds_image_then_recovers() -> None`

**Purpose:** Implements `HostProxyTests.test_missing_supervisor_venv_rebuilds_image_then_recovers` in `test_host_proxy.py`.

---

## Related

- [tests/_index](../../../_index/)
