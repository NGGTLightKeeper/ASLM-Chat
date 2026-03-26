# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""
Cross-platform Cloudflare WARP helper for selective proxy fallback.

This module is built around Cloudflare's local proxy mode:
  - the app traffic continues to use its normal network path by default
  - only selected fallback requests are sent through the local WARP proxy

The runtime supports three layers:
  1. Detect an already-running local WARP proxy
  2. Discover and use ``warp-cli`` on Windows/macOS/Linux if available
  3. Self-install the Python dependency ``curl_cffi`` when allowed
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import re
import shutil
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

try:
    from .. import config as _ws_config
except (ImportError, ValueError):
    try:
        import config as _ws_config
    except ImportError:
        _ws_config = None


DEFAULT_WARP_HOST = os.getenv("WARP_SOCKS5_HOST", "127.0.0.1")
DEFAULT_WARP_PORT = int(os.getenv("WARP_SOCKS5_PORT", "40000"))
DEFAULT_WARP_PROXY_URL = f"socks5://{DEFAULT_WARP_HOST}:{DEFAULT_WARP_PORT}"
WARP_CONNECT_TIMEOUT = float(os.getenv("WARP_CONNECT_TIMEOUT", "10.0"))

_CURL_CFFI_REQUESTS = None
_WARP_STATE_LOCK = asyncio.Lock()


def _config_value(name: str, default: Any) -> Any:
    return getattr(_ws_config, name, default)


def _configured_proxy_url() -> str:
    configured = str(_config_value("WARP_PROXY_URL", "") or "").strip()
    return configured or DEFAULT_WARP_PROXY_URL


def _configured_cli_path() -> str:
    configured = str(_config_value("WARP_CLI_PATH", "") or "").strip()
    return configured or os.getenv("SEARCH_WARP_CLI_PATH", "").strip()


def _auto_install_py_deps_enabled() -> bool:
    return bool(_config_value("WARP_AUTO_INSTALL_PY_DEPS", True))


def _ensure_proxy_mode_enabled() -> bool:
    return bool(_config_value("WARP_ENSURE_PROXY_MODE", True))


def _auto_disconnect_enabled() -> bool:
    return bool(_config_value("WARP_AUTO_DISCONNECT", True))


def default_warp_mdm_path(system_name: str | None = None) -> Path:
    system_name = (system_name or platform.system()).lower()
    if system_name == "windows":
        return Path(os.getenv("ProgramData", r"C:\ProgramData")) / "Cloudflare" / "mdm.xml"
    if system_name == "darwin":
        return Path("/Library/Application Support/Cloudflare/mdm.xml")
    return Path("/var/lib/cloudflare-warp/mdm.xml")


def render_warp_mdm_xml(*, proxy_port: int = DEFAULT_WARP_PORT, organization: str = "") -> str:
    organization_block = ""
    if organization.strip():
        organization_block = (
            "  <key>organization</key>\n"
            f"  <string>{organization.strip()}</string>\n"
        )
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        "<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" "
        "\"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">\n"
        "<plist version=\"1.0\">\n"
        "<dict>\n"
        f"{organization_block}"
        "  <key>service_mode</key>\n"
        "  <string>proxy</string>\n"
        "  <key>proxy_port</key>\n"
        f"  <integer>{int(proxy_port)}</integer>\n"
        "</dict>\n"
        "</plist>\n"
    )


