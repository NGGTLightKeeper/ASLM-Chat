"""Integration tests for container_pool against real Docker + sandbox:latest."""
from __future__ import annotations

import subprocess
import time

import pytest

from sandbox_mcp import container_pool
from sandbox_mcp.container_pool import (
    _container_name,
    _sanitize_scope,
    _POOL,
    _POOL_LOCK,
    acquire,
    evict,
    exec_in_pool,
)

from .conftest import docker_available, image_available

pytestmark = pytest.mark.integration

requires_docker = pytest.mark.skipif(
    not docker_available(),
    reason="Docker not available",
)
requires_image = pytest.mark.skipif(
    not image_available(),
    reason="sandbox:latest image not built",
)


def _container_id(name: str) -> str:
    """Return the real Docker container ID for *name*."""
    r = subprocess.run(
        ["docker", "inspect", "-f", "{{.Id}}", name],
        capture_output=True, text=True, timeout=10,
    )
    return r.stdout.strip()


@pytest.fixture(autouse=True)
def isolated_pool(tmp_path, monkeypatch):
    monkeypatch.setenv("SANDBOX_IMAGE", "sandbox:latest")
    monkeypatch.setenv("SANDBOX_TIMEOUT", "60")
    monkeypatch.setenv("SANDBOX_TMP_ROOT", str(tmp_path / "oda-sandbox"))
    monkeypatch.setenv("SANDBOX_POOL_ROOT", str(tmp_path / "pool"))
    monkeypatch.setenv("SANDBOX_SHARED_ROOT", str(tmp_path / "_sandbox"))
    (tmp_path / "_sandbox").mkdir(parents=True, exist_ok=True)
    with _POOL_LOCK:
        _POOL.clear()
    yield
    # Clean up containers created during the test.
    with _POOL_LOCK:
        names = [e.container_name for e in _POOL.values()]
        _POOL.clear()
    for name in names:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=15)


@requires_docker
@requires_image
def test_acquire_creates_and_reuses_container():
    """Two acquire() calls on the same scope reuse one container."""
    name = acquire("integ-reuse")
    id1 = _container_id(name)
    assert id1, "container should exist"

    name2 = acquire("integ-reuse")
    id2 = _container_id(name2)

    assert name == name2
    assert id1 == id2, "same Docker container should be reused"


@requires_docker
@requires_image
def test_scopes_isolated():
    """Different scopes get different containers."""
    name_a = acquire("integ-iso-a")
    name_b = acquire("integ-iso-b")

    assert name_a != name_b
    id_a = _container_id(name_a)
    id_b = _container_id(name_b)
    assert id_a != id_b


@requires_docker
@requires_image
def test_exec_basic():
    """exec_in_pool runs a command and returns output."""
    exit_code, stdout, stderr, timed_out = exec_in_pool(
        "integ-exec",
        ["python3", "-c", "print('hello-pool')"],
        timeout_s=30,
    )
    assert exit_code == 0
    assert timed_out is False
    assert "hello-pool" in stdout


@requires_docker
@requires_image
def test_exec_timeout_preserves_container():
    """Timeout kills the command but the container must still be running."""
    name = acquire("integ-timeout")
    id_before = _container_id(name)

    exit_code, stdout, stderr, timed_out = exec_in_pool(
        "integ-timeout",
        ["python3", "-c", "import time; time.sleep(999)"],
        timeout_s=3,
    )
    # Supervisor kills the command (exit 124); timed_out is only True on outer docker hang.
    assert exit_code == 124 or timed_out is True
    assert "timeout" in (stderr or "").lower() or timed_out is True

    # Container should still exist and be running.
    id_after = _container_id(name)
    assert id_before == id_after, "container should survive a command timeout"

    r = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", name],
        capture_output=True, text=True, timeout=10,
    )
    assert r.stdout.strip() == "true", "container must still be running"


@requires_docker
@requires_image
def test_pip_cache_persists_across_calls():
    """Install a package in call 1; call 2 imports it without pip install."""
    scope = "integ-pip-cache"

    # Call 1: install pandas (or any small package)
    install_code = (
        "import subprocess, sys\n"
        "r = subprocess.run(\n"
        "    [sys.executable, '-m', 'pip', 'install', '-q', 'tabulate'],\n"
        "    capture_output=True, text=True, timeout=120\n"
        ")\n"
        "print('pip rc:', r.returncode)\n"
        "if r.returncode != 0:\n"
        "    print(r.stderr[-300:])\n"
    )
    exit_code, stdout, _, timed_out = exec_in_pool(
        scope, ["python3", "-u", "-c", install_code], timeout_s=180
    )
    assert not timed_out, "pip install timed out"
    assert exit_code == 0, f"pip install failed: {stdout}"

    # Call 2: just import — should be fast (from .local/lib/...)
    import_code = "import tabulate; print('version:', tabulate.__version__)"
    t0 = time.time()
    exit_code2, stdout2, stderr2, timed_out2 = exec_in_pool(
        scope, ["python3", "-u", "-c", import_code], timeout_s=30
    )
    elapsed = time.time() - t0
    assert not timed_out2
    assert exit_code2 == 0, f"import failed: {stdout2} {stderr2}"
    assert "version:" in stdout2
    # Import from cache should be fast (< 10s). The install would take 30+s.
    assert elapsed < 10, f"import took {elapsed:.1f}s — cache likely not working"


@requires_docker
@requires_image
def test_persistent_container_same_scope_across_two_runs():
    """Two separate exec_in_pool calls share one container ID."""
    scope = "integ-persist"

    e1, o1, _, _ = exec_in_pool(scope, ["bash", "-lc", "echo run1"], timeout_s=15)
    assert e1 == 0

    # Container should still be there
    with _POOL_LOCK:
        entry = _POOL.get(_sanitize_scope(scope))
    assert entry is not None
    id1 = _container_id(entry.container_name)

    e2, o2, _, _ = exec_in_pool(scope, ["bash", "-lc", "echo run2"], timeout_s=15)
    assert e2 == 0

    with _POOL_LOCK:
        entry2 = _POOL.get(_sanitize_scope(scope))
    id2 = _container_id(entry2.container_name)

    assert id1 == id2, "both runs should use the same container"
    assert "run1" in o1
    assert "run2" in o2


@requires_docker
@requires_image
def test_tmp_survives_between_calls():
    """Files written to /tmp in call 1 are present in call 2 (same container)."""
    scope = "integ-tmp-persist"

    e1, _, _, _ = exec_in_pool(
        scope,
        ["python3", "-c", "open('/tmp/persist.txt','w').write('marker')"],
        timeout_s=15,
    )
    assert e1 == 0

    e2, out2, _, _ = exec_in_pool(
        scope,
        ["python3", "-c", "print(open('/tmp/persist.txt').read())"],
        timeout_s=15,
    )
    assert e2 == 0
    assert "marker" in out2
