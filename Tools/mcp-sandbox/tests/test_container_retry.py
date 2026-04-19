"""Tests for container.py idempotent retry logic (_ensure_container_running).

All tests here work entirely with mocked Docker CLI — no real container needed.
"""

from __future__ import annotations

import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import os
import shutil
os.environ.setdefault("SANDBOX_HOST_WORKSPACE", str(ROOT / ".test_workspace"))

import sandbox.container as container_mod  # noqa: E402
import sandbox.docker_host as docker_host_mod  # noqa: E402


# Helper: build a fake subprocess result
def _ok(stdout: str = "", stderr: str = "") -> MagicMock:
    m = MagicMock()
    m.returncode = 0
    m.stdout = stdout
    m.stderr = stderr
    return m


def _fail(stderr: str = "error", returncode: int = 1) -> MagicMock:
    m = MagicMock()
    m.returncode = returncode
    m.stdout = ""
    m.stderr = stderr
    return m


# ── _inspect_container ────────────────────────────────────────────────

class TestInspectContainer(unittest.TestCase):
    """_inspect_container must parse docker inspect output correctly."""

    def test_returns_none_when_container_missing(self) -> None:
        with patch.object(docker_host_mod, "_run_command", return_value=_fail("No such container", 1)):
            result = container_mod._inspect_container()
        self.assertIsNone(result)

    def test_returns_running_true_when_up(self) -> None:
        import json
        from sandbox.config import CONTAINER_NAME, HOST_WORKSPACE, DEFAULT_TASK_DIR
        import os as os_mod
        mount = os_mod.path.normpath(os_mod.path.join(HOST_WORKSPACE, DEFAULT_TASK_DIR))
        payload = json.dumps([{"State": {"Running": True, "Status": "running"}, "Mounts": [{"Source": mount}]}])
        with patch.object(docker_host_mod, "_run_command", return_value=_ok(payload)):
            result = container_mod._inspect_container()
        self.assertIsNotNone(result)
        self.assertTrue(result["running"])
        self.assertTrue(result["exists"])
        self.assertTrue(result["volume_ok"])

    def test_detects_volume_mismatch(self) -> None:
        import json
        payload = json.dumps([{"State": {"Running": True, "Status": "running"}, "Mounts": [{"Source": "/wrong/path"}]}])
        with patch.object(docker_host_mod, "_run_command", return_value=_ok(payload)):
            result = container_mod._inspect_container()
        self.assertIsNotNone(result)
        self.assertFalse(result["volume_ok"], "Volume mismatch should be detected")

    def test_returns_none_on_invalid_json(self) -> None:
        with patch.object(docker_host_mod, "_run_command", return_value=_ok("not json at all")):
            result = container_mod._inspect_container()
        self.assertIsNone(result)


# ── _force_remove ─────────────────────────────────────────────────────

class TestForceRemove(unittest.TestCase):
    def test_success(self) -> None:
        with patch.object(docker_host_mod, "_run_command", return_value=_ok()):
            ok, msg = container_mod._force_remove()
        self.assertTrue(ok)

    def test_already_gone_is_ok(self) -> None:
        with patch.object(docker_host_mod, "_run_command", return_value=_fail("No such container")):
            ok, msg = container_mod._force_remove()
        self.assertTrue(ok, "Already-gone container should be treated as success")

    def test_real_error_returns_false(self) -> None:
        with patch.object(docker_host_mod, "_run_command", return_value=_fail("daemon not running")):
            ok, msg = container_mod._force_remove()
        self.assertFalse(ok)


# ── _start_existing ───────────────────────────────────────────────────