def _cli_candidates() -> list[str]:
    configured = _configured_cli_path()
    candidates: list[str] = []
    if configured:
        candidates.append(configured)
    from_path = shutil.which("warp-cli")
    if from_path:
        candidates.append(from_path)

    system_name = platform.system().lower()
    if system_name == "windows":
        candidates.extend([
            r"C:\Program Files\Cloudflare\Cloudflare WARP\warp-cli.exe",
            r"C:\Program Files\Cloudflare\Cloudflare One Agent\warp-cli.exe",
            r"C:\Program Files\Cloudflare\WARP\warp-cli.exe",
        ])
    elif system_name == "darwin":
        candidates.extend([
            "/Applications/Cloudflare WARP.app/Contents/Resources/warp-cli",
            "/Applications/Cloudflare One Agent.app/Contents/Resources/warp-cli",
        ])
    else:
        candidates.extend([
            "/usr/bin/warp-cli",
            "/usr/local/bin/warp-cli",
            "/bin/warp-cli",
        ])

    seen: set[str] = set()
    ordered: list[str] = []
    for candidate in candidates:
        normalized = str(candidate).strip()
        if normalized and normalized not in seen:
            ordered.append(normalized)
            seen.add(normalized)
    return ordered


def find_warp_cli() -> str | None:
    for candidate in _cli_candidates():
        if Path(candidate).exists():
            return candidate
    return None


def _parse_mode(raw: str) -> str:
    if not raw:
        return ""
    patterns = [
        r"(?:service[_ ]mode|mode)\s*[:=]\s*([A-Za-z0-9_+-]+)",
        r"\b(warpproxy|proxy|warp|doh)\b",
    ]
    lowered = raw.lower()
    for pattern in patterns:
        match = re.search(pattern, lowered, re.IGNORECASE)
        if match:
            return match.group(1).lower()
    return ""


def _parse_proxy_port(raw: str) -> int | None:
    if not raw:
        return None
    patterns = [
        r"(?:proxy[_ ]port|port)\s*[:=]\s*(\d+)",
        r"\bon port\s+(\d+)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, raw, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def _proxy_host_port(proxy_url: str | None = None) -> tuple[str, int]:
    proxy_url = (proxy_url or _configured_proxy_url()).strip()
    parsed = urlparse(proxy_url)
    host = parsed.hostname or DEFAULT_WARP_HOST
    port = parsed.port or DEFAULT_WARP_PORT
    return host, int(port)


def _proxy_url_with_port(port: int) -> str:
    configured = _configured_proxy_url().strip()
    parsed = urlparse(configured)
    scheme = parsed.scheme or "socks5"
    host = parsed.hostname or DEFAULT_WARP_HOST
    return f"{scheme}://{host}:{int(port)}"


async def _run_warp_cli(*args: str, timeout: float = 10.0) -> tuple[int, str]:
    cli_path = find_warp_cli()
    if not cli_path:
        return -1, "warp-cli not found"

    cmd = [cli_path] + list(args)
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        output = (stdout or b"").decode(errors="replace").strip()
        return proc.returncode or 0, output
    except asyncio.TimeoutError:
        return -2, "warp-cli timed out"
    except Exception as exc:
        return -3, str(exc)


async def warp_status() -> dict:
    code, output = await _run_warp_cli("status")
    mode = _parse_mode(output)
    connected = "connected" in output.lower() and "disconnected" not in output.lower()
    return {
        "available": code >= 0,
        "connected": connected,
        "mode": mode,
        "proxy_port": _parse_proxy_port(output),
        "cli_path": find_warp_cli() or "",
        "raw": output,
    }


async def warp_settings() -> dict:
    code, output = await _run_warp_cli("settings")
    return {
        "available": code >= 0,
        "mode": _parse_mode(output),
        "proxy_port": _parse_proxy_port(output),
        "raw": output,
    }


async def warp_mdm_configs() -> dict:
    code, output = await _run_warp_cli("mdm", "get-configs")
    return {
        "available": code >= 0,
        "active": "<single-config>" if "Active: <single-config>" in output else "",
        "raw": output,
    }


async def resolve_warp_proxy_url() -> str:
    configured = _configured_proxy_url().strip()
    settings = await warp_settings()
    if settings["proxy_port"]:
        return _proxy_url_with_port(int(settings["proxy_port"]))
    return configured or DEFAULT_WARP_PROXY_URL


async def is_warp_proxy_reachable(proxy_url: str | None = None) -> bool:
    host, port = _proxy_host_port(proxy_url)
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=2.0,
        )
        writer.close()
        await writer.wait_closed()
        return True
    except Exception:
        return False


