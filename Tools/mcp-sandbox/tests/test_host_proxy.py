# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

from __future__ import annotations

import io
import os
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

os.environ.setdefault("SANDBOX_HOST_WORKSPACE", str(ROOT / ".test_workspace"))

import sandbox.docker_host as docker_host_mod  # noqa: E402

container_mod = docker_host_mod


class FakeProcess:
    def __init__(
        self,
        *,
        stdout: bytes = b"",
        stderr: bytes = b"",
        returncode: int = 0,
        on_wait=None,
    ) -> None:
        self.stdin = io.BytesIO()
        self.stdout = io.BytesIO(stdout)
        self.stderr = io.BytesIO(stderr)
        self.returncode = returncode
        self.pid = 1234
        self.on_wait = on_wait

    def wait(self) -> int:
        if self.on_wait is not None:
            self.on_wait()
        return self.returncode

    def poll(self) -> int:
        return self.returncode


class BlockingInput:
    def __init__(self) -> None:
        self.closed = threading.Event()
        self.read_count = 0

    def read(self, _size: int) -> bytes:
        self.read_count += 1
        self.closed.wait(timeout=5)
        return b""

    def close(self) -> None:
        self.closed.set()


class Read1Stream:
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = list(chunks)
        self.read_calls = 0
        self.read1_calls = 0

    def read(self, _size: int) -> bytes:
        self.read_calls += 1
        raise AssertionError("proxy stream forwarding must not use blocking read(size)")

    def read1(self, _size: int) -> bytes:
        self.read1_calls += 1
        if not self.chunks:
            return b""
        return self.chunks.pop(0)