class TestStartExisting(unittest.TestCase):
    def test_returns_true_when_container_running_after_start(self) -> None:
        import json, os as os_mod
        from sandbox.config import HOST_WORKSPACE, DEFAULT_TASK_DIR
        mount = os_mod.path.normpath(os_mod.path.join(HOST_WORKSPACE, DEFAULT_TASK_DIR))
        running_payload = json.dumps([{"State": {"Running": True, "Status": "running"}, "Mounts": [{"Source": mount}]}])

        # docker start → OK; docker inspect → running
        with patch.object(docker_host_mod, "_run_command",
                          side_effect=[_ok(), _ok(running_payload)]):
            ok, msg = container_mod._start_existing()
        self.assertTrue(ok)

    def test_returns_false_when_start_fails(self) -> None:
        with patch.object(docker_host_mod, "_run_command", return_value=_fail("permission denied")):
            ok, msg = container_mod._start_existing()
        self.assertFalse(ok)

    def test_returns_false_when_not_running_after_start(self) -> None:
        """docker start returns 0 but container dies immediately."""
        import json
        # start OK, then inspect shows not running
        dead_payload = json.dumps({"running": False, "status": "exited", "mounts": ""})
        with patch.object(docker_host_mod, "_run_command",
                          side_effect=[_ok(), _ok(dead_payload)]):
            ok, msg = container_mod._start_existing()
        self.assertFalse(ok)


# ── _build_run_command ────────────────────────────────────────────────

class TestBuildRunCommand(unittest.TestCase):
    def test_mounts_task_root_under_workspace_sandbox(self) -> None:
        from sandbox.config import DEFAULT_TASK_DIR, MODEL_WORKSPACE_CONTAINER

        cmd = container_mod._build_run_command("image:test", include_storage_limit=False)

        task_host_path = os.path.join(container_mod.HOST_WORKSPACE, DEFAULT_TASK_DIR)
        self.assertIn(f"{task_host_path}:{MODEL_WORKSPACE_CONTAINER}", cmd)
        self.assertIn("-w", cmd)
        self.assertEqual(cmd[cmd.index("-w") + 1], MODEL_WORKSPACE_CONTAINER)
        self.assertNotIn("--security-opt", cmd)

    def test_no_supervisor_source_mount_by_default(self) -> None:
        """Without SANDBOX_DEV_BIND=1 the src tree must NOT be bind-mounted."""
        with patch.object(docker_host_mod, "DEV_BIND", False):
            cmd = container_mod._build_run_command("image:test", include_storage_limit=False)
        # The path appears as an -e env var, but must NOT appear as a -v bind mount.
        bind_entry = f":{container_mod.SUPERVISOR_SRC}:ro"
        self.assertNotIn(bind_entry, cmd)

    def test_mounts_supervisor_source_read_only_when_dev_bind_enabled(self) -> None:
        """With SANDBOX_DEV_BIND=1 the src tree is bind-mounted read-only."""
        src_dir = ROOT / "src"
        with patch.object(docker_host_mod, "DEV_BIND", True), \
             patch.object(docker_host_mod, "SUPERVISOR_SRC_HOST", str(src_dir)):
            cmd = container_mod._build_run_command("image:test", include_storage_limit=False)
        self.assertIn(f"{src_dir}:{container_mod.SUPERVISOR_SRC}:ro", cmd)

    def test_adds_read_only_linux_venv_mount_when_dev_bind_enabled(self) -> None:
        temp_dir = ROOT / ".test_workspace" / "__venv_mount_test"
        shutil.rmtree(temp_dir, ignore_errors=True)
        try:
            venv = temp_dir / "venv"
            (venv / "bin").mkdir(parents=True)
            (venv / "bin" / "python").write_text("#!/usr/bin/env python\n", encoding="utf-8")
            (venv / "pyvenv.cfg").write_text("home = /usr/local/bin\n", encoding="utf-8")

            with patch.object(docker_host_mod, "DEV_BIND", True), \
                 patch.object(docker_host_mod, "SUPERVISOR_VENV_HOST", str(venv)):
                cmd = container_mod._build_run_command("image:test", include_storage_limit=False)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        self.assertIn(f"{venv}:{container_mod.SUPERVISOR_VENV}:ro", cmd)

    def test_no_venv_mount_without_dev_bind(self) -> None:
        """Without SANDBOX_DEV_BIND=1 the venv must NOT be bind-mounted."""
        temp_dir = ROOT / ".test_workspace" / "__venv_mount_test2"
        shutil.rmtree(temp_dir, ignore_errors=True)
        try:
            venv = temp_dir / "venv"
            (venv / "bin").mkdir(parents=True)
            (venv / "bin" / "python").write_text("#!/usr/bin/env python\n", encoding="utf-8")
            (venv / "pyvenv.cfg").write_text("home = /usr/local/bin\n", encoding="utf-8")

            with patch.object(docker_host_mod, "DEV_BIND", False), \
                 patch.object(docker_host_mod, "SUPERVISOR_VENV_HOST", str(venv)):
                cmd = container_mod._build_run_command("image:test", include_storage_limit=False)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        self.assertNotIn(f"{venv}:{container_mod.SUPERVISOR_VENV}:ro", cmd)

    def test_rejects_windows_venv_mount(self) -> None:
        temp_dir = ROOT / ".test_workspace" / "__venv_windows_test"
        shutil.rmtree(temp_dir, ignore_errors=True)
        try:
            venv = temp_dir / "venv"
            (venv / "Scripts").mkdir(parents=True)
            (venv / "Scripts" / "python.exe").write_text("", encoding="utf-8")
            (venv / "pyvenv.cfg").write_text("home = C:\\Python\n", encoding="utf-8")

            with patch.object(docker_host_mod, "SUPERVISOR_VENV_HOST", str(venv)):
                with self.assertRaises(ValueError):
                    container_mod._build_run_command("image:test", include_storage_limit=False)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