async def warp_doctor() -> dict:
    status = await warp_status()
    settings = await warp_settings() if status["available"] else {
        "available": False,
        "mode": "",
        "proxy_port": None,
        "raw": "",
    }
    mdm = await warp_mdm_configs() if status["available"] else {
        "available": False,
        "active": "",
        "raw": "",
    }
    proxy_url = await resolve_warp_proxy_url()
    proxy_reachable = await is_warp_proxy_reachable(proxy_url)

    recommendations: list[str] = []
    if not status["available"] and not proxy_reachable:
        recommendations.append(
            "Install the official Cloudflare WARP client, not only cloudflared, and make warp-cli discoverable."
        )
    if status["available"] and not status["connected"]:
        recommendations.append("Connect the WARP client before using selective fallback.")
    effective_mode = settings["mode"] or status["mode"]
    if status["available"] and effective_mode not in {"proxy", "warpproxy"} and not proxy_reachable:
        recommendations.append("Enable local proxy mode (service_mode=proxy) so the app can use selective WARP fallback.")
    if status["available"] and not mdm["active"]:
        recommendations.append("Apply the local mdm.xml policy so Cloudflare WARP keeps the proxy configuration persistent.")
    if status["available"] and not proxy_reachable:
        recommendations.append("Ensure the local WARP proxy is listening on the configured proxy_port.")

    return {
        "platform": platform.system(),
        "cli_path": status["cli_path"],
        "status": status,
        "settings": settings,
        "mdm": mdm,
        "proxy_url": proxy_url,
        "proxy_reachable": proxy_reachable,
        "ready": proxy_reachable,
        "recommendations": recommendations,
    }


async def _run_warp_cli_ok(*args: str, timeout: float = 10.0) -> tuple[bool, str]:
    code, output = await _run_warp_cli(*args, timeout=timeout)
    return code == 0, output


async def ensure_warp_proxy_mode(proxy_port: int | None = None) -> dict:
    target_port = int(proxy_port or _proxy_host_port()[1])
    status = await warp_status()
    if not status["available"]:
        return {"ok": False, "reason": "warp-cli unavailable", "status": status}

    settings = await warp_settings()
    mdm = await warp_mdm_configs()
    actions: list[str] = []

    if _ensure_proxy_mode_enabled():
        if mdm["active"]:
            ok, _ = await _run_warp_cli_ok("mdm", "set-config", mdm["active"], timeout=5.0)
            if ok:
                actions.append(f"mdm set-config {mdm['active']}")

        current_mode = settings["mode"] or status["mode"]
        if current_mode not in {"proxy", "warpproxy"}:
            ok, output = await _run_warp_cli_ok("mode", "proxy", timeout=10.0)
            if not ok:
                return {"ok": False, "reason": output or "mode proxy failed", "status": status, "settings": settings, "actions": actions}
            actions.append("mode proxy")

    if settings["proxy_port"] != target_port:
        ok, output = await _run_warp_cli_ok("proxy", "port", str(target_port), timeout=10.0)
        if not ok:
            return {"ok": False, "reason": output or "proxy port failed", "status": status, "settings": settings, "actions": actions}
        actions.append(f"proxy port {target_port}")

    refreshed_settings = await warp_settings()
    return {
        "ok": True,
        "actions": actions,
        "status": await warp_status(),
        "settings": refreshed_settings,
        "proxy_url": _proxy_url_with_port(refreshed_settings["proxy_port"] or target_port),
    }


