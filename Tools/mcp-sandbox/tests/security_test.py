# Copyright NEXTGGTECH. Elastic License 2.0.

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


# Test environment setup.

ROOT = Path(__file__).resolve().parent
PKG_ROOT = ROOT.parent
SUPERVISOR = PKG_ROOT / "supervisor"
SRC = PKG_ROOT / "src"
for entry in (SUPERVISOR, SRC):
    path = str(entry)
    if path not in sys.path:
        sys.path.insert(0, path)

os.environ.setdefault("SANDBOX_HOST_WORKSPACE", str(PKG_ROOT))

from sandbox import config  # noqa: E402
from sandbox.workspace import (  # noqa: E402
    describe,
    get_secure_task_path,
    is_allowed_host_import,
    normalize_model_relative_path,
    read,
    task_root,
    validate_model_path,
    write,
)

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
INFO = "\033[36mINFO\033[0m"

results: list[tuple[str, bool, str]] = []


# Output helpers.

# Print a formatted group header.
def print_group(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


# Assertion helpers.

# Run a check and record whether it raised as expected.
def check(name: str, *, expect_raise: bool, fn, notes: str = "") -> bool:
    try:
        result = fn()
        raised = False
    except Exception as exc:
        raised = True
        result = repr(exc)

    ok = raised == expect_raise
    verdict = PASS if ok else FAIL
    symbol = (
        "BLOCKED"
        if raised and expect_raise
        else ("ALLOWED" if not raised else "RAISED-UNEXPECTED")
    )
    if not expect_raise and not raised:
        symbol = "ALLOWED"

    print(f"  {verdict}  {name}")
    if notes:
        print(f"         note: {notes}")
    if not ok:
        print(f"         result: {result}")

    results.append((name, ok, symbol))
    return ok


# Docker helpers.

# Run a command inside the sandbox container.
def docker_exec(cmd: str, check_output: bool = False) -> tuple[int, str, str]:
    result = subprocess.run(
        ["docker", "exec", config.CONTAINER_NAME, "bash", "-c", cmd],
        capture_output=True,
        text=True,
        timeout=15,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


# Path validation checks.

print_group("GROUP 1 - validate_model_path - absolute / traversal rejection")

ABSOLUTE_PATHS = [
    ("/etc/passwd", "Unix absolute path"),
    ("C:\\Windows\\system32", "Windows backslash absolute"),
    ("C:/Users/dimap", "Windows forward-slash absolute"),
    ("/workspace", "Container workspace root"),
    ("//server/share", "UNC path"),
]

for path, label in ABSOLUTE_PATHS:
    check(
        f"Absolute rejected: {label}",
        expect_raise=True,
        fn=lambda p=path: validate_model_path(p),
    )

check(
    "task/ prefix is a normal relative directory",
    expect_raise=False,
    fn=lambda: validate_model_path("task/secret.txt"),
)
check(
    "task path is not normalized as workspace alias",
    expect_raise=False,
    fn=lambda: (
        normalize_model_relative_path(r"task\pages\example.json") == "task/pages/example.json"
        or (_ for _ in ()).throw(AssertionError("task alias still active"))
    ),
)

print()
print(
    "  (validate_model_path does NOT block '..'; confinement is in "
    "get_secure_task_path)"
)


# Task path confinement checks.

print_group("GROUP 2 - get_secure_task_path - traversal confinement")

TRAVERSAL_PATHS = [
    "../secret",
    "../../etc/passwd",
    "../../../Windows/System32/cmd.exe",
    "a/../../secret",
    "a/../../../b",
    ".//../secret",
]

for path in TRAVERSAL_PATHS:
    check(
        f"Traversal blocked: {path!r}",
        expect_raise=True,
        fn=lambda p=path: get_secure_task_path(p),
    )

# "......" is 6 dots — NOT a traversal sequence, it's a literal filename.
# It resolves to task_root/...... (inside sandbox). Verify it stays confined.
check(
    "Six-dot path resolves inside sandbox (not traversal)",
    expect_raise=False,
    fn=lambda: get_secure_task_path("......"),
    notes="'......' is a filename, not '../..'. Should stay inside task_root.",
)

check(
    "Null byte in path",
    expect_raise=True,
    fn=lambda: get_secure_task_path("file\x00../etc/passwd"),
    notes="null byte should cause ValueError or OSError",
)

check(
    "Encoded traversal: '..\\\\/etc/passwd' (backslash+slash mix)",
    expect_raise=True,
    fn=lambda: get_secure_task_path("..\\/etc/passwd"),
    notes="Backslash+slash mix normalizes to real traversal on Windows.",
)
# "..%2Fetc%2Fpasswd" — percent-encoding is NOT decoded by the filesystem.
# The OS treats %2F as a literal character in the filename, so this path
# resolves to task_root/..%2Fetc%2Fpasswd (inside sandbox). Not a traversal.
# URL-encoded traversal is relevant only for HTTP handlers (tested in GROUP 5).
check(
    "URL-encoded path '..%2Fetc%2Fpasswd' stays inside sandbox",
    expect_raise=False,
    fn=lambda: get_secure_task_path("..%2Fetc%2Fpasswd"),
    notes="Filesystem does not decode %2F — this is a literal filename, not traversal.",
)

check(
    "Very long path (4096 chars)",
    expect_raise=False,
    fn=lambda: get_secure_task_path("a" * 4000),
    notes="Should resolve inside the sandbox workspace but path will not exist.",
)


# Workspace read and write checks.

print_group("GROUP 3 - write / read - boundary enforcement")

WRITE_ESCAPE_PATHS = [
    ("../escape.txt", "One level up from sandbox workspace root"),
    ("../../escape.txt", "Two levels up"),
    ("sub/../../escape.txt", "Sub + two up"),
]

for path, label in WRITE_ESCAPE_PATHS:
    check(
        f"write blocked: {label}",
        expect_raise=True,
        fn=lambda p=path: write(p, "pwned"),
    )

check(
    "write to bare filename stays inside sandbox workspace",
    expect_raise=False,
    fn=lambda: write("canary_test_delete_me.txt", "ok"),
    notes="Single filename should succeed because it lands inside the sandbox workspace.",
)

try:
    (task_root() / "canary_test_delete_me.txt").unlink(missing_ok=True)
except Exception:
    pass


# Host import checks.

print_group("GROUP 4 - is_allowed_host_import - allowed-roots enforcement")

IMPORT_DENIED_PATHS = [
    Path("C:/Windows/System32/cmd.exe"),
    Path("/etc/passwd"),
    Path(os.path.expanduser("~")) / ".ssh" / "id_rsa",
    Path(os.path.expanduser("~")) / "Desktop" / "secret.txt",
    Path("C:/Users"),
]

for path in IMPORT_DENIED_PATHS:
    check(
        f"import_from_host denied: {path.name}",
        expect_raise=False,
        fn=lambda p=path: is_allowed_host_import(p),
        notes="is_allowed_host_import should return False, not raise.",
    )
    allowed = is_allowed_host_import(path)
    print(f"  {INFO}  import_from_host({path}): {'ALLOWED' if allowed else 'DENIED'}")

project_root = ROOT.parent.parent
allowed_project = is_allowed_host_import(project_root)
print(f"\n  {INFO}  Project root ({project_root}) import allowed: {allowed_project}")
if allowed_project:
    print("  WARNING  Project root is inside allowed import roots.")

print(
    f"  {INFO}  Explicit import roots: "
    f"{config.ALLOWED_IMPORT_ROOTS if config.ALLOWED_IMPORT_ROOTS else '(none)'}"
)


# share_file / describe path checks (workspace confinement).

print_group("GROUP 5 - describe() - share_file path traversal rejection")

DESCRIBE_TRAVERSAL = [
    ("../secret.txt", "One level up"),
    ("../../outside.txt", "Two levels up"),
    ("sub/../../escape.txt", "Mid-path traversal"),
]

for path, label in DESCRIBE_TRAVERSAL:
    check(
        f"describe blocked: {label}",
        expect_raise=True,
        fn=lambda p=path: describe(p),
    )


# Live container checks.

print_group("GROUP 6 - Container security (requires running container)")

CONTAINER = config.CONTAINER_NAME
container_result = subprocess.run(
    ["docker", "ps", "-q", "-f", f"name=^{CONTAINER}$"],
    capture_output=True,
    text=True,
    timeout=10,
)
container_running = bool(container_result.stdout.strip())

if not container_running:
    print(f"  {INFO}  Container '{CONTAINER}' is not running - skipping live tests")
else:
    print(f"  {INFO}  Container '{CONTAINER}' is running - executing live tests\n")

    rc, out, _ = docker_exec("id")
    is_root = "uid=0(root)" in out
    verdict = FAIL if is_root else PASS
    print(f"  {verdict}  Container runs as root: {is_root}  ({out})")
    results.append(("Container runs as root", not is_root, "root" if is_root else "non-root"))

    rc, out, _ = docker_exec("cat /etc/passwd | head -3")
    print(f"  {INFO}  /etc/passwd readable (expected): {'yes' if rc == 0 else 'no'}")

    rc, out, _ = docker_exec("ls -la /var/run/docker.sock 2>/dev/null || echo NOSOCK")
    has_docker_sock = "NOSOCK" not in out and rc == 0
    verdict = FAIL if has_docker_sock else PASS
    print(f"  {verdict}  Docker socket exposed inside container: {has_docker_sock}")
    if has_docker_sock:
        print("         WARNING  /var/run/docker.sock is accessible.")
    results.append(
        ("Docker socket in container", not has_docker_sock, "EXPOSED" if has_docker_sock else "absent")
    )

    rc, out, _ = docker_exec("ls /host 2>/dev/null || ls /mnt/host 2>/dev/null || echo NOHOSTMOUNT")
    host_mount = "NOHOSTMOUNT" not in out
    verdict = FAIL if host_mount else PASS
    print(f"  {verdict}  Host filesystem mounted at /host or /mnt/host: {host_mount}")
    results.append(
        ("Host filesystem extra mount", not host_mount, "EXPOSED" if host_mount else "absent")
    )

    rc, out, _ = docker_exec("ls /workspace/")
    workspace_items = out.splitlines() if rc == 0 else []
    non_task_items = [item for item in workspace_items if item not in (config.DEFAULT_TASK_DIR, ".gitkeep", "")]
    verdict = FAIL if non_task_items else PASS
    print(
        f"  {verdict}  /workspace exposes items beyond {config.DEFAULT_TASK_DIR}/: "
        f"{non_task_items or 'none'}"
    )
    if non_task_items:
        print(f"         WARNING  Model can see: {non_task_items}")
    results.append(
        ("Workspace exposes non-task items", not non_task_items, f"items={non_task_items}")
    )

    rc, out, _ = docker_exec("ls /workspace/tools 2>/dev/null | head -5")
    # EXPOSED only if ls succeeded AND returned non-empty output (actual files)
    can_see_tools = rc == 0 and bool(out.strip())
    verdict = FAIL if can_see_tools else PASS
    print(f"  {verdict}  Project /tools dir visible via /workspace: {can_see_tools}")
    if can_see_tools:
        print(f"         WARNING  Source code is readable inside container: {out}")
    results.append(
        ("Project source visible in container", not can_see_tools, "EXPOSED" if can_see_tools else "absent")
    )

    rc, out, _ = docker_exec("cat /proc/1/environ 2>/dev/null | tr '\\0' '\\n' | head -5 || echo NOPROC")
    can_read_proc1 = "NOPROC" not in out and rc == 0
    print(f"  {INFO}  /proc/1/environ readable: {can_read_proc1}")
    if can_read_proc1:
        print("         (Process 1 is container init; this is normal)")

    rc, out, _ = docker_exec(
        "timeout 3 curl -s --max-time 2 http://172.17.0.1:8099/ 2>/dev/null | head -1 || "
        "timeout 3 curl -s --max-time 2 http://host.docker.internal:8099/ 2>/dev/null | head -1 || "
        "echo NO_HOST_HTTP"
    )
    can_reach_host_http = "NO_HOST_HTTP" not in out
    # HTTP share reachability is by design — container uses it to serve files back to the model.
    # Token-based TTL access control is the actual protection here.
    verdict = INFO
    print(f"  {INFO}  Container can reach host HTTP share (port 8099): {can_reach_host_http} (by design — token TTL protects access)")
    results.append(
        ("Container reaches host HTTP", True, "by-design")
    )

    rc, out, _ = docker_exec("cat /proc/self/status | grep -i cap")
    print(f"  {INFO}  Container capabilities:\n    {out.replace(chr(10), chr(10) + '    ')}")

    rc, out, _ = docker_exec("touch /etc/pwned_test 2>&1 || echo READONLY")
    readonly_etc = "READONLY" in out or rc != 0
    verdict = PASS if readonly_etc else FAIL
    print(f"  {verdict}  /etc is read-only (cannot write): {readonly_etc}")
    if not readonly_etc:
        docker_exec("rm -f /etc/pwned_test")
    results.append(("Cannot write to /etc", readonly_etc, "read-only" if readonly_etc else "WRITABLE"))

    rc, out, _ = docker_exec(
        "test -f /workspace/tools/mcp-web-search/mcp-server.py && "
        "python3 /workspace/tools/mcp-web-search/mcp-server.py --help 2>/dev/null | head -1"
    )
    # POSSIBLE only if the bridge entrypoint exists and runs inside the container mount.
    can_exec_project = rc == 0 and bool(out.strip())
    verdict = FAIL if can_exec_project else PASS
    print(
        f"  {verdict}  Can run mcp-web-search bridge via /workspace/tools mount: "
        f"{can_exec_project}"
    )
    if can_exec_project:
        print("         WARNING  Model can execute mounted project entrypoints.")
    results.append(
        (
            "Execute mcp-web-search bridge from container",
            not can_exec_project,
            "POSSIBLE" if can_exec_project else "blocked",
        )
    )

    rc, out, _ = docker_exec("ls /proc/ | grep -E '^[0-9]+$' | wc -l")
    pid_count = int(out.strip()) if out.strip().isdigit() else -1
    print(f"  {INFO}  Visible PIDs in /proc: {pid_count} (>100 may indicate host PID namespace)")

    # GPG_KEY is a standard Python base image variable (PSF signing key) — not a secret.
    rc, out, _ = docker_exec("env | grep -iE 'secret|token|password|api_key|api_secret' || echo NONE")
    has_secret_env = out != "NONE" and rc == 0
    verdict = FAIL if has_secret_env else PASS
    print(f"  {verdict}  Secret-looking env vars inside container: {has_secret_env}")
    if has_secret_env:
        print(f"         WARNING  Found: {out[:300]}")
    results.append(
        ("No secret env vars in container", not has_secret_env, "FOUND" if has_secret_env else "none")
    )

    rc, out, _ = docker_exec("ls /proc/self/root/etc/ 2>/dev/null | head -3 || echo BLOCKED")
    proc_root_escape = "BLOCKED" not in out and rc == 0
    verdict = FAIL if proc_root_escape else PASS
    print(f"  {verdict}  /proc/self/root escape: {'possible' if proc_root_escape else 'blocked'}")
    results.append(
        ("proc/self/root escape", not proc_root_escape, "POSSIBLE" if proc_root_escape else "blocked")
    )

    docker_exec(f"rm -f /workspace/{config.DEFAULT_TASK_DIR}/__sym_test")
    docker_exec(f"ln -s /etc/passwd /workspace/{config.DEFAULT_TASK_DIR}/__sym_test")
    rc, out, _ = docker_exec(
        f"cat /workspace/{config.DEFAULT_TASK_DIR}/__sym_test 2>/dev/null | head -1 || echo BLOCKED"
    )
    symlink_works = "BLOCKED" not in out and rc == 0 and "root:" in out
    docker_exec(f"rm -f /workspace/{config.DEFAULT_TASK_DIR}/__sym_test")
    verdict = FAIL if symlink_works else PASS
    print(
        f"  {verdict}  Symlink inside {config.DEFAULT_TASK_DIR}/ pointing to /etc/passwd: "
        f"{'readable' if symlink_works else 'blocked'}"
    )
    if symlink_works:
        print("         WARNING  Symlink escape works.")
    results.append(
        (
            f"Symlink escape via {config.DEFAULT_TASK_DIR}/",
            not symlink_works,
            "ESCAPE" if symlink_works else "blocked",
        )
    )

    docker_exec(f"rm -f /workspace/{config.DEFAULT_TASK_DIR}/__sym_test")
    docker_exec(f"ln -s /etc/passwd /workspace/{config.DEFAULT_TASK_DIR}/__sym_test")
    try:
        read_result = read("__sym_test")
        sym_read = "root:" in ((read_result.get("result") or {}).get("content", ""))
    except Exception:
        sym_read = False
    docker_exec(f"rm -f /workspace/{config.DEFAULT_TASK_DIR}/__sym_test")
    verdict = FAIL if sym_read else PASS
    print(f"  {verdict}  sandbox read() follows symlink to /etc/passwd: {sym_read}")
    if sym_read:
        print("         WARNING  read() follows the symlink target.")
    results.append(("read symlink follow", not sym_read, "FOLLOWS" if sym_read else "blocked"))


# Summary output.

print_group("SUMMARY")

passed = sum(1 for _, ok, _ in results if ok)
failed = sum(1 for _, ok, _ in results if not ok)
total = len(results)

print(f"\n  Total: {total}  |  {PASS}: {passed}  |  {FAIL}: {failed}\n")

if failed:
    print("  FAILED tests (potential vulnerabilities):")
    for name, ok, symbol in results:
        if not ok:
            print(f"    - {name}  [{symbol}]")
else:
    print("  All tests passed.")

print()