# ── _ensure_image ─────────────────────────────────────────────────────

class TestEnsureImage(unittest.TestCase):
    def test_existing_image_with_runtime_label_is_reused(self) -> None:
        import json

        payload = json.dumps([
            {
                "Config": {
                    "Labels": {
                        container_mod.REQUIRED_IMAGE_LABEL: container_mod.REQUIRED_IMAGE_LABEL_VALUE,
                    }
                }
            }
        ])

        with patch.object(docker_host_mod, "_run_command", return_value=_ok(payload)) as run_mock:
            ok, message = container_mod._ensure_image()

        self.assertTrue(ok)
        self.assertIn("already exists", message)
        run_mock.assert_called_once()

    def test_existing_stale_image_without_runtime_label_is_rebuilt(self) -> None:
        import json

        stale_payload = json.dumps([{"Config": {"Labels": {}}}])

        def fake_run(args, timeout=30, **kwargs):
            if args[:3] == ["docker", "image", "inspect"]:
                return _ok(stale_payload)
            if args[:2] == ["docker", "build"]:
                return _ok()
            return _fail(f"unexpected command: {args}")

        with patch.object(docker_host_mod, "_run_command", side_effect=fake_run) as run_mock:
            ok, message = container_mod._ensure_image()

        self.assertTrue(ok)
        self.assertIn("built locally", message)
        self.assertTrue(
            any(call_args.args[0][:2] == ["docker", "build"] for call_args in run_mock.call_args_list),
            "stale image should trigger docker build",
        )


# ── _ensure_container_running (integration) ───────────────────────────

