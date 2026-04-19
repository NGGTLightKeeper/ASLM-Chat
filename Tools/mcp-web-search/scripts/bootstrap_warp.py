from __future__ import annotations

import argparse
import asyncio
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (str(ROOT), str(SRC)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

import warp_manager


def _run_command(command: list[str]) -> tuple[bool, str]:
    try:
        completed = subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        return True, completed.stdout.strip()
    except Exception as exc:
        return False, str(exc)


def _windows_install_client() -> tuple[bool, str]:
    winget = shutil.which("winget")
    if not winget:
        return False, "winget is not available"
    return _run_command([
        winget,
        "install",
        "--id",
        "Cloudflare.Warp",
        "-e",
        "--accept-source-agreements",
        "--accept-package-agreements",
    ])


def _macos_install_client() -> tuple[bool, str]:
    brew = shutil.which("brew")
    if not brew:
        return False, "brew is not available"
    return _run_command([brew, "install", "--cask", "cloudflare-warp"])


def _linux_install_client() -> tuple[bool, str]:
    apt = shutil.which("apt-get")
    dnf = shutil.which("dnf")
    pacman = shutil.which("pacman")
    if apt:
        return _run_command(["sudo", "apt-get", "install", "-y", "cloudflare-warp"])
    if dnf:
        return _run_command(["sudo", "dnf", "install", "-y", "cloudflare-warp"])
    if pacman:
        return _run_command(["sudo", "pacman", "-S", "--noconfirm", "cloudflare-warp"])
    return False, "unsupported Linux package manager"


def install_system_client() -> tuple[bool, str]:
    system_name = platform.system().lower()
    if system_name == "windows":
        return _windows_install_client()
    if system_name == "darwin":
        return _macos_install_client()
    return _linux_install_client()


def write_policy_file(path: Path, *, proxy_port: int, organization: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        warp_manager.render_warp_mdm_xml(proxy_port=proxy_port, organization=organization),
        encoding="utf-8",
    )
    return path


async def activate_proxy_mode(proxy_port: int) -> tuple[bool, str]:
    setup = await warp_manager.ensure_warp_proxy_mode(proxy_port=proxy_port)
    if not setup.get("ok"):
        return False, str(setup.get("reason", "proxy mode configuration failed"))
    ok = await warp_manager.warp_connect()
    if not ok:
        doctor = await warp_manager.warp_doctor()
        return False, "; ".join(doctor.get("recommendations", [])) or "WARP connect failed"
    proxy_url = await warp_manager.resolve_warp_proxy_url()
    if not await warp_manager.is_warp_proxy_reachable(proxy_url):
        return False, f"local proxy is not reachable at {proxy_url}"
    return True, proxy_url


async def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap Cloudflare WARP local proxy mode for mcp-web-search.")
    parser.add_argument("--install-system-client", action="store_true", help="Best-effort install of the official WARP client.")
    parser.add_argument("--skip-python-deps", action="store_true", help="Do not auto-install Python deps like curl_cffi.")
    parser.add_argument("--write-policy", action="store_true", help="Write a local WARP policy file enabling proxy mode.")
    parser.add_argument("--skip-activate", action="store_true", help="Do not switch the client to proxy mode and connect it.")
    parser.add_argument("--policy-path", default="", help="Override the mdm.xml destination path.")
    parser.add_argument("--proxy-port", type=int, default=40000, help="Local WARP proxy port.")
    parser.add_argument("--organization", default=os.getenv("WARP_ORGANIZATION", ""), help="Optional Cloudflare organization/team name.")
    args = parser.parse_args()

    if not args.skip_python_deps:
        warp_manager._load_curl_cffi_requests()

    if args.install_system_client:
        ok, output = install_system_client()
        print("system_client_install:", "ok" if ok else "failed")
        if output:
            print(output)

    if args.write_policy:
        target = Path(args.policy_path) if args.policy_path else warp_manager.default_warp_mdm_path()
        try:
            written = write_policy_file(target, proxy_port=args.proxy_port, organization=args.organization)
            print(f"policy_written: {written}")
        except PermissionError:
            fallback = ROOT / "tests" / "artifacts" / "warp_mdm.xml"
            written = write_policy_file(fallback, proxy_port=args.proxy_port, organization=args.organization)
            print(f"policy_written_fallback: {written}")
            print("Move this file into the system Cloudflare policy location with elevated privileges.")

    if not args.skip_activate:
        ok, detail = await activate_proxy_mode(args.proxy_port)
        print("proxy_activation:", "ok" if ok else "failed")
        if detail:
            print(detail)

    doctor = await warp_manager.warp_doctor()
    print("platform:", doctor["platform"])
    print("cli_path:", doctor["cli_path"] or "<not found>")
    print("proxy_url:", doctor["proxy_url"])
    print("proxy_reachable:", doctor["proxy_reachable"])
    print("ready:", doctor["ready"])
    if doctor["recommendations"]:
        print("recommendations:")
        for item in doctor["recommendations"]:
            print("-", item)
    return 0 if doctor["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