class HostProxyTests(unittest.TestCase):
    def test_ensure_docker_running_does_not_launch_desktop_by_default(self) -> None:
        info_result = MagicMock(returncode=1)

        with patch.object(docker_host_mod, "_docker_cli_available", return_value=True), \
             patch.object(docker_host_mod, "_docker_info", return_value=info_result), \
             patch.object(docker_host_mod.os, "name", "nt"), \
             patch.dict(docker_host_mod.os.environ, {"SANDBOX_AUTO_START_DOCKER": ""}, clear=False), \
             patch.object(docker_host_mod.subprocess, "Popen") as popen_mock:
            ok, message = docker_host_mod._ensure_docker_running()

        self.assertFalse(ok)
        self.assertIn("Start Docker Desktop manually", message)
        popen_mock.assert_not_called()

    def test_forward_binary_stream_uses_read1_for_pipe_responsiveness(self) -> None:
        source = Read1Stream([b'{"jsonrpc":"2.0"}\n'])
        sink = io.BytesIO()

        container_mod._forward_binary_stream(source, sink)

        self.assertEqual(sink.getvalue(), b'{"jsonrpc":"2.0"}\n')
        self.assertEqual(source.read_calls, 0)
        self.assertGreaterEqual(source.read1_calls, 1)

    def test_stdin_queue_uses_read1_for_pipe_responsiveness(self) -> None:
        source = Read1Stream([b'{"jsonrpc":"2.0","method":"initialize"}\n'])
        input_queue = container_mod.Queue()
        eof = threading.Event()

        container_mod._read_stdin_to_queue(source, input_queue, eof)

        self.assertEqual(input_queue.get_nowait(), b'{"jsonrpc":"2.0","method":"initialize"}\n')
        self.assertIsNone(input_queue.get_nowait())
        self.assertTrue(eof.is_set())
        self.assertEqual(source.read_calls, 0)
        self.assertGreaterEqual(source.read1_calls, 1)

    def test_supervisor_exec_uses_plain_stdin_stdout_stderr_pipes(self) -> None:
        fake = FakeProcess()

        with patch.object(container_mod.subprocess, "Popen", return_value=fake) as popen_mock:
            result = container_mod.start_container_supervisor()

        self.assertIs(result, fake)
        args = popen_mock.call_args.args[0]
        kwargs = popen_mock.call_args.kwargs
        self.assertIn("-i", args)
        self.assertNotIn("-t", args)
        self.assertEqual(kwargs["stdin"], container_mod.subprocess.PIPE)
        self.assertEqual(kwargs["stdout"], container_mod.subprocess.PIPE)
        self.assertEqual(kwargs["stderr"], container_mod.subprocess.PIPE)

    def test_pipe_keeps_supervisor_stderr_out_of_mcp_stdout(self) -> None:
        fake = FakeProcess(stdout=b'{"jsonrpc":"2.0"}\n', stderr=b"supervisor log\n")
        output = io.BytesIO()
        error = io.BytesIO()

        with patch.object(docker_host_mod, "_ensure_container_running", return_value=(True, "OK")), \
             patch.object(docker_host_mod, "ensure_supervisor_ready", return_value=(True, "pong")), \
             patch.object(docker_host_mod, "start_container_supervisor", return_value=fake):
            code = container_mod.pipe_to_container_supervisor(
                max_restarts=0,
                input_stream=io.BytesIO(b""),
                output_stream=output,
                error_stream=error,
            )

        self.assertEqual(code, 0)
        self.assertEqual(output.getvalue(), b'{"jsonrpc":"2.0"}\n')
        self.assertEqual(error.getvalue(), b"supervisor log\n")

    def test_supervisor_healthcheck_uses_runtime_pong(self) -> None:
        result = MagicMock()
        result.returncode = 0
        result.stdout = "sandbox-supervisor-pong-v2\n"
        result.stderr = ""

        with patch.object(docker_host_mod, "_run_command", return_value=result) as run_mock:
            ok, message = container_mod.healthcheck_container_supervisor(timeout_s=2)

        self.assertTrue(ok)
        self.assertEqual(message, "sandbox-supervisor-pong-v2")
        args = run_mock.call_args.args[0]
        self.assertNotIn("-t", args)
        self.assertNotIn("-i", args)
        self.assertIn("--healthcheck", args)

    def test_supervisor_ready_recreates_after_healthcheck_failures(self) -> None:
        health_results = [
            (False, "broken pipe"),
            (False, "timeout"),
            (True, "sandbox-supervisor-pong"),
        ]

        with patch.object(docker_host_mod, "healthcheck_container_supervisor", side_effect=health_results), \
             patch.object(docker_host_mod, "_force_remove", return_value=(True, "removed")) as remove_mock, \
             patch.object(docker_host_mod, "_create_container", return_value=(True, "created")) as create_mock:
            ok, message = container_mod.ensure_supervisor_ready(attempts=2, timeout_s=1)

        self.assertTrue(ok)
        self.assertIn("recovered", message)
        remove_mock.assert_called_once()
        create_mock.assert_called_once()

    def test_pipe_reconnects_when_model_kills_supervisor_process(self) -> None:
        input_stream = BlockingInput()
        output = io.BytesIO()
        error = io.BytesIO()

        killed = FakeProcess(
            stdout=b"",
            stderr=b"Killed\n",
            returncode=137,
        )
        restarted = FakeProcess(
            stdout=b'{"jsonrpc":"2.0","result":"after-reconnect"}\n',
            stderr=b"",
            returncode=0,
            on_wait=lambda: (input_stream.close(), time.sleep(0.05)),
        )

        with patch.object(docker_host_mod, "_ensure_container_running", return_value=(True, "OK")) as ensure_mock, \
             patch.object(docker_host_mod, "ensure_supervisor_ready", return_value=(True, "pong")) as health_mock, \
             patch.object(docker_host_mod, "start_container_supervisor", side_effect=[killed, restarted]) as start_mock:
            code = container_mod.pipe_to_container_supervisor(
                max_restarts=1,
                input_stream=input_stream,
                output_stream=output,
                error_stream=error,
            )

        self.assertEqual(code, 0)
        self.assertEqual(start_mock.call_count, 2)
        self.assertEqual(ensure_mock.call_count, 2)
        self.assertEqual(health_mock.call_count, 2)
        self.assertIn(b"after-reconnect", output.getvalue())
        self.assertIn(b"supervisor exited with 137; restarting", error.getvalue())

    def test_corrupted_supervisor_runtime_recreates_then_fails_closed(self) -> None:
        health_results = [
            (False, "SyntaxError: invalid syntax in sandbox/supervisor.py"),
            (False, "SyntaxError: invalid syntax in sandbox/supervisor.py"),
            (False, "SyntaxError: invalid syntax in sandbox/supervisor.py"),
            (False, "SyntaxError: invalid syntax in sandbox/supervisor.py"),
        ]

        with patch.object(docker_host_mod, "healthcheck_container_supervisor", side_effect=health_results), \
             patch.object(docker_host_mod, "_force_remove", return_value=(True, "removed")) as remove_mock, \
             patch.object(docker_host_mod, "_create_container", return_value=(True, "created")) as create_mock:
            ok, message = container_mod.ensure_supervisor_ready(attempts=2, timeout_s=1)

        self.assertFalse(ok)
        self.assertIn("healthcheck failed after recreate", message)
        self.assertIn("SyntaxError", message)
        remove_mock.assert_called_once()
        create_mock.assert_called_once()

    def test_proxy_does_not_start_mcp_pipe_when_runtime_healthcheck_is_bad(self) -> None:
        input_stream = BlockingInput()
        output = io.BytesIO()
        error = io.BytesIO()

        with patch.object(docker_host_mod, "_ensure_container_running", return_value=(True, "OK")), \
             patch.object(docker_host_mod, "ensure_supervisor_ready", return_value=(False, "ImportError: no module named fastmcp")), \
             patch.object(docker_host_mod, "start_container_supervisor") as start_mock:
            code = container_mod.pipe_to_container_supervisor(
                max_restarts=0,
                input_stream=input_stream,
                output_stream=output,
                error_stream=error,
            )

        self.assertEqual(code, 1)
        self.assertEqual(output.getvalue(), b"")
        self.assertIn(b"ImportError", error.getvalue())
        start_mock.assert_not_called()
        self.assertEqual(input_stream.read_count, 0, "stdin reader must not start before healthcheck passes")

    def test_missing_supervisor_venv_rebuilds_image_then_recovers(self) -> None:
        missing_python = (
            'OCI runtime exec failed: exec failed: unable to start container process: '
            'exec: "/opt/sandbox-venv/bin/python": stat /opt/sandbox-venv/bin/python: '
            "no such file or directory: unknown"
        )
        health_results = [
            (False, "broken pipe"),
            (False, "timeout"),
            (False, missing_python),
            (False, missing_python),
            (True, "sandbox-supervisor-pong"),
        ]

        with patch.object(docker_host_mod, "healthcheck_container_supervisor", side_effect=health_results), \
             patch.object(docker_host_mod, "_force_remove", return_value=(True, "removed")) as remove_mock, \
             patch.object(docker_host_mod, "_create_container", return_value=(True, "created")) as create_mock, \
             patch.object(docker_host_mod, "_ensure_image", return_value=(True, "rebuilt")) as image_mock:
            ok, message = container_mod.ensure_supervisor_ready(attempts=2, timeout_s=1)

        self.assertTrue(ok)
        self.assertIn("image rebuild", message)
        self.assertEqual(remove_mock.call_count, 2)
        self.assertEqual(create_mock.call_count, 2)
        image_mock.assert_called_once_with(force_rebuild=True)

if __name__ == "__main__":
    unittest.main()