async def warp_connect() -> bool:
    async with _WARP_STATE_LOCK:
        status = await warp_status()
        if not status["available"]:
            logger.warning("warp: warp-cli not available")
            return False

        setup = await ensure_warp_proxy_mode()
        if not setup["ok"]:
            logger.warning("warp: failed to configure proxy mode: %s", setup.get("reason", "unknown"))
            return False

        status = await warp_status()
        if status["connected"]:
            logger.debug("warp: already connected")
            return True

        code, output = await _run_warp_cli("disconnect", timeout=5.0)
        if code == 0:
            logger.debug("warp: pre-connect disconnect applied")

        code, output = await _run_warp_cli("connect", timeout=WARP_CONNECT_TIMEOUT)
        if code != 0:
            logger.warning("warp: connect failed: %s", output)
            return False

        await asyncio.sleep(1.0)
        post_status = await warp_status()
        ok = post_status["connected"]
        if ok:
            logger.info("warp: connected successfully")
        else:
            logger.warning("warp: connect returned 0 but status is not connected")
        return ok


async def warp_disconnect() -> None:
    async with _WARP_STATE_LOCK:
        code, output = await _run_warp_cli("disconnect", timeout=5.0)
        if code == 0:
            logger.debug("warp: disconnected")
        else:
            logger.debug("warp: disconnect result: %s", output)


@asynccontextmanager
async def warp_session(auto_connect: bool = True, auto_disconnect: bool | None = None):
    connected = False
    proxy_url = await resolve_warp_proxy_url()
    auto_disconnect = _auto_disconnect_enabled() if auto_disconnect is None else auto_disconnect

    if await is_warp_proxy_reachable(proxy_url):
        connected = True
    elif auto_connect:
        if await warp_connect():
            proxy_url = await resolve_warp_proxy_url()
            connected = await is_warp_proxy_reachable(proxy_url)
            if not connected:
                doctor = await warp_doctor()
                if doctor["recommendations"]:
                    logger.warning("warp: %s", doctor["recommendations"][0])

    try:
        yield proxy_url if connected else None
    finally:
        if auto_disconnect and connected:
            await warp_disconnect()


def _html_to_text(raw_html: str) -> str:
    raw = re.sub(
        r"<(script|style)[^>]*>.*?</\1>",
        "",
        raw_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return re.sub(r"\s{2,}", "\n", re.sub(r"<[^>]+>", " ", raw)).strip()


def _load_curl_cffi_requests():
    global _CURL_CFFI_REQUESTS
    if _CURL_CFFI_REQUESTS is not None:
        return _CURL_CFFI_REQUESTS

    try:
        from curl_cffi import requests as cffi_requests
    except ImportError:
        if not _auto_install_py_deps_enabled():
            raise
        logger.info("warp: installing missing Python dependency curl_cffi")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "curl_cffi"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        from curl_cffi import requests as cffi_requests

    _CURL_CFFI_REQUESTS = cffi_requests
    return _CURL_CFFI_REQUESTS


async def fetch_via_warp(
    url: str,
    *,
    proxy_url: str | None = None,
    timeout: int = 20,
) -> str:
    loop = asyncio.get_running_loop()
    cffi_requests = await loop.run_in_executor(None, _load_curl_cffi_requests)
    target_proxy_url = (proxy_url or await resolve_warp_proxy_url()).strip()

    def _do():
        response = cffi_requests.get(
            url,
            impersonate="chrome124",
            timeout=timeout,
            proxies={"http": target_proxy_url, "https": target_proxy_url},
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36"
                ),
            },
        )
        response.raise_for_status()
        return response.text

    try:
        raw = await loop.run_in_executor(None, _do)
        return _html_to_text(raw)
    except Exception as exc:
        logger.debug("warp: fetch failed for %s: %s", url, exc)
        return ""


async def fetch_via_warp_auto(
    url: str,
    *,
    timeout: int = 20,
) -> str:
    async with warp_session(auto_connect=True, auto_disconnect=None) as proxy:
        if not proxy:
            return ""
        return await fetch_via_warp(url, proxy_url=proxy, timeout=timeout)