class TestEnsureContainerRunning(unittest.TestCase):
    """High-level idempotent ensure with mocked Docker."""

    def _mock_docker_ok(self) -> MagicMock:
        """Simulate _ensure_docker_running returning True."""
        m = MagicMock(return_value=(True, "Docker daemon is running."))
        return m

    def test_returns_true_when_already_running_correct_volume(self) -> None:
        import json, os as os_mod
        from sandbox.config import HOST_WORKSPACE, DEFAULT_TASK_DIR
        mount = os_mod.path.normpath(os_mod.path.join(HOST_WORKSPACE, DEFAULT_TASK_DIR))
        payload = json.dumps([{"State": {"Running": True, "Status": "running"}, "Mounts": [{"Source": mount}]}])

        with patch.object(docker_host_mod, "_ensure_docker_running",
                          return_value=(True, "OK")), \
             patch.object(docker_host_mod, "_run_command", return_value=_ok(payload)):
            ok, msg = container_mod._ensure_container_running()

        self.assertTrue(ok)
        self.assertIn("running", msg.lower())

    def test_recreates_container_on_volume_mismatch(self) -> None:
        """If volume is wrong, old container is removed and a new one created."""
        import json
        # First inspect: running but wrong volume
        bad_payload = json.dumps({"running": True, "status": "running", "mounts": "/wrong"})
        # After rm, no container; after docker run, OK
        no_container_fail = _fail("No such container", 1)

        call_count = {"n": 0}
        payloads = [_ok(bad_payload), _ok(), _fail("No such container", 1), _ok()]

        def fake_run(args, timeout=10, **kw):
            idx = call_count["n"]
            call_count["n"] += 1
            if idx < len(payloads):
                return payloads[idx]
            return _ok()

        with patch.object(docker_host_mod, "_ensure_docker_running", return_value=(True, "OK")), \
             patch.object(docker_host_mod, "_ensure_image", return_value=(True, "OK")), \
             patch.object(docker_host_mod, "_wait_for_container_running", return_value=(True, "running")), \
             patch.object(docker_host_mod, "_run_command", side_effect=fake_run):
            ok, msg = container_mod._ensure_container_running()

        self.assertTrue(ok)

    def test_retries_on_name_conflict(self) -> None:
        """Name-conflict error during create triggers a retry."""
        import json, os as os_mod
        from sandbox.config import HOST_WORKSPACE, DEFAULT_TASK_DIR
        mount = os_mod.path.normpath(os_mod.path.join(HOST_WORKSPACE, DEFAULT_TASK_DIR))
        running_payload = json.dumps({"running": True, "status": "running", "mounts": mount})

        call_count = {"n": 0}

        def fake_run(args, timeout=10, **kw):
            n = call_count["n"]
            call_count["n"] += 1
            if "inspect" in args and n == 0:
                return _fail("No such object", 1)          # first inspect: no container
            if "run" in args and n == 1:
                return _fail("name already in use", 125)   # create conflict
            if "inspect" in args and n == 2:
                return _ok(running_payload)                # second inspect: now running
            return _ok()

        with patch.object(docker_host_mod, "_ensure_docker_running", return_value=(True, "OK")), \
             patch.object(docker_host_mod, "_ensure_image", return_value=(True, "OK")), \
             patch.object(docker_host_mod, "_wait_for_container_running", return_value=(True, "running")), \
             patch.object(docker_host_mod, "_run_command", side_effect=fake_run):
            ok, msg = container_mod._ensure_container_running(retry_delay=0)

        self.assertTrue(ok, f"Expected success after retry, got: {msg}")

    def test_concurrent_calls_serialized(self) -> None:
        """Concurrent _ensure_container_running calls must not race each other."""
        results: list[tuple[bool, str]] = []
        errors: list[Exception] = []
        active_inspects = 0
        max_active_inspects = 0
        active_lock = threading.Lock()

        def fake_inspect():
            nonlocal active_inspects, max_active_inspects
            with active_lock:
                active_inspects += 1
                max_active_inspects = max(max_active_inspects, active_inspects)
            try:
                # Give other threads a chance to enter if the production lock is broken.
                import time
                time.sleep(0.01)
                return {
                    "exists": True,
                    "running": True,
                    "status": "running",
                    "volume_ok": True,
                }
            finally:
                with active_lock:
                    active_inspects -= 1

        def worker():
            try:
                r = container_mod._ensure_container_running()
                results.append(r)
            except Exception as e:
                errors.append(e)

        with patch.object(docker_host_mod, "_ensure_docker_running", return_value=(True, "OK")), \
             patch.object(docker_host_mod, "_inspect_container", side_effect=fake_inspect):
            threads = [threading.Thread(target=worker) for _ in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=5)

        self.assertFalse(errors, f"Concurrent calls raised exceptions: {errors}")
        self.assertEqual(len(results), 4)
        self.assertTrue(all(ok for ok, _ in results), f"Some calls failed: {results}")
        self.assertEqual(max_active_inspects, 1, "_ensure_container_running did not serialize inspect calls")


if __name__ == "__main__":
    unittest.main(verbosity=2)
